"""Reproduce the Rust/Python comparison on bounded, published CT and tifxyz crops."""

import argparse
import gzip
import hashlib
import json
import os
import platform
import random
import statistics
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from time import perf_counter, process_time
from urllib.request import urlopen

import numpy as np
import psutil
import zarr
from rust_bench import peak_rss

from vesuvius_data_explorer.core import chunkcache
from vesuvius_data_explorer.core.alignment import choose_level, grid_normals, level_factors
from vesuvius_data_explorer.core.alignment_map import (
    alignment_map,
    field_on_grid,
    reliable_tiles,
    review_zones,
    snap_field,
    snap_points,
    switch_tiles,
)
from vesuvius_data_explorer.core.catalog import parse_catalog
from vesuvius_data_explorer.core.flatten import flatten
from vesuvius_data_explorer.core.tifxyz import in_volume, load_tifxyz, write_tifxyz
from vesuvius_data_explorer.core.volume import open_levels
from vesuvius_data_explorer.qc.carte import run_map, write_outputs

SCANS = (
    ("0814", "20260226110425", "20250804134230", (36, 132), 16, None, .25),
    ("0500p2", "20250825181928", "20250526151718", None, 24, None, .20),
    ("0139-curved", "20260316000000", "20260413113053", None, 16, None, .40),
    ("0500p2-fine", "20250825181928", "20250526151718", (32, 80), 8, 1, .20),
)
BUCKET = "https://vesuvius-challenge-open-data.s3.amazonaws.com"
MAX_CT_BYTES = 96 * 2**20


def dump(path, content):
    path.write_text(json.dumps(content, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                    encoding="utf-8")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def find_origin(points, side, dispersion_target, within_budget):
    normals = grid_normals(points)
    stride = max(1, side // 2)
    candidates = []
    for row in range(0, points.shape[0] - side + 1, stride):
        for col in range(0, points.shape[1] - side + 1, stride):
            region = normals[row:row+side, col:col+side].reshape(-1, 3)
            valid = region[np.isfinite(region).all(axis=1)]
            if len(valid) >= side**2 * 0.9 and within_budget(points[row:row+side, col:col+side]):
                dispersion = float(np.linalg.norm(valid.std(axis=0)))
                candidates.append((abs(dispersion - dispersion_target), row, col))
    if not candidates:
        raise ValueError("No sufficiently complete patch in published surface")
    return min(candidates)[1:]


def prepare(root, catalog_file):
    if not catalog_file.exists():
        with urlopen(f"{BUCKET}/metadata.json", timeout=30) as response:
            raw = response.read(16 * 2**20 + 1)
        if len(raw) > 16 * 2**20:
            raise ValueError("Catalogue above download limit")
        catalog_file.write_bytes(raw)
    raw = catalog_file.read_bytes()
    cat = parse_catalog(json.loads(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw))
    manifest = root / "corpus.json"
    previous = ({record["name"]: record for record in json.loads(manifest.read_text(encoding="utf-8"))}
                if manifest.exists() else {})
    cases = []
    for name, segment_id, volume_id, origin, side, max_level, dispersion in SCANS:
        folder = root / name
        folder.mkdir(exist_ok=True)
        saved = previous.get(name)
        ct_file = folder / "ct.npy"
        if (saved and saved["volume"].find(volume_id) >= 0 and saved["surface_side"] == side and
                ct_file.is_file() and digest(ct_file) == saved["ct_sha256"]):
            cases.append(saved)
            print(f"Reusing {name}", flush=True)
            continue
        segment = next(s for s in cat.segments if s.segment_id == segment_id and
                       s.target_volume_id == volume_id and not s.superseded)
        volume = next(v for v in cat.volumes if v.volume_id == volume_id and v.codec == "standard")
        surface = load_tifxyz(segment.uri, max_bytes=4 * 2**20)
        if surface.stride != 1:
            raise ValueError(f"Decimated surface {surface.source}")
        arrays, levels = open_levels(volume.uri, cache=False)
        if max_level is not None:
            levels = levels[:max_level + 1]
        shapes = [level.shape for level in levels]
        level = choose_level(shapes, volume.pixel_size_um)
        array = arrays[level]
        factor = level_factors(shapes)[level]
        margin = np.ceil(250 / (volume.pixel_size_um * factor)).astype(int) + 3
        chunks = np.asarray(array.chunks)

        def bounds(region):
            finite = region[np.isfinite(region).all(axis=2)]
            projected = (finite + 0.5) / factor - 0.5
            low = np.maximum(((np.floor(projected.min(0)).astype(int) - margin) // chunks) * chunks, 0)
            high = np.minimum((np.floor(projected.max(0)).astype(int) + margin + chunks) // chunks
                              * chunks, array.shape)
            return low, high, int(np.prod(high - low)) * array.dtype.itemsize

        def eligible(region):
            return (in_volume(region, shapes[0]).mean() >= .9 and
                    0 < bounds(region)[2] <= MAX_CT_BYTES)

        row, col = origin or find_origin(surface.points, side, dispersion, eligible)
        points = surface.points[row:row+side, col:col+side].copy()
        finite = points[np.isfinite(points).all(axis=2)]
        # Cover the full ±200 µm normal sampling, interpolator neighbours, and ±50 µm snap.
        low, high, decoded_bytes = bounds(points)
        if not 0 < decoded_bytes <= MAX_CT_BYTES:
            raise ValueError(f"{name} exceeds the CT crop limit ({decoded_bytes} bytes)")
        started = perf_counter()
        block = array[tuple(slice(a, b) for a, b in zip(low, high))]
        seconds = perf_counter() - started
        np.save(ct_file, block)
        segment_folder = folder / "segment"
        if not segment_folder.exists():
            write_tifxyz(segment_folder, points, surface.meta)
        # Tifxyz uses float32 coordinates. The input is already float32 before decoding.
        np.testing.assert_array_equal(load_tifxyz(str(segment_folder)).points, points)
        case = {
            "name": name, "volume": volume.uri, "segment": segment.uri, "level": level,
            "pixel_size_um": volume.pixel_size_um, "shapes": shapes, "factor_zyx": factor.tolist(),
            "chunks": chunks.tolist(), "lo_zyx": low.tolist(), "hi_zyx": high.tolist(),
            "dtype": str(block.dtype), "ct_sha256": digest(folder / "ct.npy"),
            "uv_origin_rc": [row, col], "surface_side": side,
            "surface_files_sha256": {p.name: digest(p) for p in sorted(segment_folder.glob("*"))},
            "surface_valid_pct": 100 * len(finite) / points.shape[0] / points.shape[1],
            "normal_dispersion": float(np.linalg.norm(np.nanstd(grid_normals(points), axis=(0, 1)))),
            "region_decoded_bytes": decoded_bytes, "roi_remote_read_ms": seconds * 1e3,
        }
        cases.append(case)
        dump(root / "corpus.json", cases)
        print(f"Saved {name}: L{level}, {decoded_bytes / 2**20:g} MiB", flush=True)


class CroppedSource:
    """Serve the recorded voxels in the original ZYX frame; fail on incomplete coverage."""

    def __init__(self, data, case):
        self.data, self.dtype = data, data.dtype
        self.lo, self.hi = case["lo_zyx"], case["hi_zyx"]
        self.shape = tuple(case["shapes"][case["level"]])
        self.chunks = tuple(case["chunks"])
        self.reset()

    def reset(self):
        self.accesses, self.keys, self.bytes = 0, set(), 0

    def __getitem__(self, selection):
        if any(s.start < low or s.stop > high for s, low, high in zip(selection, self.lo, self.hi)):
            raise ValueError(f"Validation requested voxels outside the downloaded ROI: {selection}")
        block = self.data[tuple(slice(s.start - lo, s.stop - lo) for s, lo in zip(selection, self.lo))]
        self.keys.add(tuple(s.start // c for s, c in zip(selection, self.chunks)))
        self.accesses += 1
        self.bytes += block.nbytes
        return block


def distribution(values):
    return {"mean_ms": statistics.mean(values), "median_ms": statistics.median(values),
            "p95_ms": float(np.percentile(values, 95)), "samples_ms": values}


def worker(root, case, backend, side, repeats):
    os.environ["VESUVIUS_RUST_SAMPLER"] = "1" if backend == "rust" else "0"
    if backend == "rust" and chunkcache._rust_sampler() is None:
        raise RuntimeError("The Rust wheel is required")
    folder = root / case["name"]
    backing = CroppedSource(np.load(folder / "ct.npy", mmap_mode="r"), case)
    original = load_tifxyz(str(folder / "segment"))
    start = (original.points.shape[0] - side) // 2
    surface = replace(original, points=original.points[start:start+side, start:start+side],
                      grid_shape=(side, side))
    run_folder = Path(tempfile.mkdtemp(prefix=f"{side}-{backend}-", dir=folder))
    segment = write_tifxyz(run_folder / "segment", surface.points, surface.meta)
    shapes, px, level = case["shapes"], case["pixel_size_um"], case["level"]
    arrays = [None] * len(shapes)
    arrays[level] = backing
    name = f"{side}-{backend}"
    times = {"map": [], "render": [], "report": []}
    first_rss = psutil.Process().memory_info().rss
    cpu_start = process_time()
    for repeat in range(repeats + 1):
        started = perf_counter()
        amap = alignment_map(surface, arrays, shapes, pixel_size_um=px)
        times["map"].append((perf_counter() - started) * 1e3)
        started = perf_counter()
        render = flatten(surface.points, arrays, shapes, level=level, step_voxels=surface.step_voxels,
                         normal_offsets=(-1., 0., 1.))
        times["render"].append((perf_counter() - started) * 1e3)
        started = perf_counter()
        result = run_map(str(segment), arrays, shapes, pixel_size_um=px, snap=True)
        write_outputs(result, run_folder / f"report-{repeat}")
        times["report"].append((perf_counter() - started) * 1e3)
    cpu_ms = (process_time() - cpu_start) * 1e3
    raw = {name: getattr(amap, name) for name in ("profiles", "points", "centers", "offset",
           "reliability", "uncertainty", "residues", "drift", "sheet", "unwrapped", "offsets")}
    mask = reliable_tiles(amap)
    field = snap_field(amap, max_shift=50 / px)
    grid = field_on_grid(field, amap, surface.points.shape[:2])
    raw.update(render=render, reliable=mask, switches=switch_tiles(amap), snap_field=grid,
               snapped=snap_points(surface.points, grid))
    np.savez(folder / f"parity-{name}.npz", **raw)
    zones = review_zones(amap, pixel_size_um=px)
    return {
        "backend": backend, "side": side, "case": case["name"], "dtype": case["dtype"],
        "time": {key: {"first_ms": values[0], **distribution(values[1:])}
                 for key, values in times.items()},
        "baseline_rss_bytes": first_rss, "peak_rss_bytes": peak_rss(), "process_cpu_ms": cpu_ms,
        "decoded_accesses": backing.accesses, "decoded_bytes": backing.bytes,
        "distinct_chunk_keys_zyx": sorted(backing.keys), "map_voxels_read": amap.voxels_read,
        "tiles_measured": int((amap.points > 0).sum()), "tiles_reliable": int(mask.sum()),
        "tiles_near_reliability_threshold": int((np.abs(amap.reliability - 3) <= .05).sum()),
        "reference_voxels": amap.reference, "spacing_voxels": amap.spacing,
        "zones": zones, "warnings": list(amap.warnings), "wraps": amap.wraps,
    }


def compare(folder, python, rust):
    side = python["side"]
    result = {"case": python["case"], "side": side, "errors": {}}
    for key in ("tiles_measured", "tiles_reliable", "tiles_near_reliability_threshold",
                "distinct_chunk_keys_zyx", "map_voxels_read", "wraps", "warnings"):
        assert python[key] == rust[key], key
    for key in ("reference_voxels", "spacing_voxels"):
        if python[key] is None:
            assert rust[key] is None, key
        else:
            np.testing.assert_allclose(rust[key], python[key], rtol=0, atol=1e-8, err_msg=key)
    for field in ("type", "rang", "tuiles"):
        assert [z[field] for z in python["zones"]] == [z[field] for z in rust["zones"]], field
    with (np.load(folder / f"parity-{side}-python.npz") as left,
          np.load(folder / f"parity-{side}-rust.npz") as right):
        for key in left.files:
            a, b = left[key], right[key]
            assert a.dtype == b.dtype and a.shape == b.shape, key
            if a.dtype.kind != "f":
                np.testing.assert_array_equal(a, b, err_msg=key)
                continue
            np.testing.assert_array_equal(np.isfinite(a), np.isfinite(b), err_msg=key)
            np.testing.assert_array_equal(np.isnan(a), np.isnan(b), err_msg=key)
            tolerance = 0.004 if a.dtype == np.float32 else 1e-8
            np.testing.assert_allclose(a, b, rtol=0, atol=tolerance, err_msg=key)
            valid = np.isfinite(a)
            error = np.abs(a[valid].astype(float) - b[valid])
            result["errors"][key] = {"max_abs": float(np.max(error, initial=0)),
                                     "rmse": float(np.sqrt(np.mean(error**2))) if len(error) else 0}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--worker", nargs=3, metavar=("CASE", "BACKEND", "SIDE"))
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    if args.prepare:
        prepare(args.root, args.root / "catalog.json")
        return
    cases = json.loads((args.root / "corpus.json").read_text(encoding="utf-8"))
    if args.worker:
        name, backend, side = args.worker
        print(json.dumps(worker(args.root, next(c for c in cases if c["name"] == name), backend,
                                int(side), args.repeats), ensure_ascii=True, allow_nan=False))
        return
    if not args.output or args.repeats < 2:
        parser.error("Specify --output and at least two repeats")
    rows, parity = [], []
    order = random.Random(2026)
    for case in cases:
        large = case["surface_side"]
        small = {8: 6, 16: 8, 24: 12}[large]
        for side in (small, large):
            by_backend = {}
            for backend in order.sample(["python", "rust"], 2):
                command = [sys.executable, __file__, str(args.root), "--repeats", str(args.repeats),
                           "--worker", case["name"], backend, str(side)]
                response = subprocess.run(command, capture_output=True, encoding="utf-8",
                                          env={**os.environ, "PYTHONIOENCODING": "utf-8"})
                if response.returncode:
                    raise RuntimeError(f"{case['name']} {side} {backend}:\n{response.stderr}")
                by_backend[backend] = json.loads(response.stdout)
            rows.extend(by_backend.values())
            parity.append(compare(args.root / case["name"], **by_backend))
            print(f"Measured {case['name']}/{side}", flush=True)
        dump(args.output, {"platform": platform.platform(), "python": sys.version,
                           "numpy": np.__version__, "zarr": zarr.__version__,
                           "repeats_after_first": args.repeats, "corpus": cases, "parity": parity,
                           "results": rows})


if __name__ == "__main__":
    main()
