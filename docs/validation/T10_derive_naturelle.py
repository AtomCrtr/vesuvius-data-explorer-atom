"""T10: snapping of natural drift on every published segment of PHerc0814, selection rule fixed in advance.

Usage: python docs/validation/T10_derive_naturelle.py OUTPUT_DIR   (matplotlib required)

Rule (frozen before any run, docs/validation/T10-carte-alignement.md section 9):

- segments: every non-superseded segment of volume 20250804134230 (PHerc0814, 9.362 um, standard codec);
- map, snapping and new map with the defaults of ``vesuvius-qc carte --recaler`` (tile 8, reliability >= 3,
  smoothing 0.5, cap 50 um, target = the segment's usual offset);
- population: snapped tiles (non-zero field) with |drift| > 25 um before; drift after is measured against the
  reference of the map before;
- reported: count, share whose |drift| decreases, medians before / after, reliability medians before / after;
- figure: the population tile with the largest |drift| before (outcome-blind), two CT cross-sections and the
  flattened render of the tile and its neighbours, before / after.
"""

import json
import sys
from dataclasses import replace
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from T10_coupes import draw_section  # noqa: E402

from vesuvius_data_explorer.core.alignment import grid_normals, level_factors  # noqa: E402
from vesuvius_data_explorer.core.alignment_map import (  # noqa: E402
    DEFAULT_MAX_SHIFT_UM,
    alignment_map,
    field_on_grid,
    snap_field,
    snap_points,
)
from vesuvius_data_explorer.core.catalog import load_catalog  # noqa: E402
from vesuvius_data_explorer.core.chunkcache import DecodedChunks  # noqa: E402
from vesuvius_data_explorer.core.flatten import flatten  # noqa: E402
from vesuvius_data_explorer.core.tifxyz import load_tifxyz  # noqa: E402
from vesuvius_data_explorer.core.volume import open_levels  # noqa: E402

VOLUME = "20250804134230"
THRESHOLD_UM = 25.0

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
catalog = load_catalog()
volume = next(v for v in catalog.volumes
              if v.volume_id == VOLUME and v.codec == "standard" and v.uri.startswith("s3://"))
px = volume.pixel_size_um
arrays, levels = open_levels(volume.uri)
shapes = [level.shape for level in levels]
segments = sorted((s for s in catalog.segments if not s.superseded and s.target_volume_id == VOLUME),
                  key=lambda s: s.segment_id)

records, population, kept = [], [], {}
for segment in segments:
    record = {"segment": segment.segment_id}
    try:
        surface = load_tifxyz(segment.uri, max_bytes=512 * 2**20)
        before = alignment_map(surface, arrays, shapes, pixel_size_um=px)
        field = snap_field(before, max_shift=DEFAULT_MAX_SHIFT_UM / px)
        snapped = snap_points(surface.points, field_on_grid(field, before, surface.points.shape[:2]))
        after = alignment_map(replace(surface, points=snapped), arrays, shapes, pixel_size_um=px)
        drift_before = (before.offset - before.reference) * px
        drift_after = (after.offset - before.reference) * px
        with np.errstate(invalid="ignore"):
            selected = (field != 0) & (np.abs(drift_before) > THRESHOLD_UM)
        record.update(tiles_measured=int((before.points > 0).sum()), tiles_snapped=int((field != 0).sum()),
                      tiles_selected=int(selected.sum()))
        for r, c in zip(*np.nonzero(selected)):
            population.append({"segment": segment.segment_id, "tile": [int(r), int(c)],
                               "drift_before_um": float(drift_before[r, c]),
                               "drift_after_um": float(drift_after[r, c]),
                               "reliability_before": float(before.reliability[r, c]),
                               "reliability_after": float(after.reliability[r, c])})
        if selected.any():
            kept[segment.segment_id] = (surface, before, snapped)
    except Exception as exc:  # Recorded, never stops the run.
        record["error"] = f"{type(exc).__name__}: {exc}"
    records.append(record)
    print(json.dumps(record), flush=True)

b = np.array([abs(p["drift_before_um"]) for p in population])
a = np.array([abs(p["drift_after_um"]) for p in population])
finite = np.isfinite(a)
summary = {
    "volume": VOLUME, "segments": len(segments), "threshold_um": THRESHOLD_UM,
    "tiles": len(population), "tiles_measured_after": int(finite.sum()),
    "share_drift_decreased": float(np.mean(a[finite] < b[finite])) if finite.any() else None,
    "drift_abs_median_before_um": float(np.median(b)) if len(b) else None,
    "drift_abs_median_after_um": float(np.median(a[finite])) if finite.any() else None,
    "reliability_median_before": float(np.median([p["reliability_before"] for p in population]))
    if population else None,
    "reliability_median_after": float(np.nanmedian([p["reliability_after"] for p in population]))
    if population else None,
}
figure = max(population, key=lambda p: abs(p["drift_before_um"])) if population else None
summary["figure_tile"] = figure
(out / "t10-derive-naturelle.json").write_text(
    json.dumps({"summary": summary, "segments": records, "population": population}, indent=1) + "\n",
    encoding="utf-8")
print(json.dumps(summary, indent=1))

if figure:
    surface, before, snapped = kept[figure["segment"]]
    tile = tuple(figure["tile"])
    points, size = surface.points, before.tile * before.stride
    normals = grid_normals(points)
    factor = level_factors(shapes)[before.level]
    chunks = DecodedChunks(arrays[before.level])
    fig, axes = plt.subplots(2, 1, figsize=(9, 5.4), layout="constrained")
    draw_section(axes[0], points, normals, snapped, tile=tile, size=size, spacing=px, factor=factor,
                 chunks=chunks, axis="row")
    draw_section(axes[1], points.swapaxes(0, 1), normals.swapaxes(0, 1), snapped.swapaxes(0, 1),
                 tile=tile[::-1], size=size, spacing=px, factor=factor, chunks=chunks, axis="column")
    fig.suptitle(f"PHerc0814 • segment {figure['segment']} • tile {tile} • drift "
                 f"{figure['drift_before_um']:+.1f} → {figure['drift_after_um']:+.1f} µm")
    fig.savefig(out / f"t10-coupes-{figure['segment']}.png", dpi=140)

    # Flattened render of the tile and its neighbours (3 x 3 tiles), before / after.
    rows = slice(max(0, (tile[0] - 1) * size), (tile[0] + 2) * size)
    cols = slice(max(0, (tile[1] - 1) * size), (tile[1] + 2) * size)
    renders = [flatten(p[rows, cols], arrays, shapes, level=before.level, step_voxels=surface.step_voxels)
               for p in (points, snapped)]
    fig, axes = plt.subplots(1, 2, figsize=(9, 4.6), layout="constrained")
    lo, hi = np.nanpercentile(np.concatenate([r.ravel() for r in renders]), [1, 99])
    for ax, render, title in zip(axes, renders, ("Published", "Snapped")):
        ax.imshow(render, cmap="gray", vmin=lo, vmax=hi)
        ax.set_title(title)
        ax.axis("off")
    fig.suptitle(f"PHerc0814 • segment {figure['segment']} • tiles around {tile}, flattened")
    fig.savefig(out / f"t10-rendu-{figure['segment']}.png", dpi=140)
