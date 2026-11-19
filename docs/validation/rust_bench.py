"""Reproduce the CT projection comparison and its I/O controls on bounded fixtures."""

import argparse
import cProfile
import io
import json
import os
import platform
import pstats
import random
import shutil
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path
from time import perf_counter, process_time

import numpy as np
import psutil
import scipy
import zarr
from numcodecs import Blosc
from scipy import ndimage

from vesuvius_data_explorer.core import chunkcache
from vesuvius_data_explorer.core.chunkcache import DecodedChunks
from vesuvius_data_explorer.core.flatten import flatten
from vesuvius_data_explorer.core.volume import normalized_preview, read_slice

CHUNKS = (32, 32, 32)
SIZES = {"small": (48, 101, 117), "large": (96, 301, 333)}
BACKENDS = ("python", "scipy", "rust")
STAGES = ("block_read", "blosc_decode", "roi", "preview", "ink_components")
CASES = (("surface_points", "memory"), ("surface_render", "memory"),
         ("surface_render", "zarr"))


class TimedArray:
    def __init__(self, array):
        self.array = array
        self.shape, self.dtype = array.shape, array.dtype
        self.chunks = getattr(array, "chunks", CHUNKS)
        self.reset()

    def reset(self):
        self.upstream_seconds, self.bytes, self.blocks = 0.0, 0, 0

    def __getitem__(self, selection):
        start = perf_counter()
        block = self.array[selection]
        self.upstream_seconds += perf_counter() - start
        self.bytes += block.nbytes
        self.blocks += 1
        return block


def scipy_sampler(array, coords):
    """Group inner points once and use SciPy C interpolation. Keep the reference at crossings."""
    coords = np.clip(coords, 0, np.asarray(array.shape) - 1)
    chunks = np.asarray(array.chunks)
    base = coords.astype(np.int64)
    keys = base // chunks
    inner = (keys == np.minimum(base + 1, np.asarray(array.shape) - 1) // chunks).all(axis=1)
    result = np.empty(len(coords), dtype=np.float64)
    if (~inner).any():
        result[~inner] = chunkcache._sample_python(array, coords[~inner])
    members = np.flatnonzero(inner)
    if len(members):
        labels = np.ravel_multi_index(keys[members].T, tuple(-(-np.asarray(array.shape) // chunks)))
        order = np.argsort(labels, kind="stable")
        starts = np.flatnonzero(labels[order[1:]] != labels[order[:-1]]) + 1
        for indices in np.split(members[order], starts):
            key = keys[indices[0]]
            result[indices] = ndimage.map_coordinates(
                array._chunk(tuple(key)), (coords[indices] - key * chunks).T,
                order=1, mode="nearest", output=np.float64,
            )
    return result


def surface(shape):
    r, c = np.mgrid[4:shape[1] - 4:4, 4:shape[2] - 4:4]
    z = shape[0] / 2 + 9 * np.sin(r / 31) * np.cos(c / 26)
    return np.stack((z, r, c), axis=-1)


def make_fixtures(root, size, crop):
    rng = np.random.default_rng(42)
    dtype = np.uint8 if size == "small" else np.uint16
    volume = (np.load(crop, allow_pickle=False) if crop else
              rng.integers(0, np.iinfo(dtype).max + 1, SIZES[size], dtype=dtype))
    if volume.ndim != 3 or any(n < 32 or n > 512 for n in volume.shape):
        raise ValueError("Expected a 3D crop between 32 and 512 voxels per axis")
    if volume.dtype not in (np.uint8, np.uint16):
        raise ValueError("Expected native uint8 or uint16")
    group = zarr.open_group(str(root / size), mode="w", zarr_format=2)
    group.attrs["multiscales"] = [{"version": "0.4", "axes": ["z", "y", "x"], "datasets": [
        {"path": "0", "coordinateTransformations": [{"type": "scale", "scale": [1, 1, 1]}]},
    ]}]
    codec = Blosc(cname="zstd", clevel=3, shuffle=Blosc.SHUFFLE)
    array = group.create_array("0", shape=volume.shape, dtype=volume.dtype, chunks=CHUNKS,
                               compressor=codec)
    array[:] = volume
    np.save(root / (size + ".npy"), volume)
    (root / (size + ".block")).write_bytes(volume[:32, :32, :32].tobytes())
    return {"shape_zyx": volume.shape, "dtype": str(volume.dtype), "chunks_zyx": CHUNKS}


def instruments(times, units):
    return {
        "mean_ms": statistics.mean(times) * 1e3,
        "median_ms": statistics.median(times) * 1e3,
        "p95_ms": float(np.percentile(times, 95)) * 1e3,
        "units_per_second": units / statistics.mean(times),
    }


def peak_rss():
    if sys.platform == "win32":
        return psutil.Process().memory_info().peak_wset
    import resource

    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin"
                                                                else 1024)


def worker(args):
    root = args.fixture_dir
    start = perf_counter()
    volume = (np.load(root / (args.size + ".npy"), allow_pickle=False) if args.store == "memory"
              else zarr.open_array(str(root / args.size / "0"), mode="r"))
    open_ms = (perf_counter() - start) * 1e3
    backing = TimedArray(volume)
    reference = chunkcache._sample_python
    sampler = {"python": reference, "scipy": scipy_sampler,
               "rust": chunkcache.sample_trilinear}[args.backend]
    os.environ["VESUVIUS_RUST_SAMPLER"] = "1" if args.backend == "rust" else "0"
    if args.backend == "rust" and chunkcache._rust_sampler() is None:
        raise RuntimeError("Build and install the Rust release wheel before benchmarking it")
    points = surface(backing.shape)
    coords = points.reshape(-1, 3) + [0.3, 0.2, 0.7]
    raw_path = root / (args.size + ".block")
    if args.case == "surface_render":
        def action():
            return flatten(points, [backing], [backing.shape], level=0, step_voxels=4,
                           normal_offsets=(-1, 0, 1))

        units = (4 * (points.shape[0] - 1) + 1) * (4 * (points.shape[1] - 1) + 1) * 3
    elif args.case == "surface_points":
        decoded = DecodedChunks(backing)

        def action():
            return sampler(decoded, coords)

        units = len(coords)
    elif args.case == "block_read":
        action, units = raw_path.read_bytes, raw_path.stat().st_size
    elif args.case == "blosc_decode":
        codec = Blosc(cname="zstd", clevel=3, shuffle=Blosc.SHUFFLE)
        raw = raw_path.read_bytes()
        encoded = codec.encode(np.frombuffer(raw, dtype=volume.dtype))

        def action():
            return codec.decode(encoded)

        units = len(raw)
    elif args.case == "roi":
        def action():
            return np.asarray(backing[8:40, 8:40, 8:40])

        units = np.prod([min(n, 40) - 8 for n in volume.shape]).item()
    elif args.case == "preview":
        def action():
            return normalized_preview(read_slice(backing, "z", volume.shape[0] // 2, 0, 0,
                                                 volume.shape[1], volume.shape[2]))

        units = volume.shape[1] * volume.shape[2]
    else:
        scores = np.random.default_rng(42).random(volume.shape[1:], dtype=np.float32)

        def action():
            return ndimage.label(scores >= 0.85)[0]

        units = scores.size

    # Leave the production dispatcher in place for Rust and for the reference. The optimized
    # Python experiment is confined to this benchmark process.
    if args.case == "surface_render" and args.backend == "scipy":
        chunkcache.sample_trilinear = scipy_sampler
    base_rss = psutil.Process().memory_info().rss
    cpu_start = process_time()
    times, upstream, read_bytes, blocks = [], [], [], []
    for _ in range(args.repeats + 1):
        backing.reset()
        tick = perf_counter()
        result = action()
        times.append(perf_counter() - tick)
        upstream.append(backing.upstream_seconds)
        read_bytes.append(backing.bytes)
        blocks.append(backing.blocks)
    record = {
        "size": args.size, "case": args.case, "store": args.store, "backend": args.backend,
        "open_ms": open_ms, "first_ms": times[0] * 1e3,
        "first_upstream_ms": upstream[0] * 1e3, "first_upstream_bytes": read_bytes[0],
        "first_upstream_calls": blocks[0], "warm_upstream_bytes_median": statistics.median(read_bytes[1:]),
        "warm_upstream_ms_median": statistics.median(upstream[1:]) * 1e3,
        "warm_non_upstream_ms_median": statistics.median(
            total - access for total, access in zip(times[1:], upstream[1:])) * 1e3,
        "unit": "bytes" if args.case in ("block_read", "blosc_decode") else "samples",
        "initial_rss_bytes": base_rss, "peak_process_rss_bytes": peak_rss(),
        "process_cpu_percent_one_core": 100 * (process_time() - cpu_start) / sum(times),
        **instruments(times[1:], units),
    }
    if args.case.startswith("surface_"):
        np.save(root / f"{args.size}-{args.case}-{args.store}-{args.backend}.npy", result)
    if args.profile and args.case == "surface_render" and args.store == "memory" and args.backend == "python":
        profiler = cProfile.Profile()
        profiler.runcall(action)
        summary = io.StringIO()
        pstats.Stats(profiler, stream=summary).strip_dirs().sort_stats("cumulative").print_stats(16)
        record["profile"] = summary.getvalue()
    return record


def run(args, root):
    results, sizes = [], {}
    order = random.Random(42)
    labels = [*SIZES, "real"] if args.crop else list(SIZES)
    for size in labels:
        sizes[size] = make_fixtures(root, size, args.crop if size == "real" else None)
        cases = [(case, store, backend) for case, store in CASES for backend in BACKENDS]
        cases += [(case, "zarr", "python") for case in STAGES]
        order.shuffle(cases)
        for case, store, backend in cases:
            command = [sys.executable, __file__, "--fixture-dir", str(root), "--size", size,
                       "--case", case, "--store", store, "--backend", backend,
                       "--repeats", str(args.repeats)]
            if args.profile:
                command.append("--profile")
            completed = subprocess.run(command, capture_output=True, text=True,
                                       encoding="utf-8")
            if completed.returncode:
                raise RuntimeError(f"{size}/{case}/{store}/{backend}\n{completed.stderr}")
            results.append(json.loads(completed.stdout))
        for case, store in CASES:
            expected = np.load(root / f"{size}-{case}-{store}-python.npy")
            tolerance = 1e-8 if expected.dtype == np.float64 else 0.004
            for backend in BACKENDS[1:]:
                observed = np.load(root / f"{size}-{case}-{store}-{backend}.npy")
                assert observed.shape == expected.shape and observed.dtype == expected.dtype
                np.testing.assert_array_equal(np.isnan(observed), np.isnan(expected))
                np.testing.assert_allclose(observed, expected, rtol=0, atol=tolerance)
                valid = np.isfinite(expected)
                record = next(item for item in results if (item["size"], item["case"], item["store"],
                              item["backend"]) == (size, case, store, backend))
                record["max_abs_error"] = float(
                    np.max(np.abs(observed[valid] - expected[valid]), initial=0))
    rustc = shutil.which("rustc")
    return {
        "python": sys.version, "numpy": np.__version__, "scipy": scipy.__version__,
        "zarr": zarr.__version__, "platform": platform.platform(), "cpu": platform.processor(),
        "cores": psutil.cpu_count(logical=False), "threads": psutil.cpu_count(),
        "ram_bytes": psutil.virtual_memory().total, "repetitions_after_first": args.repeats,
        "rustc_on_path": subprocess.check_output([rustc, "--version"], text=True).strip()
        if rustc else None,
        "sizes": sizes, "real_crop_source": args.source, "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=15)
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--crop", type=Path, help="Optional small real CT crop in NumPy format")
    parser.add_argument("--source", help="Provenance of the real crop including level and ZYX ROI")
    parser.add_argument("--output", type=Path, help="Write results as UTF-8 JSON")
    parser.add_argument("--fixture-dir", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--size", choices=(*SIZES, "real"), help=argparse.SUPPRESS)
    parser.add_argument("--case", choices=(*{case for case, _ in CASES}, *STAGES), help=argparse.SUPPRESS)
    parser.add_argument("--store", choices=("memory", "zarr"), help=argparse.SUPPRESS)
    parser.add_argument("--backend", choices=BACKENDS, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.repeats < 2 or bool(args.crop) != bool(args.source):
        parser.error("Use at least two warm repetitions and pair --crop with --source")
    if args.fixture_dir:
        result = worker(args)
    else:
        with tempfile.TemporaryDirectory(prefix="vesuvius-rust-bench-") as directory:
            result = run(args, Path(directory))
    payload = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)


if __name__ == "__main__":
    main()
