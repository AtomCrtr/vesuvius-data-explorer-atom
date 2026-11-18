"""Pure coordinate helpers linking QC locations, napari world coordinates and views.

No napari or Qt imports. Conventions:

- axes are (z, y, x) everywhere;
- ``levels`` is ``volume_summary(...)["levels"]`` (finest first), as stored in the
  napari layer metadata; level ``k`` is mapped to level 0 by the shape ratio
  ``shape_0 / shape_k`` on each axis, which works with or without OME scales;
- napari draws level-0 voxel ``i`` of a layer with scale ``s`` centred on ``i * s``,
  so it covers the world interval ``[(i - 0.5) * s, (i + 0.5) * s]``.
"""

from dataclasses import dataclass
from math import ceil, floor
from typing import Any, Mapping, Sequence

import numpy as np

from ..core.volume import slice_stats

AXES = ("z", "y", "x")


@dataclass(frozen=True)
class WorldBox:
    """A rectangle lying in one plane, in napari world coordinates (z, y, x)."""

    axis: str                      # plane axis: "z", "y" or "x"
    plane: float                   # world coordinate of the plane on that axis
    low: tuple[float, float]       # world corner on the two in-plane axes, (z, y, x) order
    high: tuple[float, float]

    @property
    def in_plane_axes(self) -> tuple[int, int]:
        return _in_plane(AXES.index(self.axis))

    @property
    def center(self) -> tuple[float, float]:
        return tuple((lo + hi) / 2 for lo, hi in zip(self.low, self.high))

    def rectangle(self) -> list[list[float]]:
        """Four 3D vertices (z, y, x) for a napari Shapes rectangle."""
        plane_index = AXES.index(self.axis)
        a, b = self.in_plane_axes
        vertices = []
        for va, vb in ((self.low[0], self.low[1]), (self.low[0], self.high[1]),
                       (self.high[0], self.high[1]), (self.high[0], self.low[1])):
            point = [0.0, 0.0, 0.0]
            point[plane_index], point[a], point[b] = self.plane, va, vb
            vertices.append(point)
        return vertices


def _in_plane(plane_index: int) -> tuple[int, int]:
    return tuple(i for i in range(3) if i != plane_index)


def _level(levels: Sequence[Mapping[str, Any]], key: str) -> Mapping[str, Any]:
    for level in levels:
        if level["key"] == key:
            return level
    raise KeyError(f"Niveau absent du volume : {key}")


def _ratios(levels, key) -> tuple[float, float, float]:
    finest = levels[0]["shape"]
    shape = _level(levels, key)["shape"]
    return tuple(f / s for f, s in zip(finest, shape))


def location_to_world(location, levels, layer_scale) -> WorldBox:
    """Convert a QC ``Location`` (or its dict form) on level ``k`` to a world rectangle."""
    loc = location if isinstance(location, Mapping) else location.to_dict()
    if loc["axis"] not in AXES:
        raise ValueError("Axe attendu : z, y ou x.")
    plane_index = AXES.index(loc["axis"])
    ratios = _ratios(levels, loc["level"])
    finest = levels[0]["shape"]
    scale = tuple(float(s) for s in layer_scale)
    # Plane: centre of the level-k voxel, as a level-0 index napari can display.
    r = ratios[plane_index]
    level0 = floor(loc["index"] * r + (r - 1) / 2)
    level0 = min(max(level0, 0), finest[plane_index] - 1)
    plane = level0 * scale[plane_index]
    low, high = [], []
    for axis, start, size in zip(_in_plane(plane_index), loc["origin"], loc["size"]):
        r, s, n = ratios[axis], scale[axis], finest[axis]
        first = start * r
        last = min((start + size) * r, n)
        low.append((first - 0.5) * s)
        high.append((last - 0.5) * s)
    return WorldBox(loc["axis"], plane, tuple(low), tuple(high))


def visible_region(levels, layer_scale, plane_axis: str, plane_world: float,
                   view_low, view_high, max_side: int = 512) -> dict:
    """Bounded ``read_slice`` arguments for the region shown in a 2D view.

    ``view_low`` / ``view_high`` are the world corners of the view on the two in-plane
    axes, in (z, y, x) order. The finest level whose visible region fits in
    ``max_side × max_side`` is chosen; if none fits, the central part of the coarsest level,
    at most ``max_side`` on each axis, is used. The region is the visible **rectangle**:
    ``width_a`` × ``width_b`` (``width`` is the larger side, kept for compatibility).
    """
    if not 1 <= max_side <= 512:
        raise ValueError("Largeur de fenêtre autorisée : 1 à 512 pixels.")
    plane_index = AXES.index(plane_axis)
    scale = tuple(float(s) for s in layer_scale)
    in_plane = _in_plane(plane_index)

    def to_level(world, axis, ratio):
        # Inverse of the napari mapping, then level-0 -> level-k voxel coordinate.
        return (world / scale[axis] + 0.5) / ratio - 0.5

    choice = None
    for level in levels:
        ratios = _ratios(levels, level["key"])
        shape = level["shape"]
        bounds = []
        for axis, lo, hi in zip(in_plane, view_low, view_high):
            first = max(0, floor(to_level(min(lo, hi), axis, ratios[axis]) + 0.5))
            last = min(shape[axis], ceil(to_level(max(lo, hi), axis, ratios[axis]) + 0.5))
            bounds.append((first, max(last, first + 1)))
        width = max(last - first for first, last in bounds)
        choice = (level, ratios, bounds, width)
        if width <= max_side:
            break
    level, ratios, bounds, width = choice
    shape = level["shape"]
    if width > max_side:
        # Keep each side within max_side, centred on the view, without squaring it.
        centred = []
        for axis, (first, last) in zip(in_plane, bounds):
            side = min(last - first, max_side)
            middle = (first + last) // 2
            start = max(0, min(middle - side // 2, shape[axis] - side))
            centred.append((start, start + side))
        bounds = centred
    index = round(to_level(plane_world, plane_index, ratios[plane_index]))
    index = min(max(index, 0), shape[plane_index] - 1)
    starts = [min(first, shape[axis] - 1) for axis, (first, _) in zip(in_plane, bounds)]
    sides = [int(max(1, min(last - first, max_side))) for first, last in bounds]
    return {
        "level": level["key"],
        "axis": plane_axis,
        "index": int(index),
        "start_a": int(starts[0]),
        "start_b": int(starts[1]),
        "width_a": sides[0],
        "width_b": sides[1],
        "width": max(sides),
    }


def view_metrics(data: np.ndarray, background_value: float = 0.0,
                 background_enabled: bool = True) -> dict:
    """``slice_stats`` of a view, plus its background percentage (rule of T3)."""
    stats = slice_stats(data)
    if background_enabled:
        stats["background_pct"] = float(100 * np.count_nonzero(data == background_value) / data.size)
    else:
        stats["background_pct"] = None
    return stats
