"""T5.1 calibration: alignment profile of published segments vs imposed and incoherent shifts.

Usage: python T5.1_calibration.py SEGMENT_SIZES_JSON OUTPUT_JSON [CATALOG_CACHE_DIR]

Environment: SEED (11 for the first sample), PER_CLASS (7), PATCHES (36), EXCLUDE (comma-separated
result files whose segments must not be drawn again: the second sample excludes the first one).

SEGMENT_SIZES_JSON maps catalogue paths of tifxyz-transformed copies to the size of their x.tif
(only segments under 64 MiB per grid are drawn). For each drawn segment the profile is measured
on the published segment, after imposed shifts of +-25 and +-50 µm along the normals, and with
an independent random shift per patch (incoherent control, +-50 µm).
"""

import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from vesuvius_data_explorer.core.alignment import alignment_metrics, normal_profiles, shift_surface
from vesuvius_data_explorer.core.catalog import load_catalog
from vesuvius_data_explorer.core.tifxyz import load_tifxyz
from vesuvius_data_explorer.core.volume import open_levels

SHIFTS_UM = (0.0, 25.0, -25.0, 50.0, -50.0)
# Large enough for every requested patch (the 8 Mi-voxel default cut most profiles to 4-7).
MAX_VOXELS = int(os.environ.get("MAX_VOXELS", str(128 * 2**20)))
PATCHES = int(os.environ.get("PATCHES", "36"))  # 12 for the first calibration run
CLASSES = {"~8 µm": (7.0, 10.0), "~2,4 µm": (2.0, 2.5), "~1,1 µm": (1.0, 1.2)}
PER_CLASS = int(os.environ.get("PER_CLASS", "7"))
SEED = int(os.environ.get("SEED", "11"))
EXCLUDED = {(row["segment"], row["volume"])
            for path in filter(None, os.environ.get("EXCLUDE", "").split(","))
            for row in json.load(open(path))}

sizes = json.load(open(sys.argv[1]))
catalog = load_catalog(cache_dir=sys.argv[3]) if len(sys.argv) > 3 else load_catalog()
volumes = {v.volume_id: v for v in catalog.volumes if v.codec == "standard"}
random.seed(SEED)
drawn = []
for name, (low, high) in CLASSES.items():
    pool = [s for s in catalog.segments if not s.superseded
            and s.target_volume_id in volumes
            and low <= (volumes[s.target_volume_id].pixel_size_um or 0) < high
            and sizes.get(s.uri.split("open-data/", 1)[-1] + "/", 1e12) < 64 * 2**20
            and (s.segment_id, s.target_volume_id) not in EXCLUDED]
    drawn += [(name, s) for s in random.sample(pool, min(PER_CLASS, len(pool)))]
opened = {}


def measure(item):
    name, segment = item
    volume = volumes[segment.target_volume_id]
    started = time.time()
    try:
        if volume.uri not in opened:
            arrays, levels = open_levels(volume.uri)  # Zarr reads and local cache (T6)
            opened[volume.uri] = (arrays, [level.shape for level in levels])
        arrays, shapes = opened[volume.uri]
        surface = load_tifxyz(segment.uri)
        pixel = volume.pixel_size_um
        rows = {}
        for shift_um in SHIFTS_UM:
            shifted = shift_surface(surface, shift_um / pixel) if shift_um else surface
            rows[f"{shift_um:+g}"] = alignment_metrics(
                normal_profiles(shifted, arrays, shapes, pixel_size_um=pixel,
                                max_voxels=MAX_VOXELS, patches=PATCHES))
        rng = np.random.default_rng(0)
        rows["random"] = alignment_metrics(normal_profiles(
            surface, arrays, shapes, pixel_size_um=pixel, max_voxels=MAX_VOXELS,
            patches=PATCHES, patch_shifts=rng.uniform(-50, 50, PATCHES) / pixel))
        keep = ("peak_offset", "peak_prominence", "bootstrap_width", "edge_offset", "level",
                "patches", "voxels_read")
        return {"class": name, "sample": segment.sample_id, "segment": segment.segment_id,
                "volume": volume.volume_id, "pixel_size_um": pixel,
                "step_voxels": float(np.diff(rows["+0"]["offsets"])[0]),
                "seconds": round(time.time() - started, 1),
                "published_profile": rows["+0"]["mean_profile"],
                "offsets": rows["+0"]["offsets"],
                "conditions": {k: {f: v[f] for f in keep} for k, v in rows.items()}}
    except Exception as error:  # Recorded, not hidden: the validation counts failures.
        return {"class": name, "segment": segment.segment_id, "volume": volume.volume_id,
                "error": f"{type(error).__name__}: {error}"[:300]}


with ThreadPoolExecutor(6) as pool:
    results = list(pool.map(measure, drawn))
json.dump(results, open(sys.argv[2], "w"), indent=1)
for row in results:
    if "error" in row:
        print(row["class"], row["segment"], "ERROR", row["error"])
        continue
    c = row["conditions"]
    print(row["class"], row["segment"], row["pixel_size_um"], "step", row["step_voxels"],
          {k: (v["peak_offset"], v["peak_prominence"] and round(v["peak_prominence"], 2),
               v["bootstrap_width"]) for k, v in c.items()}, row["seconds"], "s")
