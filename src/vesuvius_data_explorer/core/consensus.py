"""Descriptive agreement on a common raster without ink ground truth."""

from itertools import combinations
from math import ceil

import numpy as np

from .comparison import (
    UNCERTAINTY_MARGIN,
    _roi,
    comparable_probabilities,
    near_threshold,
    roi_coordinates,
)


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def overlap_counts(a, b):
    """Summarize two Boolean decisions for the same eligible pixels."""
    both = int(np.count_nonzero(a & b))
    only_a = int(np.count_nonzero(a)) - both
    only_b = int(np.count_nonzero(b)) - both
    union = both + only_a + only_b
    return {"both_positive": both, "a_only": only_a, "b_only": only_b, "both_below": a.size - union,
            "jaccard": _ratio(both, union), "dice": _ratio(2 * both, union + both),
            "disagreement_rate": _ratio(only_a + only_b, a.size)}


def rank_agreement(a, b, fractions=(0.01, 0.05, 0.20)):
    """Compare each model's own high scores; keep all ties at the cutoff."""
    if a.shape != b.shape or a.ndim != 1:
        raise ValueError("Deux vecteurs de scores au même support sont requis.")
    if not a.size:
        return []
    rows = []
    for fraction in fractions:
        if not 0 < fraction <= 1:
            raise ValueError("Une fraction de rang doit être comprise dans ]0,1].")
        count = ceil(fraction * a.size)
        k = a.size - count
        a_cut, b_cut = np.partition(a, k)[k], np.partition(b, k)[k]
        ae, be = a >= a_cut, b >= b_cut
        rows.append({"fraction": fraction, "requested_pixels": count,
                     "a_cutoff": float(a_cut), "b_cutoff": float(b_cut),
                     "a_selected": int(ae.sum()), "b_selected": int(be.sum()),
                     **overlap_counts(ae, be)})
    return rows


def _distribution(raw, scale):
    values = raw[np.isfinite(raw)]
    counts, edges = np.histogram(values.astype(np.float64) / scale, bins=20, range=(0, 1))
    return {"finite_pixels": values.size, "normalized_bin_edges": edges.tolist(),
            "counts": counts.tolist(),
            "raw_range": [float(values.min()), float(values.max())] if values.size else None}


def analyze_pair(comparison, models, roi, thresholds=(35, 50, 65)):
    """Compare two selected manifests' models over a half-open, local V/U box.

    Each threshold is an integer percent or a pair of integer percents. Missing
    values make a pixel ineligible for overlap statistics, but are reported.
    """
    v, u, h, w = _roi(roi, comparison.ct.pixels.shape)
    ia, ib = models
    if ia == ib or not all(type(index) is int and 1 <= index <= len(comparison.predictions)
                          for index in models):
        raise ValueError("Choisir deux modèles distincts.")
    a, b = (comparison.predictions[index-1] for index in models)
    a_raw, b_raw = (p.image.pixels[v:v+h, u:u+w] for p in (a, b))
    valid = np.isfinite(a_raw) & np.isfinite(b_raw)
    av, bv = a_raw[valid], b_raw[valid]
    rows = []
    for setting in thresholds:
        at, bt = (setting, setting) if isinstance(setting, int) else setting
        if any(type(t) is not int or not 0 <= t <= 100 for t in (at, bt)):
            raise ValueError("Les seuils doivent être des pourcentages entiers dans [0, 100].")
        threshold_a, threshold_b = a.score_scale * (at / 100), b.score_scale * (bt / 100)
        near_a = near_threshold(av, a.score_scale, at)
        near_b = near_threshold(bv, b.score_scale, bt)
        rows.append({"thresholds_percent": [at, bt],
                     "uncertain_pixels": int(np.count_nonzero(near_a | near_b)),
                     **overlap_counts(av >= threshold_a, bv >= threshold_b)})
    probabilities = None
    if av.size and comparable_probabilities(a, b):
        delta = av.astype(np.float64)/a.score_scale - bv.astype(np.float64)/b.score_scale
        probabilities = {"event": a.calibration["event"],
                         "mean_signed_a_minus_b": float(delta.mean()),
                         "mean_absolute_difference": float(np.abs(delta).mean())}
    return {"interpretation": "descriptive", "manifest_sha256": comparison.manifest_sha256,
            "volume_id": comparison.volume_id, "segment_id": comparison.segment_id,
            "surface_revision": comparison.surface_revision, "roi": roi, "axes": ["v", "u"],
            "coordinates": roi_coordinates(comparison, roi),
            "paired_pixels": int(av.size), "missing_pixels": int(a_raw.size-av.size),
            "uncertainty_margin_percent_points": UNCERTAINTY_MARGIN,
            "models": [{"name": p.name, "model": p.model, "score_scale": p.score_scale,
                        "registration": p.registration, "calibration": p.calibration,
                        "provenance": p.provenance} for p in (a, b)],
            "thresholds": rows, "rank_agreement": rank_agreement(av, bv),
            "score_distributions": [_distribution(a_raw, a.score_scale),
                                    _distribution(b_raw, b.score_scale)],
            "probability_differences": probabilities}


def analyze_comparison(comparison, roi, thresholds=(35, 50, 65)):
    """Report each unique pair of the manifest's available models."""
    thresholds = tuple(thresholds)
    return [analyze_pair(comparison, pair, roi, thresholds)
            for pair in combinations(range(1, len(comparison.predictions)+1), 2)]
