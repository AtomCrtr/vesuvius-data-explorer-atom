"""Dense alignment map of a tifxyz segment (T10): offset to its sheet, tile by tile.

The segment grid is cut into tiles of ``tile`` × ``tile`` points. For each tile, the volume is
read along the normals of its points (as in :mod:`.alignment`) and the mean profile gives the
offset of the nearest bright sheet, with a reliability and an uncertainty. On top of that map:

- **reference**: the segment's usual offset (published segments sit about 10 µm off the bright
  centre of their sheet, see docs/investigations/I2-etat-de-l-art-2026.md, section 4). Drift is
  measured relative to it, so a correction keeps the face the segment follows;
- **sheet spacing** ``Δ``, from the autocorrelation of the segment's mean profile;
- **phase**: drift wrapped to ``[-Δ/2, Δ/2)``. Quality-guided unwrapping gives the drift across the
  whole segment and a relative sheet index; **residues** on 2 × 2 loops of tiles and **wrap edges**
  between neighbours mark sheet switches.

Limits: a switch abrupt enough to fit inside one tile leaves both sides aligned on *a* sheet and is
seen only as an unreliable tile, not as a switch. Coordinates are level-0 voxels (z, y, x).
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field

import numpy as np

from .alignment import (
    DEFAULT_HALF_RANGE_UM,
    choose_level,
    grid_normals,
    half_range_voxels,
    level_factors,
)
from .tifxyz import TifxyzSurface, in_volume

DEFAULT_TILE = 8
DEFAULT_MIN_POINTS = 16  # Usable points a tile needs to be measured.
DEFAULT_MAP_MAX_VOXELS = 4 * 2**30


@dataclass(frozen=True)
class AlignmentMap:
    tile: int  # grid points per tile side, in the loaded (possibly decimated) grid
    stride: int  # decimation of the loaded grid relative to the tifxyz files
    offsets: np.ndarray  # (n,) sample positions along the normal, level-0 voxels
    profiles: np.ndarray  # (tr, tc, n) mean profile per tile, NaN where not measured
    points: np.ndarray  # (tr, tc) usable points per tile
    centers: np.ndarray  # (tr, tc, 3) mean position of the usable points, NaN if none
    offset: np.ndarray  # (tr, tc) nearest sheet offset, level-0 voxels, NaN if undetermined
    reliability: np.ndarray  # (tr, tc) peak height / standard error of the tile mean
    uncertainty: np.ndarray  # (tr, tc) standard deviation of ``offset`` (delta method)
    reference: float | None  # segment's usual offset
    spacing: float | None  # sheet spacing Δ, level-0 voxels
    drift: np.ndarray  # (tr, tc) offset - reference, wrapped to [-Δ/2, Δ/2) when Δ is known
    unwrapped: np.ndarray  # (tr, tc) drift unwrapped across the segment (NaN without Δ)
    sheet: np.ndarray  # (tr, tc) relative sheet index (0 = majority), -999 where unknown
    residues: np.ndarray  # (tr-1, tc-1) +1 / -1 on 2 x 2 loops that do not close, else 0
    wraps: list = field(default_factory=list)  # [((r, c), (r2, c2)), ...] neighbours > Δ/2 apart
    level: int = 0
    half_range: float = 0.0
    voxels_read: int = 0
    warnings: tuple[str, ...] = ()


def refine_peak(offsets: np.ndarray, values: np.ndarray, index: int) -> float:
    """Sub-sample position of a local maximum by a parabola through its two neighbours."""
    left, centre, right = values[index - 1], values[index], values[index + 1]
    curvature = left - 2 * centre + right
    if not curvature < 0:
        return float(offsets[index])
    shift = 0.5 * (left - right) / curvature
    step = float(offsets[index + 1] - offsets[index])
    return float(offsets[index] + np.clip(shift, -0.5, 0.5) * step)


def nearest_peak(offsets: np.ndarray, values: np.ndarray, center: float = 0.0,
                 window: float | None = None) -> int | None:
    """Index of the local maximum nearest to ``center``, brighter than the profile's median.

    Unlike the brightest point of a window, this does not jump to a neighbouring sheet when sheets
    are closer than the window. A maximum on the first or last sample is not a peak. ``window``
    limits the search to ``|offset - center| <= window``. None when there is no such maximum.
    """
    values = np.asarray(values, dtype=float)
    if len(values) < 3 or not np.isfinite(values).all():
        return None
    inner = np.arange(1, len(values) - 1)
    is_max = (values[inner] >= values[inner - 1]) & (values[inner] > values[inner + 1])
    is_max &= values[inner] > np.median(values)
    candidates = inner[is_max]
    if window is not None:
        candidates = candidates[np.abs(offsets[candidates] - center) <= window]
    if len(candidates) == 0:
        return None
    return int(candidates[np.argmin(np.abs(offsets[candidates] - center))])


def peak_uncertainty(offsets: np.ndarray, values: np.ndarray, variances: np.ndarray,
                     index: int) -> float:
    """Standard deviation of the parabolic peak position, propagated from the sample variances.

    Delta method on ``x0 = x_i + h (y- - y+) / (2 (y- - 2 y0 + y+))``; independent samples. It is
    the local (Cramér-Rao-like) precision of the estimate: it falls as 1/√N with the number of
    points averaged, and grows when the peak is flat.
    """
    left, centre, right = values[index - 1], values[index], values[index + 1]
    curvature = left - 2 * centre + right
    step = float(offsets[index + 1] - offsets[index])
    if not curvature < 0:
        return step / np.sqrt(12)  # Quantisation only.
    numerator = left - right
    d_left = (curvature - numerator) / (2 * curvature**2)
    d_centre = numerator / curvature**2
    d_right = (-curvature - numerator) / (2 * curvature**2)
    var = (d_left**2 * variances[index - 1] + d_centre**2 * variances[index]
           + d_right**2 * variances[index + 1])
    return float(min(step * np.sqrt(var), step))


MIN_PERIODICITY = 0.2  # Autocorrelation peak / zero-lag value below which there is no period.


def sheet_spacing(offsets: np.ndarray, profiles: np.ndarray) -> float | None:
    """Distance between sheets: first maximum (lag > 0) of the mean autocorrelation of the profiles.

    Averaging autocorrelations, not profiles, keeps the spacing visible when the segment drifts by
    more than a sheet: each tile's profile is periodic even if their peaks do not line up.
    """
    profiles = np.atleast_2d(np.asarray(profiles, dtype=float))
    profiles = profiles[np.isfinite(profiles).all(axis=1)]
    n = profiles.shape[1]
    if n < 5 or len(profiles) == 0:
        return None
    trend = np.polyfit(offsets, profiles.T, 1)  # Remove each profile's linear trend.
    x = profiles - (trend[0][:, None] * offsets[None, :] + trend[1][:, None])
    if not np.any(x):
        return None
    corr = np.array([np.mean(np.sum(x[:, :n - lag] * x[:, lag:], axis=1)) / (n - lag)
                     for lag in range(2 * n // 3 + 1)])
    for lag in range(2, len(corr) - 1):
        if (corr[lag] >= MIN_PERIODICITY * corr[0] and corr[lag] >= corr[lag - 1]
                and corr[lag] > corr[lag + 1]):
            step = float(offsets[1] - offsets[0])
            return refine_peak(np.arange(len(corr)) * step, corr, lag)
    return None


def segment_reference(offset: np.ndarray, reliability: np.ndarray,
                      spacing: float | None) -> float | None:
    """The segment's usual offset: circular mean of the tile offsets (period Δ), weighted by
    reliability; plain weighted median without Δ. None when no tile is determined."""
    known = np.isfinite(offset)
    if not known.any():
        return None
    w = np.clip(np.nan_to_num(reliability[known], nan=0.0, posinf=1e6), 0, None) + 1e-12
    values = offset[known]
    if spacing:
        angle = np.angle(np.sum(w * np.exp(2j * np.pi * values / spacing)))
        return float(spacing * angle / (2 * np.pi))
    order = np.argsort(values)
    cumulative = np.cumsum(w[order])
    return float(values[order][np.searchsorted(cumulative, cumulative[-1] / 2)])


def _wrap(value, spacing):
    return (value + spacing / 2) % spacing - spacing / 2


def _neighbours(r, c, rows, cols):
    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        if 0 <= r + dr < rows and 0 <= c + dc < cols:
            yield r + dr, c + dc


def unwrap(drift: np.ndarray, reliability: np.ndarray, spacing: float) -> np.ndarray:
    """Quality-guided unwrapping: grow from the most reliable tile, most reliable first."""
    rows, cols = drift.shape
    out = np.full(drift.shape, np.nan)
    known = np.isfinite(drift)
    weight = np.where(np.isfinite(reliability), reliability, 0.0)
    for start in np.argsort(-weight, axis=None):
        r0, c0 = divmod(int(start), cols)
        if not known[r0, c0] or np.isfinite(out[r0, c0]):
            continue
        out[r0, c0] = drift[r0, c0]
        heap = [(-weight[r, c], r, c, r0, c0) for r, c in _neighbours(r0, c0, rows, cols)]
        heapq.heapify(heap)
        while heap:
            _, r, c, pr, pc = heapq.heappop(heap)
            if not known[r, c] or np.isfinite(out[r, c]):
                continue
            out[r, c] = out[pr, pc] + _wrap(drift[r, c] - drift[pr, pc], spacing)
            for nr, nc in _neighbours(r, c, rows, cols):
                if known[nr, nc] and not np.isfinite(out[nr, nc]):
                    heapq.heappush(heap, (-weight[nr, nc], nr, nc, r, c))
    return out


def residues(drift: np.ndarray, spacing: float) -> np.ndarray:
    """+1 / -1 where the wrapped drift does not close around a 2 x 2 loop of tiles."""
    a, b = drift[:-1, :-1], drift[:-1, 1:]
    c, d = drift[1:, 1:], drift[1:, :-1]
    with np.errstate(invalid="ignore"):
        total = (_wrap(b - a, spacing) + _wrap(c - b, spacing) + _wrap(d - c, spacing)
                 + _wrap(a - d, spacing))
        out = np.rint(total / spacing)
    return np.where(np.isfinite(out), out, 0).astype(int)


def _tile_profiles(surface, arrays, shapes, tile, offsets, factor, level, min_points,
                   max_voxels, warnings):
    from scipy import ndimage

    points = surface.points
    normals = grid_normals(points)
    usable = in_volume(points, shapes[0]) & np.isfinite(normals).all(axis=2)
    rows, cols = -(-points.shape[0] // tile), -(-points.shape[1] // tile)
    n = len(offsets)
    profiles = np.full((rows, cols, n), np.nan)
    variances = np.full((rows, cols, n), np.nan)
    counts = np.zeros((rows, cols), dtype=int)
    centers = np.full((rows, cols, 3), np.nan)
    array, level_shape = arrays[level], np.asarray(shapes[level])
    voxels_read = 0
    for tr in range(rows):
        for tc in range(cols):
            block = (slice(tr * tile, (tr + 1) * tile), slice(tc * tile, (tc + 1) * tile))
            mask = usable[block]
            if mask.sum() < min_points:
                continue
            p, nrm = points[block][mask], normals[block][mask]
            coords = ((p[:, None, :] + offsets[None, :, None] * nrm[:, None, :] + 0.5) / factor
                      - 0.5).reshape(-1, 3)
            low = np.maximum(np.floor(coords.min(axis=0)).astype(int) - 1, 0)
            high = np.minimum(np.ceil(coords.max(axis=0)).astype(int) + 2, level_shape)
            if np.any(high <= low):
                continue
            size = int(np.prod(high - low))
            if voxels_read + size > max_voxels:
                warnings.append(f"Budget de {max_voxels} voxels atteint : carte partielle.")
                return profiles, variances, counts, centers, voxels_read
            box = np.asarray(array[low[0]:high[0], low[1]:high[1], low[2]:high[2]],
                             dtype=np.float32)
            voxels_read += size
            values = ndimage.map_coordinates(box, (coords - low).T, order=1, mode="nearest")
            values = values.reshape(len(p), n)
            profiles[tr, tc] = values.mean(axis=0)
            variances[tr, tc] = values.var(axis=0, ddof=1) / len(p)  # Of the tile mean.
            counts[tr, tc] = len(p)
            centers[tr, tc] = p.mean(axis=0)
    return profiles, variances, counts, centers, voxels_read


def alignment_map(surface: TifxyzSurface, arrays, shapes, *, pixel_size_um=None,
                  half_range_um=DEFAULT_HALF_RANGE_UM, tile=DEFAULT_TILE,
                  min_points=DEFAULT_MIN_POINTS, max_voxels=DEFAULT_MAP_MAX_VOXELS,
                  ) -> AlignmentMap:
    """Measure the alignment map of ``surface`` on the volume levels ``arrays`` / ``shapes``."""
    if isinstance(tile, bool) or not isinstance(tile, int) or tile < 2:
        raise ValueError("La taille des tuiles doit être un entier ≥ 2.")
    level = choose_level(shapes, pixel_size_um)
    factor = level_factors(shapes)[level]
    half = half_range_voxels(pixel_size_um, half_range_um)
    step = float(factor.mean())
    count = int(np.floor(half / step))
    if count < 2:
        raise ValueError("Portée du profil trop courte pour le niveau choisi.")
    offsets = step * np.arange(-count, count + 1)
    warnings: list[str] = []
    profiles, variances, counts, centers, voxels_read = _tile_profiles(
        surface, arrays, shapes, tile, offsets, factor, level, min_points, max_voxels, warnings)
    measured = counts > 0
    if not measured.any():
        raise ValueError("Aucune tuile mesurable : pas assez de points valides dans le volume.")

    spacing = sheet_spacing(offsets, profiles[measured])
    if spacing is None:
        warnings.append("Espacement des feuilles introuvable : pas d'analyse de phase.")
    window = spacing / 2 if spacing else half / 2

    rows, cols = counts.shape
    offset = np.full((rows, cols), np.nan)
    reliability = np.full((rows, cols), np.nan)
    uncertainty = np.full((rows, cols), np.nan)
    for tr, tc in zip(*np.nonzero(measured)):
        values = profiles[tr, tc]
        index = nearest_peak(offsets, values, 0.0, window)
        if index is None:
            continue
        offset[tr, tc] = refine_peak(offsets, values, index)
        error = float(np.sqrt(variances[tr, tc, index]))
        height = float(values[index] - values.mean())
        reliability[tr, tc] = height / error if error > 0 else (np.inf if height > 0 else 0.0)
        uncertainty[tr, tc] = peak_uncertainty(offsets, values, variances[tr, tc], index)

    reference = segment_reference(offset, reliability, spacing)
    if reference is None:
        warnings.append("Aucune feuille identifiable sur le segment.")
    drift = offset - (0.0 if reference is None else reference)
    unwrapped = np.full((rows, cols), np.nan)
    sheet = np.full((rows, cols), -999, dtype=int)
    loops = np.zeros((max(rows - 1, 0), max(cols - 1, 0)), dtype=int)
    wraps = []
    if spacing:
        drift = _wrap(drift, spacing)
        unwrapped = unwrap(drift, reliability, spacing)
        known = np.isfinite(unwrapped)
        index_map = np.rint((unwrapped - drift) / spacing)
        if known.any():
            values, freq = np.unique(index_map[known], return_counts=True)
            majority = values[np.argmax(freq)]
            sheet[known] = (index_map[known] - majority).astype(int)
            unwrapped = unwrapped - majority * spacing
        if rows > 1 and cols > 1:
            loops = residues(drift, spacing)
        for r in range(rows):
            for c in range(cols):
                for r2, c2 in ((r + 1, c), (r, c + 1)):
                    if r2 < rows and c2 < cols and np.isfinite(drift[r, c]) \
                            and np.isfinite(drift[r2, c2]) \
                            and abs(drift[r2, c2] - drift[r, c]) > spacing / 2:
                        wraps.append(((r, c), (r2, c2)))
    return AlignmentMap(tile, surface.stride, offsets, profiles, counts, centers, offset,
                        reliability, uncertainty, reference, spacing, drift, unwrapped, sheet,
                        loops, wraps, level, half, voxels_read, tuple(warnings))


DEFAULT_MAX_DRIFT_UM = 30.0
DEFAULT_MIN_RELIABILITY = 3.0  # Provisional, to be calibrated (docs/tasks/T10-carte-alignement.md).
ZONE_SEVERITY = {"saut_de_feuille": 3, "derive": 2, "sans_feuille": 1}


def switch_tiles(amap: AlignmentMap) -> np.ndarray:
    """Tiles touching a wrap edge, a residue or a change of relative sheet index."""
    rows, cols = amap.offset.shape
    mask = np.zeros((rows, cols), dtype=bool)
    for (r, c), (r2, c2) in amap.wraps:
        mask[r, c] = mask[r2, c2] = True
    for r, c in zip(*np.nonzero(amap.residues)):
        mask[r:r + 2, c:c + 2] = True
    sheet = amap.sheet
    known = sheet != -999
    vertical = known[1:, :] & known[:-1, :] & (sheet[1:, :] != sheet[:-1, :])
    horizontal = known[:, 1:] & known[:, :-1] & (sheet[:, 1:] != sheet[:, :-1])
    mask[1:, :] |= vertical
    mask[:-1, :] |= vertical
    mask[:, 1:] |= horizontal
    mask[:, :-1] |= horizontal
    return mask


def reliable_tiles(amap: AlignmentMap, min_reliability=DEFAULT_MIN_RELIABILITY) -> np.ndarray:
    with np.errstate(invalid="ignore"):
        return np.isfinite(amap.offset) & (amap.reliability >= min_reliability)


def drift_voxels(amap: AlignmentMap) -> np.ndarray:
    """Drift to report: unwrapped across the segment when possible, else the wrapped drift."""
    return np.where(np.isfinite(amap.unwrapped), amap.unwrapped, amap.drift)


def review_zones(amap: AlignmentMap, *, pixel_size_um=None, max_drift_um=DEFAULT_MAX_DRIFT_UM,
                 min_reliability=DEFAULT_MIN_RELIABILITY) -> list[dict]:
    """Regions for a human to review, most severe and largest first (active learning).

    ``saut_de_feuille``: sheet switch (wrap edge, residue, change of sheet index);
    ``derive``: reliable tiles drifting more than ``max_drift_um`` from the segment's usual offset
    (voxels when the voxel size is unknown: then ``max_drift_um`` is read as voxels);
    ``sans_feuille``: measured tiles without a reliable sheet. Rows and columns are in the grid of
    the tifxyz files; centres in level-0 voxels (z, y, x).
    """
    from scipy import ndimage

    scale = pixel_size_um if pixel_size_um and pixel_size_um > 0 else 1.0
    switch = switch_tiles(amap)
    reliable = reliable_tiles(amap, min_reliability)
    drift = drift_voxels(amap)
    with np.errstate(invalid="ignore"):
        drifting = reliable & ~switch & (np.abs(drift) * scale > max_drift_um)
    no_sheet = (amap.points > 0) & ~reliable & ~switch
    span = amap.tile * amap.stride
    zones = []
    for kind, mask in (("saut_de_feuille", switch), ("derive", drifting),
                       ("sans_feuille", no_sheet)):
        labels, count = ndimage.label(mask)
        for index, region in enumerate(ndimage.find_objects(labels), start=1):
            inside = labels[region] == index
            tiles = int(inside.sum())
            centers = amap.centers[region][inside]
            centers = centers[np.isfinite(centers).all(axis=1)]
            values = drift[region][inside]
            values = values[np.isfinite(values)]
            zone = {
                "type": kind,
                "gravite": ZONE_SEVERITY[kind],
                "tuiles": tiles,
                "lignes": [region[0].start * span, region[0].stop * span],
                "colonnes": [region[1].start * span, region[1].stop * span],
                "centre_zyx": (None if len(centers) == 0
                               else [round(float(v), 1) for v in centers.mean(axis=0)]),
                "derive_mediane": None if len(values) == 0 else float(np.median(values)) * scale,
            }
            zones.append(zone)
    zones.sort(key=lambda z: (-z["gravite"], -z["tuiles"]))
    for rank, zone in enumerate(zones, start=1):
        zone["rang"] = rank
    return zones


DEFAULT_SMOOTHING = 0.5  # Relative to the mean weight; provisional, to be calibrated.


def snap_field(amap: AlignmentMap, *, min_reliability=DEFAULT_MIN_RELIABILITY,
               smoothing=DEFAULT_SMOOTHING) -> np.ndarray:
    """Per-tile displacement along the normal that brings the segment back to its usual offset.

    Weighted least squares on the tile grid: ``(W + λ L) u = W t``. ``t`` is the drift of
    reliable tiles, away from sheet switches and from the ambiguous half of the period
    (``|drift| > Δ/4``); those excluded tiles are pulled towards 0 instead, so they do not move
    and the field fades smoothly around them. ``L`` is the 4-neighbour graph Laplacian, ``λ`` =
    ``smoothing``. Moving a point by ``+u`` along its normal changes its offset by ``-u``.
    """
    from scipy.sparse import coo_matrix, diags
    from scipy.sparse.linalg import spsolve

    rows, cols = amap.offset.shape
    target = np.nan_to_num(amap.drift, nan=0.0)
    use = reliable_tiles(amap, min_reliability) & ~switch_tiles(amap)
    if amap.spacing:
        with np.errstate(invalid="ignore"):
            use &= np.abs(amap.drift) <= amap.spacing / 4
    weight = np.clip(np.nan_to_num(amap.reliability, nan=0.0, posinf=1e6), 0, None)
    pinned = weight[use].mean() if use.any() else 1.0
    weight = np.where(use, weight, pinned)
    target = np.where(use, target, 0.0)
    n = rows * cols
    index = np.arange(n).reshape(rows, cols)
    pairs = [(index[:-1, :].ravel(), index[1:, :].ravel()),
             (index[:, :-1].ravel(), index[:, 1:].ravel())]
    i = np.concatenate([p[0] for p in pairs])
    j = np.concatenate([p[1] for p in pairs])
    adjacency = coo_matrix((np.ones(len(i)), (i, j)), shape=(n, n))
    adjacency = adjacency + adjacency.T
    laplacian = diags(np.asarray(adjacency.sum(axis=1)).ravel()) - adjacency
    system = diags(weight.ravel()) + smoothing * pinned * laplacian
    field = spsolve(system.tocsc(), weight.ravel() * target.ravel()).reshape(rows, cols)
    if amap.spacing:
        field = np.clip(field, -amap.spacing / 4, amap.spacing / 4)
    return field


def field_on_grid(field: np.ndarray, amap: AlignmentMap, grid_shape) -> np.ndarray:
    """Bilinear interpolation of a per-tile field onto the full grid of the tifxyz files."""
    from scipy import ndimage

    rows, cols = np.mgrid[:grid_shape[0], :grid_shape[1]].astype(float)
    centre = (amap.tile - 1) / 2
    coords = np.stack([(rows / amap.stride - centre) / amap.tile,
                       (cols / amap.stride - centre) / amap.tile])
    return ndimage.map_coordinates(field, coords, order=1, mode="nearest")


def snap_points(points: np.ndarray, field_grid: np.ndarray) -> np.ndarray:
    """Points moved by ``field_grid`` along their normals; invalid points stay NaN."""
    normals = grid_normals(points)
    moved = points + field_grid[..., None] * np.nan_to_num(normals)
    return np.where(np.isfinite(points).all(axis=2)[..., None], moved, np.nan)
