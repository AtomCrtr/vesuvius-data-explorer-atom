"""Landmark-only registration between explicitly scaled, planar physical grids."""

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import map_coordinates
from scipy.spatial import ConvexHull


@dataclass(frozen=True)
class Grid:
    """Pixel centers in YX order. Origin and pitch are in micrometres."""

    shape: tuple[int, int]
    pitch: tuple[float, float]
    origin: tuple[float, float] = (0., 0.)

    def __post_init__(self):
        if (len(self.shape) != 2 or any(type(n) is not int or n < 2 for n in self.shape)
                or np.shape(self.pitch) != (2,) or np.shape(self.origin) != (2,)
                or not np.isfinite((*self.pitch, *self.origin)).all() or min(self.pitch) <= 0):
            raise ValueError("Invalid calibrated YX grid")

    def physical(self, yx):
        return np.asarray(yx) * self.pitch + self.origin

    def pixels(self, physical):
        return (np.asarray(physical) - self.origin) / self.pitch


def transform(matrix, points):
    return np.asarray(points) @ matrix[:2, :2].T + matrix[:2, 2]


def _fit(source, destination, kind, parity):
    src = source - source.mean(axis=0)
    dst = destination - destination.mean(axis=0)
    for points in (src, dst):
        spread = np.linalg.svd(points, compute_uv=False)
        if spread[0] == 0 or spread[1] / spread[0] < .01:
            raise ValueError("Landmarks must span two physical dimensions")
    if kind == "rigid":
        left, _, right = np.linalg.svd(dst.T @ src)
        correction = np.diag((1., parity * np.linalg.det(left @ right)))
        linear = left @ correction @ right
    elif kind == "affine":
        linear = np.linalg.lstsq(src, dst, rcond=None)[0].T
    else:
        raise ValueError("Select rigid or affine before inspecting validation landmarks")
    if np.linalg.det(linear) * parity <= 1e-8:
        raise ValueError("Degenerate transform or undocumented reflection")
    matrix = np.eye(3)
    matrix[:2, :2] = linear
    matrix[:2, 2] = destination.mean(axis=0) - linear @ source.mean(axis=0)
    return matrix


def landmarks_fit(rows, optical, ct, *, feature_um, kind="rigid", parity=1):
    """Fit using geometric landmarks only, then assess reserved correspondences."""
    if parity not in (-1, 1) or not np.isfinite(feature_um) or feature_um <= 0:
        raise ValueError("Explicit parity and predeclared minimum feature width are required")
    if len({r["id"] for r in rows}) != len(rows) or any(
            r["split"] not in ("fit", "check") or not r.get("feature") for r in rows):
        raise ValueError("Landmarks need distinct IDs, a frozen split and a geometric description")
    src, dst = (np.asarray([r[key] for r in rows], float) for key in ("optical_yx", "ct_vu"))
    for pixels, grid in ((src, optical), (dst, ct)):
        if (pixels.shape != (len(rows), 2) or not np.isfinite(pixels).all()
                or np.any(pixels < 0) or np.any(pixels > np.array(grid.shape) - 1)
                or len(np.unique(pixels, axis=0)) != len(rows)):
            raise ValueError("Landmarks need distinct finite pixel centers inside each grid")
    fit = np.array([r["split"] == "fit" for r in rows])
    if fit.sum() < 4 or (~fit).sum() < 3:
        raise ValueError("At least four fit landmarks and three independent check landmarks are required")
    source, destination = optical.physical(src), ct.physical(dst)
    matrix = _fit(source[fit], destination[fit], kind, parity)
    hull = ConvexHull(destination[fit])
    checked_hull = ConvexHull(destination[~fit]) if np.linalg.matrix_rank(
        destination[~fit] - destination[~fit].mean(axis=0)) == 2 else None
    predicted = transform(matrix, source)
    errors = np.linalg.norm(predicted - destination, axis=1)
    check_error = errors[~fit]
    check_px = np.linalg.norm(ct.pixels(predicted)[~fit] - dst[~fit], axis=1)
    leave_one_out = []
    place = np.where(fit)[0]
    for omitted in place:
        kept = place[place != omitted]
        leave_one_out.append(_fit(source[kept], destination[kept], kind, parity).tolist())
    rms = float(np.sqrt(np.mean(check_error**2)))
    sides = (np.array(ct.shape) - 1) * ct.pitch
    fit_coverage = float(hull.volume / np.prod(sides))
    checked_coverage = float(checked_hull.volume / np.prod(sides)) if checked_hull else 0.
    limit = float(min(2 * max(ct.pitch), feature_um / 4))
    checked_inside = bool(np.max(destination[~fit] @ hull.equations[:, :2].T
                                 + hull.equations[:, 2]) <= 1e-7)
    return {"kind": kind, "parity_xy": parity, "ct_from_optical_um": matrix.tolist(),
            "optical_from_ct_um": np.linalg.inv(matrix).tolist(),
            "linear_singular_values": np.linalg.svd(matrix[:2, :2], compute_uv=False).tolist(),
            "landmarks": [{**row, "error_um": float(err), "error_ct_px": float(np.linalg.norm(p - target)),
                           "residual_ct_yx_um": residual.tolist()}
                          for row, err, p, target, residual in zip(
                              rows, errors, ct.pixels(predicted), dst, predicted - destination)],
            "check_median_um": float(np.median(check_error)), "check_rms_um": rms,
            "check_rms_ct_px": float(np.sqrt(np.mean(check_px**2))),
            "check_median_ct_px": float(np.median(check_px)),
            "check_p90_um": float(np.quantile(check_error, .9)), "limit_um": limit,
            "fit_hull_coverage": fit_coverage, "check_hull_coverage": checked_coverage,
            "check_within_fit_hull": checked_inside,
            "fit_hull_equations": hull.equations.tolist(),
            "leave_one_out_ct_from_optical_um": leave_one_out,
            "quality_gate": bool(rms <= limit and np.quantile(check_error, .9) <= limit
                                 and fit_coverage >= .25 and checked_coverage >= .05 and checked_inside
                                 and (kind == "rigid" or np.allclose(
                                     np.linalg.svd(matrix[:2, :2], compute_uv=False), 1., atol=.1, rtol=0))),
            }


def registration_tolerance(residuals_um, *, reference_px_um, ct_px_um, k=3.0, min_count=20):
    """Spatial tolerance for evaluating against a coarse optical reference (phase 11).

    Pixel-level metrics need a residual below 2 CT pixels, which a reference coarser than the CT
    cannot reach. The tolerance is the larger of |median bias| + k robust sigmas of independent
    residuals (sigma = 1.4826 MAD) and 2 pixels of either grid; metrics must ignore or tolerate
    that distance around label edges.
    """
    residuals = np.asarray(residuals_um, float)
    if residuals.ndim != 1 or residuals.size < min_count or not np.isfinite(residuals).all():
        raise ValueError(f"At least {min_count} finite independent residuals are required")
    if min(reference_px_um, ct_px_um) <= 0 or k <= 0:
        raise ValueError("Pixel sizes and k must be positive")
    bias = float(np.median(residuals))
    sigma = float(1.4826 * np.median(np.abs(residuals - bias)))
    floor = 2 * max(reference_px_um, ct_px_um)
    tolerance = max(abs(bias) + k * sigma, floor)
    return {"n": int(residuals.size), "bias_um": bias, "robust_sigma_um": sigma, "k": k,
            "floor_um": floor, "tolerance_um": tolerance,
            "pixel_metrics_valid": bool(abs(bias) + k * sigma <= 2 * ct_px_um)}


def warp_optical(frame, optical, ct, audit, *, support, discrete=False):
    """Resample from the optical grid, respecting missing pixels and the landmark hull."""
    if (frame.shape[:2] != optical.shape or frame.ndim not in (2, 3)
            or support.shape != optical.shape or support.dtype != bool):
        raise ValueError("Optical raster and valid support must share one grid")
    yx = np.moveaxis(np.indices(ct.shape, dtype=float), 0, -1)
    physical = ct.physical(yx)
    inverse = np.asarray(audit["optical_from_ct_um"])
    coords = np.moveaxis(optical.pixels(transform(inverse, physical)), -1, 0)
    equations = np.asarray(audit["fit_hull_equations"])
    usable = np.ones(ct.shape, bool)
    for eq in equations:
        usable &= physical @ eq[:2] + eq[2] <= 1e-7
    finite = np.isfinite(frame)
    support = support & (finite.all(axis=-1) if frame.ndim == 3 else finite)
    order = 0 if discrete else 1
    usable &= map_coordinates(support.astype(np.float32), coords, order=order,
                              mode="constant", cval=0) >= 1 - 1e-7
    channels = np.moveaxis(frame, -1, 0) if frame.ndim == 3 else (frame,)
    values = [map_coordinates(np.where(support, channel, 0).astype(np.float32), coords,
                              order=order, mode="constant", cval=0) for channel in channels]
    for image in values:
        image[~usable] = np.nan
    return (np.stack(values, axis=-1) if frame.ndim == 3 else values[0]), usable


def spatial_uncertainty(ct, audit, usable):
    """Quadrature of held-out RMS and sensitivity to refitting each fit landmark."""
    yx = np.moveaxis(np.indices(ct.shape, dtype=float), 0, -1)
    physical = ct.physical(yx)
    native = transform(np.asarray(audit["optical_from_ct_um"]), physical)
    shifts = np.zeros(ct.shape, dtype=float)
    trials = audit["leave_one_out_ct_from_optical_um"]
    for matrix in trials:
        delta = transform(np.asarray(matrix), native) - physical
        shifts += np.sum(delta**2, axis=-1)
    result = np.sqrt(shifts / len(trials) + audit["check_rms_um"]**2).astype(np.float32)
    result[~usable] = np.nan
    return result
