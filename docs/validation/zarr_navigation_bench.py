"""Trace application ROI reads through the real S3 Zarr store and persistent chunk cache."""

import argparse
import cProfile
import io
import os
import pstats
import tempfile
from collections import Counter
from pathlib import Path
from time import perf_counter, process_time

import numpy as np
import zarr
from rust_bench import peak_rss
from rust_real_bench import distribution, dump
from zarr.abc.store import Store
from zarr.storage import FsspecStore, WrapperStore

from vesuvius_data_explorer.core.cache import cache_size, cached_store
from vesuvius_data_explorer.core.volume import list_levels, normalized_preview, read_slice

URI = ("s3://vesuvius-challenge-open-data/PHerc0800/volumes/"
       "20250521135224-8.640um-1.2m-116keV-masked.zarr")
BLOCK_BYTES = 128**3
REQUEST_BUDGET = 44  # Per remote session, at most 88 MiB of raw data.


class MeasuredStore(WrapperStore):
    def __init__(self, store, events, budget=None):
        super().__init__(store)
        self.events, self.budget = events, budget

    def with_read_only(self, read_only=False):
        return type(self)(self._store.with_read_only(read_only), self.events, self.budget)

    async def get(self, key, prototype, byte_range=None):
        chunk = len(key.split("/")) == 4 and all(part.isdigit() for part in key.split("/"))
        if chunk and self.budget is not None:
            self.budget[0] -= 1
            if self.budget[0] < 0:
                raise RuntimeError("Remote chunk request budget exceeded")
        started = perf_counter()
        value = await self._store.get(key, prototype, byte_range)
        self.events.append((started, perf_counter(), key, chunk, len(value) if value else 0))
        if chunk and value and len(value) > BLOCK_BYTES:
            raise RuntimeError("Unexpected block size for this validation")
        return value

    def _get_many(self, requests):
        return Store._get_many(self, requests)


def summarize(events):
    chunks = [event for event in events if event[3]]
    total, stop = 0.0, 0.0
    for begin, end, *_ in sorted(events):
        total += max(0, end - max(begin, stop))
        stop = max(stop, end)
    return {
        "calls": len(events), "data_calls": len(chunks), "bytes": sum(event[4] for event in events),
        "data_bytes": sum(event[4] for event in chunks),
        "union_ms": total * 1e3, "keys": dict(Counter(event[2] for event in chunks)),
        "data_request_ms": (distribution([(end - begin) * 1e3 for begin, end, *_ in chunks])
                            if chunks else None),
    }


def open_logged(root, use_cache, budget=None):
    before, after = [], []
    source = FsspecStore.from_url(URI, storage_options={"anon": True}, read_only=True)
    store = MeasuredStore(source, before, budget=[REQUEST_BUDGET] if budget is None else budget)
    if use_cache:
        store = cached_store(store, URI, root=root)
    store = MeasuredStore(store, after)
    start = perf_counter()
    group = zarr.open_group(store=store, mode="r", zarr_format=2, use_consolidated=False)
    levels = list_levels(group)
    array = group[levels[0].key]
    if array.chunks != (128, 128, 128) or array.dtype != np.uint8 or array.metadata.compressor:
        raise RuntimeError("PHerc0800 metadata differs from the pinned uncompressed fixture")
    summary = {"wall_ms": (perf_counter() - start) * 1e3, "source": summarize(before),
               "store": summarize(after)}
    return array, before, after, summary


TRAJECTORY = (
    ("narrow", "z", 12058, 6200, 3350, 48),
    ("narrow", "z", 12059, 6200, 3350, 48),
    ("narrow", "z", 12063, 6200, 3350, 48),
    ("narrow", "z", 12161, 6200, 3350, 48),
    ("wide", "z", 12058, 6230, 3400, 128),
    ("wide", "z", 12059, 6230, 3400, 128),
    ("wide", "z", 12060, 6230, 3400, 128),
    ("wide", "z", 12064, 6230, 3400, 128),
    ("wide", "y", 6260, 12045, 3400, 128),
    ("wide", "x", 3396, 12045, 6230, 128),
)


def navigate(array, before, after):
    results = []
    for label, axis, index, a, b, side in TRAJECTORY:
        before.clear()
        after.clear()
        cpu = process_time()
        started = perf_counter()
        raw = read_slice(array, axis, index, a, b, side)
        read_ms = (perf_counter() - started) * 1e3
        started = perf_counter()
        preview = normalized_preview(raw)
        normalize_ms = (perf_counter() - started) * 1e3
        results.append({"roi": [label, axis, index, a, b, side], "read_ms": read_ms,
                        "normalize_ms": normalize_ms, "cpu_ms": (process_time() - cpu) * 1e3,
                        "source": summarize(before), "store": summarize(after),
                        "raw_sum": int(raw.sum()), "preview_sum": float(preview.sum())})
    return results


def run(root, concurrency):
    os.environ["VESUVIUS_CACHE"] = "1"
    zarr.config.set({"async.concurrency": concurrency})
    phases, reference = {}, None
    with tempfile.TemporaryDirectory(prefix="zarr-nav-", dir=root) as folder:
        cache = Path(folder)
        for label in ("direct", "empty_cache", "reused_cache"):
            array, before, after, opening = open_logged(cache, label != "direct")
            values = navigate(array, before, after)
            sums = [(row["raw_sum"], row["preview_sum"]) for row in values]
            if reference is None:
                reference = sums
            assert reference == sums, "Navigation and cache must produce matching results"
            phases[label] = {"open": opening, "steps": values, "cache_bytes": cache_size(cache),
                             "read_ms": distribution([row["read_ms"] for row in values]),
                             "network_data_calls": sum(row["source"]["data_calls"] for row in values),
                             "network_data_bytes": sum(row["source"]["data_bytes"] for row in values),
                             "requested_data_calls": sum(row["store"]["data_calls"] for row in values)}
        profiler = cProfile.Profile()
        profiler.runcall(navigate, array, before, after)
        profile = io.StringIO()
        pstats.Stats(profiler, stream=profile).strip_dirs().sort_stats("cumulative").print_stats(18)
    return {"uri": URI, "concurrency": concurrency, "zarr": zarr.__version__,
            "peak_process_rss_bytes": peak_rss(), "profile_warm_sync_caller": profile.getvalue(),
            "phases": phases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--concurrency", type=int, default=64)
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    dump(args.output, run(args.root, args.concurrency))


if __name__ == "__main__":
    main()
