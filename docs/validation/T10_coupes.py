"""Two CT cross-sections around the natural drift on PHerc0814, tile (5, 17).

With matplotlib installed: python docs/validation/T10_coupes.py output.png
The cyan trace is the published surface; orange is the corrected trace projected onto
the same curved section, sampled along the normals of the published surface.
"""

import argparse
from dataclasses import replace

import matplotlib.pyplot as plt
import numpy as np

from vesuvius_data_explorer.core.alignment import grid_normals, level_factors
from vesuvius_data_explorer.core.alignment_map import (
    DEFAULT_MAX_SHIFT_UM,
    alignment_map,
    field_on_grid,
    snap_field,
    snap_points,
)
from vesuvius_data_explorer.core.catalog import load_catalog
from vesuvius_data_explorer.core.chunkcache import DecodedChunks, sample_trilinear
from vesuvius_data_explorer.core.tifxyz import load_tifxyz
from vesuvius_data_explorer.core.volume import open_levels

SEGMENT = "20260226110425"
VOLUME = "20250804134230"
TILE = (5, 17)


def interpolate_row(grid, row, columns):
    indices = np.arange(grid.shape[1])
    return np.column_stack([np.interp(columns, indices, values) for values in grid[row].T])


def draw_section(ax, points, normals, snapped, *, tile, size, spacing, factor, chunks, axis):
    fixed, varying = tile
    row = fixed * size + size // 2
    first = max(0, (varying - 1) * size)
    last = min(points.shape[1] - 1, (varying + 2) * size - 1)
    columns = np.linspace(first, last, (last - first) * 16 + 1)
    line = interpolate_row(points, row, columns)
    normal = interpolate_row(normals, row, columns)
    normal /= np.linalg.norm(normal, axis=1, keepdims=True)
    valid = np.isfinite(line).all(axis=1) & np.isfinite(normal).all(axis=1)

    offsets = np.linspace(-110, 110, 101)
    coords = line[valid] + offsets[:, None, None] / spacing * normal[valid]
    coords = (coords + 0.5) / factor - 0.5
    image = np.full((len(offsets), len(columns)), np.nan)
    image[:, valid] = sample_trilinear(chunks, coords.reshape(-1, 3)).reshape(len(offsets), -1)
    ax.imshow(image, extent=(first, last, offsets[0], offsets[-1]), origin="lower",
              cmap="gray", aspect="auto")

    corrected = interpolate_row(snapped, row, columns)
    displacement = (corrected - line) * spacing
    projection = np.sum(displacement * normal, axis=1)
    ax.plot(columns, np.where(valid, 0, np.nan), color="#15e2ff", linestyle="--",
            linewidth=1.5, label="Published")
    ax.plot(columns, projection, color="#ffb629", linewidth=1.75, label="Corrected")
    for edge in (varying * size - 0.5, (varying + 1) * size - 0.5):
        ax.axvline(edge, color="white", alpha=0.65, linewidth=1)
    ax.set(xlabel=f"tifxyz grid position ({axis} {row})", ylabel="Normal offset (µm)")
    ax.legend(loc="upper right")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", help="Output PNG")
    args = parser.parse_args()
    catalog = load_catalog()
    segment = next(s for s in catalog.segments if not s.superseded and s.segment_id == SEGMENT
                   and s.target_volume_id == VOLUME)
    volume = next(v for v in catalog.volumes if v.volume_id == VOLUME)
    spacing = volume.pixel_size_um
    arrays, levels = open_levels(volume.uri)
    shapes = [level.shape for level in levels]
    surface = load_tifxyz(segment.uri)
    before = alignment_map(surface, arrays, shapes, pixel_size_um=spacing)
    field = snap_field(before, max_shift=DEFAULT_MAX_SHIFT_UM / spacing)
    grid = field_on_grid(field, before, surface.points.shape[:2])
    snapped = snap_points(surface.points, grid)
    rows, cols = np.ogrid[:grid.shape[0], :grid.shape[1]]
    span = before.tile * before.stride
    frozen = (field == 0)[rows // span, cols // span] & np.isfinite(surface.points).all(axis=2)
    np.testing.assert_array_equal(snapped[frozen], surface.points[frozen])
    print(f"{int(frozen.sum())} valid points on excluded tiles held fixed.")

    after = alignment_map(replace(surface, points=snapped), arrays, shapes, pixel_size_um=spacing)
    print(f"Tile {TILE}, drift relative to the original reference: "
          f"{(before.offset[TILE] - before.reference) * spacing:+.2f} → "
          f"{(after.offset[TILE] - before.reference) * spacing:+.2f} µm. "
          f"Reliability: {before.reliability[TILE]:.2f} → {after.reliability[TILE]:.2f}.")

    points = surface.points
    normals = grid_normals(points)
    factor = level_factors(shapes)[before.level]
    chunks = DecodedChunks(arrays[before.level])
    fig, axes = plt.subplots(2, 1, figsize=(9, 5.4), layout="constrained")
    draw_section(axes[0], points, normals, snapped, tile=TILE, size=before.tile,
                 spacing=spacing, factor=factor, chunks=chunks, axis="row")
    draw_section(axes[1], points.swapaxes(0, 1), normals.swapaxes(0, 1), snapped.swapaxes(0, 1),
                 tile=TILE[::-1], size=before.tile, spacing=spacing, factor=factor,
                 chunks=chunks, axis="column")
    fig.suptitle(f"PHerc0814  •  Segment {SEGMENT}  •  Tile {TILE}")
    fig.savefig(args.output, dpi=140)


if __name__ == "__main__":
    main()
