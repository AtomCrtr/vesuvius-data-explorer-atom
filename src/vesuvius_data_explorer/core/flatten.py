"""Flattened rendering of a tifxyz segment: the volume sampled on the surface (T10 visual proof).

The tifxyz grid has one point every ~20 level-0 voxels; it is interpolated bilinearly to about one
pixel per voxel of the chosen level, then the volume is sampled there (and optionally a few
voxels along the normal, averaged). On a well-placed surface, papyrus fibres are visible.
"""

from __future__ import annotations

import numpy as np

from .alignment import grid_normals, level_factors

DEFAULT_RENDER_MAX_PIXELS = 4 * 2**20
DEFAULT_RENDER_MAX_VOXELS = 512 * 2**20


def upsample_grid(points: np.ndarray, factor: int) -> np.ndarray:
    """(rows, cols, 3) grid interpolated bilinearly ``factor`` times; NaN where a corner is NaN."""
    from scipy import ndimage

    rows, cols = points.shape[:2]
    r = np.linspace(0, rows - 1, (rows - 1) * factor + 1)
    c = np.linspace(0, cols - 1, (cols - 1) * factor + 1)
    rr, cc = np.meshgrid(r, c, indexing="ij")
    valid = np.isfinite(points).all(axis=2).astype(float)
    filled = np.nan_to_num(points)
    out = np.stack([ndimage.map_coordinates(filled[..., k], [rr, cc], order=1)
                    for k in range(3)], axis=-1)
    weight = ndimage.map_coordinates(valid, [rr, cc], order=1)
    out[weight < 1 - 1e-6] = np.nan
    return out


def flatten(points: np.ndarray, arrays, shapes, *, level: int, step_voxels: float,
            normal_offsets=(0.0,), max_pixels=DEFAULT_RENDER_MAX_PIXELS,
            max_voxels=DEFAULT_RENDER_MAX_VOXELS) -> np.ndarray:
    """Flattened image of a grid crop ``points`` (rows, cols, 3), NaN outside the segment.

    ``step_voxels`` is the level-0 distance between grid points; the grid is upsampled to about one
    pixel per voxel of ``level``. ``normal_offsets`` (level-0 voxels) are averaged.
    """
    from scipy import ndimage

    factor = level_factors(shapes)[level]
    up = max(1, int(round(step_voxels / float(factor.mean()))))
    rows, cols = points.shape[:2]
    if ((rows - 1) * up + 1) * ((cols - 1) * up + 1) > max_pixels:
        raise ValueError("Rendu trop grand : réduire la zone rendue.")
    normals = grid_normals(points)
    dense = upsample_grid(points, up)
    dense_normals = upsample_grid(np.where(np.isfinite(normals), normals, np.nan), up)
    norm = np.linalg.norm(dense_normals, axis=2, keepdims=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        dense_normals = dense_normals / norm
    valid = np.isfinite(dense).all(axis=2) & np.isfinite(dense_normals).all(axis=2)
    image = np.full(dense.shape[:2], np.nan, dtype=np.float32)
    if not valid.any():
        return image
    p, n = dense[valid], dense_normals[valid]
    offsets = np.asarray(normal_offsets, dtype=float)
    coords = ((p[:, None, :] + offsets[None, :, None] * n[:, None, :] + 0.5) / factor
              - 0.5).reshape(-1, 3)
    array = arrays[level]
    if not isinstance(array, np.ndarray):  # Only the chunks the surface crosses are read.
        from .chunkcache import DecodedChunks, sample_trilinear

        values = sample_trilinear(DecodedChunks(array), coords)
    else:
        level_shape = np.asarray(shapes[level])
        low = np.maximum(np.floor(coords.min(axis=0)).astype(int) - 1, 0)
        high = np.minimum(np.ceil(coords.max(axis=0)).astype(int) + 2, level_shape)
        if np.any(high <= low):
            return image
        if int(np.prod(high - low)) > max_voxels:
            raise ValueError("Zone rendue trop grande pour le budget de voxels.")
        box = np.asarray(array[low[0]:high[0], low[1]:high[1], low[2]:high[2]],
                         dtype=np.float32)
        values = ndimage.map_coordinates(box, (coords - low).T, order=1, mode="nearest")
    image[valid] = values.reshape(len(p), len(offsets)).mean(axis=1)
    return image


def sharpness(image: np.ndarray) -> dict:
    """Texture measures of a flattened render, over its valid pixels.

    ``contraste``: band-pass energy (difference of Gaussians, σ = 1 and 4 pixels) divided by the
    mean intensity: fibres are fine structure, noise is mostly finer, background is coarser.
    ``moyenne``: mean intensity (a surface on its sheet is brighter than one in the gap).
    """
    from scipy import ndimage

    valid = np.isfinite(image)
    if valid.sum() < 64:
        return {"moyenne": None, "contraste": None, "pixels": int(valid.sum())}
    filled = np.where(valid, image, float(np.nanmean(image)))
    band = ndimage.gaussian_filter(filled, 1.0) - ndimage.gaussian_filter(filled, 4.0)
    inner = ndimage.binary_erosion(valid, iterations=4)
    if inner.sum() < 64:
        inner = valid
    mean = float(image[valid].mean())
    return {"moyenne": mean,
            "contraste": float(band[inner].std() / mean) if mean else None,
            "pixels": int(valid.sum())}
