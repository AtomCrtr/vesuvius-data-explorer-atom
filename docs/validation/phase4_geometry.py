"""Infer the local sampling kernel of public CT pyramids from their voxel values."""

import argparse
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
from phase3_science import MASKED16, SURFACE16, SURFACE_V3, V3, VOLUME
from scipy.ndimage import map_coordinates
from zarr_navigation_bench import URI

from vesuvius_data_explorer.core.flatten import flatten
from vesuvius_data_explorer.core.geometry import level_factors, to_level, verified_sampling
from vesuvius_data_explorer.core.tifxyz import load_tifxyz
from vesuvius_data_explorer.core.volume import open_levels

SAMPLES = {
    "paris4_20260310170716": (VOLUME + ".zarr", ((3072, 1024, 1024), (2968, 1328, 1248))),
    "paris4_20230205180739": (MASKED16, ((8512, 4592, 3280), (8480, 4560, 3248))),
    "pherc0800": (URI, ((12056, 6200, 3352), (12144, 6232, 3400))),
}
WEIGHTS = {"even": (1.0, 0.0), "odd": (0.0, 1.0), "mean": (0.5, 0.5)}
SURFACES = {"paris4_20260310170716": (SURFACE_V3, 294, 276, 3),
            "paris4_20260310170716_sharded": (SURFACE_V3, 294, 276, 3),
            "paris4_20230205180739": (SURFACE16, 267, 746, 3)}


def digest(array):
    return hashlib.sha256(np.ascontiguousarray(array).view("u1")).hexdigest()


def assess(fine, coarse):
    """Compare spatial hypotheses jointly, with floor, round and ceil quantizers."""
    z, y, x = coarse.shape
    cells = fine.reshape(z, 2, y, 2, x, 2)
    rows = []
    foreground = (cells.max(axis=(1, 3, 5)) > 0) | (coarse > 0)
    if foreground.sum() < 24 or np.ptp(coarse[foreground]) < 5:
        raise ValueError("Insufficient distinct CT structure in the reference region")
    for kernel in itertools.product(WEIGHTS, repeat=3):
        wz, wy, wx = (np.asarray(WEIGHTS[name]) for name in kernel)
        prediction = np.einsum("zaybxc,a,b,c->zyx", cells, wz, wy, wx, optimize=True)
        for quantizer in (np.floor, np.rint, np.ceil):
            delta = quantizer(prediction)[foreground] - coarse[foreground]
            rows.append({"kernel_zyx": kernel, "rounding": quantizer.__name__,
                         "mae": float(np.abs(delta).mean()),
                         "exact": int(np.count_nonzero(delta == 0)),
                         "max_error": int(np.abs(delta).max())})
    return {"foreground": int(foreground.sum()), "coarse_range": [int(coarse.min()), int(coarse.max())],
            "scores": sorted(rows, key=lambda row: (row["mae"], -row["exact"]))}


def read_pair(arrays, center, level, side=8):
    start = np.asarray(center) // (2 ** (level + 1)) - side // 2
    coarse = arrays[level + 1][tuple(slice(int(c), int(c + side)) for c in start)]
    fine = arrays[level][tuple(slice(int(2*c), int(2*(c + side))) for c in start)]
    assert fine.shape == (side * 2,) * 3 and coarse.shape == (side,) * 3
    return start, fine, coarse


def surface_check(uri, arrays, levels, case):
    source, v, u, level = case
    surface = load_tifxyz(source)
    points = surface.points[v:v+3, u:u+3]
    assert points.shape == (3, 3, 3) and np.isfinite(points).all()
    sampling = verified_sampling(uri, levels)
    assert sampling is not None, (uri, levels[:4])
    shapes = [item.shape for item in levels]
    # Independent UV interpolation oracle: half a grid cell in U, then in V.
    grid = np.arange(3, dtype=float)
    coords = np.linspace(0, 2, 5)
    across = np.array([[np.interp(coords, grid, row[:, axis]) for axis in range(3)]
                       for row in points])
    dense = np.stack([[np.interp(coords, grid, across[:, axis, col]) for col in range(5)]
                      for axis in range(3)], axis=-1).transpose(1, 0, 2)
    f = 2**level
    expected_level = (dense - (f - 1) / 2) / f
    extent = to_level(dense, level_factors(shapes)[level])
    metadata = dense / f
    starts = np.floor(np.minimum(expected_level, metadata).min(axis=(0, 1))).astype(int) - 1
    stops = np.ceil(np.maximum(expected_level, metadata).max(axis=(0, 1))).astype(int) + 2
    selection = tuple(slice(a, b) for a, b in zip(starts, stops))
    box = arrays[level][selection]
    expect = map_coordinates(box.astype(float), (expected_level - starts).reshape(-1, 3).T,
                             order=1, mode="nearest").reshape(5, 5)
    image = flatten(points, arrays, shapes, level=level, step_voxels=2*f, sampling=sampling)
    np.testing.assert_allclose(image, expect, rtol=0, atol=2e-5)
    historical = flatten(points, arrays, shapes, level=level, step_voxels=2*f)
    return {"surface": source, "uv_origin": [v, u], "level": level, "zyx_sha256": digest(points),
            "crop_zyx": [starts.tolist(), stops.tolist()], "ct_sha256": digest(box),
            "render_sha256": digest(image), "render": image.tolist(),
            "old_vs_verified_level_voxel": np.abs(extent-expected_level).max(axis=(0, 1)).tolist(),
            "ngff_vs_verified_level_voxel": np.abs(metadata-expected_level).max(axis=(0, 1)).tolist(),
            "max_historical_ct_error": float(np.max(np.abs(historical-image))),
            "max_oracle_ct_error": float(np.max(np.abs(expect-image)))}


def run(root, samples):
    results = {}
    for name, (uri, centers) in samples.items():
        arrays, levels = open_levels(uri, cache=True)
        sample = {"uri": uri, "levels": [{"shape": level.shape, "scale": level.scale}
                                         for level in levels], "regions": []}
        for region, center in enumerate(centers):
            for level in range(3):
                start, fine, coarse = read_pair(arrays, center, level)
                file = root / f"{name}-{region}-l{level}.npz"
                np.savez_compressed(file, fine=fine, coarse=coarse)
                result = assess(fine, coarse)
                result.update({"level": level, "center_l0_zyx": center,
                               "start_coarse_zyx": start.tolist(), "fine_sha256": digest(fine),
                               "coarse_sha256": digest(coarse)})
                sample["regions"].append(result)
                best = result["scores"][0]
                assert best["kernel_zyx"] == ("mean",) * 3 and best["rounding"] == "rint"
                assert best["mae"] == 0, (name, region, level, best)
                print(name, region, level, best["kernel_zyx"], best["rounding"], best["mae"],
                      flush=True)
        if name in SURFACES:
            sample["surface"] = surface_check(uri, arrays, levels, SURFACES[name])
        results[name] = sample
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--v3", action="store_true", help="Verify the published shard copy")
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    samples = ({"paris4_20260310170716_sharded": (V3, SAMPLES["paris4_20260310170716"][1])}
               if args.v3 else SAMPLES)
    report = run(args.work, samples)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
