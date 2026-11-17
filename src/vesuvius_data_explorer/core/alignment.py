"""Surface–volume alignment: mean intensity profile along the normals of a segment.

A papyrus sheet is denser, hence brighter, than the gap between sheets. Reading the volume along
the surface normals, from -D to +D voxels, on a few patches of the segment, and averaging gives a
profile whose brightest point near 0 is the sheet the segment follows: its offset estimates the
surface–sheet distance. Exploratory, see docs/tasks/T5.1-alignement-surface-volume.md:

- the profile repeats from one sheet to the next: a segment off by a whole sheet looks aligned;
- the measure is informational until calibrated on real segments.

Coordinates are level-0 voxels (z, y, x), like the rest of the core.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from .tifxyz import TifxyzSurface, in_volume

DEFAULT_HALF_RANGE_UM = 200.0
DEFAULT_HALF_RANGE_VOXELS = 24.0  # When the physical voxel size is unknown.
MAX_SAMPLING_UM = 10.0
# 12 patches of real segments read 7 to 23 Mi-voxels (T5.1 calibration); 8 Mi cut most to 4-7.
DEFAULT_MAX_VOXELS = 32 * 2**20


@dataclass(frozen=True)
class AlignmentProfile:
    offsets: np.ndarray  # (n,) level-0 voxels along the normal
    mean: np.ndarray  # (n,) mean intensity over every sampled point
    patch_profiles: np.ndarray  # (patches, n) mean intensity per patch
    patch_centers: np.ndarray  # (patches, 3) level-0 (z, y, x)
    level: int
    half_range: float  # level-0 voxels
    points: int
    voxels_read: int
    warnings: tuple[str, ...] = field(default=())


def grid_normals(points: np.ndarray) -> np.ndarray:
    """Unit normals of a (rows, cols, 3) grid by central differences; NaN where undefined."""
    with np.errstate(invalid="ignore", divide="ignore"):
        normals = np.cross(np.gradient(points, axis=1), np.gradient(points, axis=0))
        normals /= np.linalg.norm(normals, axis=2, keepdims=True)
    return normals


def level_factors(shapes) -> np.ndarray:
    """(levels, 3) ratio of the level-0 shape to each level's shape, per axis."""
    base = np.asarray(shapes[0], dtype=float)
    return np.array([base / np.asarray(shape, dtype=float) for shape in shapes])


def choose_level(shapes, pixel_size_um: float | None, max_um: float = MAX_SAMPLING_UM) -> int:
    """Coarsest level whose voxel is at most ``max_um``; level 0 when the size is unknown."""
    if pixel_size_um is None or pixel_size_um <= 0:
        return 0
    factors = level_factors(shapes).max(axis=1)
    fitting = [k for k, factor in enumerate(factors) if factor * pixel_size_um <= max_um]
    return max(fitting) if fitting else 0


def half_range_voxels(pixel_size_um: float | None,
                      half_range_um: float = DEFAULT_HALF_RANGE_UM) -> float:
    if pixel_size_um is None or pixel_size_um <= 0:
        return DEFAULT_HALF_RANGE_VOXELS
    return half_range_um / pixel_size_um


def shift_surface(surface: TifxyzSurface, offset: float) -> TifxyzSurface:
    """The same segment moved by ``offset`` level-0 voxels along its normals (calibration)."""
    return replace(surface, points=surface.points + offset * grid_normals(surface.points))


def normal_profiles(surface: TifxyzSurface, arrays, shapes, *, pixel_size_um=None,
                    half_range_um=DEFAULT_HALF_RANGE_UM, patches=12, patch_size=6, seed=0,
                    max_voxels=DEFAULT_MAX_VOXELS, patch_shifts=None) -> AlignmentProfile:
    """Mean intensity profiles along the normals of ``patches`` random patches of the segment.

    ``arrays`` are the volume levels (NumPy, Zarr or Dask), ``shapes`` their (z, y, x) shapes.
    Only patches whose points are all valid, with a normal, and inside the volume are used. A box
    around each patch is read at the chosen level, within ``max_voxels`` in total; the profile is
    sampled every voxel of that level by trilinear interpolation. ``patch_shifts`` (one offset
    per drawn patch) is for calibration only: it moves each patch along its normals.
    """
    from scipy import ndimage

    if isinstance(max_voxels, bool) or not isinstance(max_voxels, int) or max_voxels < 1:
        raise ValueError("Le budget de voxels doit être un entier strictement positif.")
    level = choose_level(shapes, pixel_size_um)
    factor = level_factors(shapes)[level]
    half = half_range_voxels(pixel_size_um, half_range_um)
    step = float(factor.mean())
    count = int(np.floor(half / step))
    if count < 2:
        raise ValueError("Portée du profil trop courte pour le niveau choisi.")
    offsets = step * np.arange(-count, count + 1)

    points = surface.points
    normals = grid_normals(points)
    usable = in_volume(points, shapes[0]) & np.isfinite(normals).all(axis=2)
    rows, cols = usable.shape
    candidates = [(r, c) for r in range(0, rows - patch_size + 1, patch_size)
                  for c in range(0, cols - patch_size + 1, patch_size)
                  if usable[r:r + patch_size, c:c + patch_size].all()]
    if not candidates:
        raise ValueError(f"Aucun patch de {patch_size} × {patch_size} points valides dans le "
                         "volume : profil d'alignement impossible.")
    rng = np.random.default_rng(seed)
    drawn = [candidates[i] for i in rng.choice(len(candidates), size=min(patches, len(candidates)),
                                               replace=False)]
    warnings = []
    if len(drawn) < patches:
        warnings.append(f"{len(drawn)} patch(s) utilisable(s) sur {patches} demandés.")

    array, level_shape = arrays[level], np.asarray(shapes[level])
    profiles, centers, voxels_read, used_points = [], [], 0, 0
    for index, (r, c) in enumerate(drawn):
        p = points[r:r + patch_size, c:c + patch_size].reshape(-1, 3)
        n = normals[r:r + patch_size, c:c + patch_size].reshape(-1, 3)
        if patch_shifts is not None:
            p = p + patch_shifts[index] * n
        samples = p[:, None, :] + offsets[None, :, None] * n[:, None, :]
        # Level-0 voxel centre c0 maps to (c0 + 0.5) / factor - 0.5 on level k.
        coords = ((samples + 0.5) / factor - 0.5).reshape(-1, 3)
        low = np.maximum(np.floor(coords.min(axis=0)).astype(int) - 1, 0)
        high = np.minimum(np.ceil(coords.max(axis=0)).astype(int) + 2, level_shape)
        if np.any(high <= low):
            continue  # The whole profile lies outside the volume.
        size = int(np.prod(high - low))
        if voxels_read + size > max_voxels:
            warnings.append(f"Budget : {len(profiles)} patch(s) lu(s) sur {len(drawn)} "
                            f"({max_voxels} voxels au plus).")
            break
        box = np.asarray(array[low[0]:high[0], low[1]:high[1], low[2]:high[2]], dtype=np.float32)
        voxels_read += size
        values = ndimage.map_coordinates(box, (coords - low).T, order=1, mode="nearest")
        profiles.append(values.reshape(len(p), len(offsets)).mean(axis=0))
        centers.append(p.mean(axis=0))
        used_points += len(p)
    if not profiles:
        raise ValueError("Budget de voxels insuffisant pour lire un seul patch.")
    patch_profiles = np.array(profiles)
    return AlignmentProfile(offsets, patch_profiles.mean(axis=0), patch_profiles,
                            np.array(centers), level, half, used_points, voxels_read,
                            tuple(warnings))


def _peak(offsets: np.ndarray, mean: np.ndarray, half: float) -> int:
    """Index of the brightest point within ±half/2: the sheet followed, not its neighbours."""
    window = np.flatnonzero(np.abs(offsets) <= half / 2)
    return int(window[np.argmax(mean[window])])


def alignment_metrics(profile: AlignmentProfile, *, resamples=200, seed=0) -> dict:
    """Peak offset, prominence, bootstrap spread and (informational) sharpest-edge offset."""
    offsets, mean = profile.offsets, profile.mean
    peak = _peak(offsets, mean, profile.half_range)
    spread = float(np.std(profile.patch_profiles[:, peak]))
    prominence = float((mean[peak] - mean.mean()) / spread) if spread > 0 else None
    rng = np.random.default_rng(seed)
    count = len(profile.patch_profiles)
    estimates = [offsets[_peak(offsets, profile.patch_profiles[rng.integers(count, size=count)]
                               .mean(axis=0), profile.half_range)] for _ in range(resamples)]
    low, high = (float(v) for v in np.percentile(estimates, [25, 75]))
    edge = int(np.argmax(np.abs(np.gradient(mean, offsets))))
    return {
        "peak_offset": float(offsets[peak]),
        "peak_prominence": prominence,
        "bootstrap_iqr": [low, high],
        "bootstrap_width": high - low,
        "edge_offset": float(offsets[edge]),
        "level": profile.level,
        "patches": count,
        "points": profile.points,
        "voxels_read": profile.voxels_read,
        "half_range": profile.half_range,
        "offsets": [float(v) for v in offsets],
        "mean_profile": [float(v) for v in mean],
    }
