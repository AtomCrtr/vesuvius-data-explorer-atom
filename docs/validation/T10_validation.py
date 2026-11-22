"""T10 validation: alignment map of published segments, imposed drift, snapping, renders.

Usage: python T10_validation.py OUTPUT_DIR

Environment: SEED (7), PER_CLASS (3), MIN_KB / MAX_KB (size of x.tif, to keep segments of a few
hundred tiles), DRIFT_UM (40: ramp imposed across the columns), TILE (8), EXCLUDE (comma-separated
segment ids never drawn, e.g. those of an earlier sample), SEGMENTS (segment:volume,... run
exactly these segments instead of drawing).

For each drawn segment (S3 volumes only, three resolution classes):

1. map of the published segment;
2. the same segment moved along its normals by a ramp of 0 to DRIFT_UM across its columns; the
   map must find the ramp: ``offset(ramp) - offset(published) = -ramp`` at each tile, within
   2 sampling steps, on reliable tiles;
3. snapping of the drifted segment, then a new map: residual drift relative to the published map;
4. snapping of the published segment: flattened renders before / after, texture measures, and
   the reliability of the map before / after (must not drop).
"""

import json
import os
import random
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

from vesuvius_data_explorer.core.alignment import grid_normals
from vesuvius_data_explorer.core.alignment_map import (
    alignment_map,
    field_on_grid,
    reliable_tiles,
    review_zones,
    snap_field,
    snap_points,
)
from vesuvius_data_explorer.core.catalog import load_catalog
from vesuvius_data_explorer.core.flatten import flatten, sharpness
from vesuvius_data_explorer.core.tifxyz import load_tifxyz
from vesuvius_data_explorer.core.volume import open_levels
from vesuvius_data_explorer.qc.carte import grey_png, render_crop

CLASSES = {"~8 µm": (7.0, 10.0), "~2,4 µm": (2.0, 2.5), "~1,1 µm": (1.0, 1.2)}
SEED = int(os.environ.get("SEED", "7"))
PER_CLASS = int(os.environ.get("PER_CLASS", "3"))
MIN_KB, MAX_KB = int(os.environ.get("MIN_KB", "40")), int(os.environ.get("MAX_KB", "400"))
DRIFT_UM = float(os.environ.get("DRIFT_UM", "40"))
TILE = int(os.environ.get("TILE", "8"))
EXCLUDE = set(filter(None, os.environ.get("EXCLUDE", "").split(",")))
# SEGMENTS=segment:volume,... replays a fixed sample: the catalogue grows, so a seed alone does not.
SEGMENTS = {tuple(item.split(":")) for item in os.environ.get("SEGMENTS", "").split(",") if item}

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
log = open(out / "progress.log", "a", buffering=1)
catalog = load_catalog()
volumes = {v.volume_id: v for v in catalog.volumes
           if v.codec == "standard" and v.uri.startswith("s3://")}


def size_kb(uri):
    import s3fs

    try:
        return s3fs.S3FileSystem(anon=True).size(uri.removeprefix("s3://") + "/x.tif") / 1024
    except OSError:
        return None


rng = random.Random(SEED)
drawn = []
for label, (low, high) in CLASSES.items():
    candidates = [s for s in catalog.segments if not s.superseded
                  and s.segment_id not in EXCLUDE and s.target_volume_id in volumes
                  and low <= (volumes[s.target_volume_id].pixel_size_um or 0) <= high]
    if SEGMENTS:  # Explicit list: no draw, no size filter.
        drawn += [(label, s) for s in candidates if (s.segment_id, s.target_volume_id) in SEGMENTS]
        continue
    rng.shuffle(candidates)
    picked = []
    for segment in candidates:
        if len(picked) == PER_CLASS:
            break
        if any(p.target_volume_id == segment.target_volume_id for p in picked):
            continue  # One segment per volume, for diversity.
        kb = size_kb(segment.uri)
        if kb is not None and MIN_KB <= kb <= MAX_KB:
            picked.append(segment)
    drawn += [(label, s) for s in picked]
    print(f"{label}: {[s.segment_id for s in picked]}", file=log)


def moved(surface, shift_grid):
    normals = np.nan_to_num(grid_normals(surface.points))
    return replace(surface, points=surface.points + shift_grid[..., None] * normals)


def tile_values(amap, grid, reliable):
    """Value of a grid field at the tile centres (mean over the tile's points)."""
    t = amap.tile
    rows, cols = amap.offset.shape
    out = np.full((rows, cols), np.nan)
    for r, c in zip(*np.nonzero(reliable)):
        out[r, c] = np.nanmean(grid[r * t:(r + 1) * t, c * t:(c + 1) * t])
    return out


results = []
for label, segment in drawn:
    volume = volumes[segment.target_volume_id]
    px = volume.pixel_size_um
    record = {"class": label, "segment": segment.segment_id, "volume": volume.volume_id,
              "pixel_size_um": px}
    try:
        started = time.time()
        arrays, levels = open_levels(volume.uri)
        shapes = [level.shape for level in levels]
        surface = load_tifxyz(segment.uri, max_bytes=512 * 2**20)
        record["grid"] = list(surface.points.shape[:2])
        base = alignment_map(surface, arrays, shapes, pixel_size_um=px, tile=TILE)
        step_um = float(base.offsets[1] - base.offsets[0]) * px
        reliable = reliable_tiles(base)
        record.update(level=base.level, step_um=step_um, seconds_map=round(time.time() - started),
                      voxels_read=base.voxels_read,
                      tiles={"measured": int((base.points > 0).sum()),
                             "reliable": int(reliable.sum())},
                      reference_um=None if base.reference is None else base.reference * px,
                      spacing_um=None if base.spacing is None else base.spacing * px,
                      zones=[{k: z[k] for k in ("type", "tuiles")} for z in
                             review_zones(base, pixel_size_um=px)])

        # 2. Imposed ramp, in voxels along the normals.
        cols = surface.points.shape[1]
        ramp = np.broadcast_to(DRIFT_UM / px * np.arange(cols)[None, :] / max(cols - 1, 1),
                               surface.points.shape[:2])
        drifted = moved(surface, ramp)
        dmap = alignment_map(drifted, arrays, shapes, pixel_size_um=px, tile=TILE)
        both = reliable & reliable_tiles(dmap)
        expected = -tile_values(base, ramp, both)
        found = dmap.offset - base.offset
        error_um = np.abs(found - expected)[both] * px
        record["ramp"] = {"tiles": int(both.sum()),
                          "within_2_steps": float(np.mean(error_um <= 2 * step_um))
                          if both.any() else None,
                          "error_median_um": float(np.median(error_um)) if both.any() else None}

        # 3. Snapping the drifted segment.
        field = snap_field(dmap, max_shift=50 / px)
        snapped = replace(drifted, points=snap_points(
            drifted.points, field_on_grid(field, dmap, drifted.points.shape[:2])))
        smap = alignment_map(snapped, arrays, shapes, pixel_size_um=px, tile=TILE)
        common = reliable & reliable_tiles(dmap) & reliable_tiles(smap)
        imposed = tile_values(base, ramp, common)[common]

        def slope(m):
            """Regression slope of the measured offset change against the imposed ramp:
            -1 when the ramp is fully seen, 0 when it has been removed."""
            change = (m.offset - base.offset)[common]
            return float(np.polyfit(imposed, change, 1)[0]) if common.sum() > 2 else None

        record["snap_drifted"] = {
            "tiles": int(common.sum()),
            "ramp_slope_before": slope(dmap), "ramp_slope_after": slope(smap),
            "drift_abs_median_before_um": float(np.median(np.abs(dmap.drift[common]))) * px
            if common.any() else None,
            "drift_abs_median_after_um": float(np.median(np.abs(smap.drift[common]))) * px
            if common.any() else None}

        # 4. Snapping the published segment; renders.
        field = snap_field(base, max_shift=50 / px)
        grid = field_on_grid(field, base, surface.points.shape[:2])
        snapped = replace(surface, points=snap_points(surface.points, grid))
        amap = alignment_map(snapped, arrays, shapes, pixel_size_um=px, tile=TILE)
        crop = render_crop(surface, base, base.level, shapes)
        render_before = flatten(surface.points[crop], arrays, shapes, level=base.level,
                                step_voxels=surface.step_voxels)
        render_after = flatten(snapped.points[crop], arrays, shapes, level=base.level,
                               step_voxels=surface.step_voxels)
        name = f"t10-{segment.segment_id}"
        (out / f"{name}-avant.png").write_bytes(grey_png(render_before))
        (out / f"{name}-apres.png").write_bytes(grey_png(render_after))
        valid = np.isfinite(surface.points).all(axis=2)
        snapped_reliable = reliable_tiles(amap)
        moved_tiles = field != 0
        span = base.tile * base.stride
        frozen = ~moved_tiles[np.arange(valid.shape[0])[:, None] // span,
                              np.arange(valid.shape[1])[None, :] // span]
        # Revised 2b (frozen 2026-11-22): frozen points bit-identical, moved tiles' reliability.
        steps = np.concatenate([np.abs(np.diff(grid, axis=a))[np.diff(valid, axis=a) == 0]
                                for a in (0, 1)]) * px
        record["snap_published_2b"] = {
            "moved_tiles": int(moved_tiles.sum()),
            "frozen_points_identical": bool(np.array_equal(snapped.points[frozen & valid],
                                                           surface.points[frozen & valid])),
            "moved_reliability_median_before": float(np.nanmedian(base.reliability[moved_tiles]))
            if moved_tiles.any() else None,
            "moved_reliability_median_after": float(np.nanmedian(amap.reliability[moved_tiles]))
            if moved_tiles.any() else None,
            "step_um_p95": float(np.percentile(steps, 95)) if steps.size else None,
            "step_um_max": float(steps.max()) if steps.size else None}
        record["snap_published"] = {
            "moved_median_um": float(np.median(np.abs(grid[valid]))) * px,
            "moved_max_um": float(np.max(np.abs(grid[valid]))) * px,
            "reliability_median_before": float(np.nanmedian(base.reliability)),
            "reliability_median_after": float(np.nanmedian(amap.reliability)),
            "drift_abs_median_before_um": float(np.median(np.abs(base.drift[reliable]))) * px
            if reliable.any() else None,
            "drift_abs_median_after_um": float(np.median(np.abs(amap.drift[snapped_reliable]))) * px
            if snapped_reliable.any() else None,
            "render_before": sharpness(render_before),
            "render_after": sharpness(render_after)}
        record["seconds"] = round(time.time() - started)
    except Exception as exc:  # Recorded, never stops the run.
        record["error"] = f"{type(exc).__name__}: {exc}"
    results.append(record)
    print(json.dumps(record, ensure_ascii=False), file=log)
    (out / "t10-validation.json").write_text(json.dumps(results, indent=2, ensure_ascii=False)
                                             + "\n", encoding="utf-8")
print("fin", file=log)
