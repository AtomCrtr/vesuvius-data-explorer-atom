"""Descriptive checkpoint × depth-order contrasts on one registered score grid."""

from itertools import combinations

import numpy as np
from scipy.stats import rankdata

from .consensus import _distribution, overlap_counts, rank_agreement
from .ink_disagreement import correlations

CONDITIONS = ("A+", "A-", "B+", "B-")
FRACTIONS = (0.001, 0.01, 0.05, 0.10)
THRESHOLDS = (20, 35, 50, 65, 80)


def registered_conditions(comparison):
    """Return one position per explicitly identified factorial condition."""
    found = {}
    for index, plane in enumerate(comparison.predictions, 1):
        condition = (plane.provenance or {}).get("factorial_condition")
        if condition in CONDITIONS:
            if condition in found:
                raise ValueError(f"Condition factorielle en double · {condition}")
            found[condition] = index
    return found


def summarize_pair(a, b, support, scales):
    """Report only co-located finite pixels within the supplied support."""
    if a.ndim != 2 or a.shape != b.shape or a.shape != support.shape or support.dtype != bool:
        raise ValueError("Les cartes et le masque booléen doivent partager la même grille V/U.")
    scales = tuple(scales)
    if len(scales) != 2 or any(not np.isfinite(s) or s <= 0 for s in scales):
        raise ValueError("Deux échelles finies et positives sont requises.")
    valid = support & np.isfinite(a) & np.isfinite(b)
    x, y = a[valid], b[valid]
    if any(np.any(z < 0) or np.any(z > s) for z, s in zip((x, y), scales)):
        raise ValueError("Score hors de son échelle déclarée.")
    scores = [_distribution(z, s) for z, s in zip((x, y), scales)]
    ranks = rank_agreement(x, y, FRACTIONS)
    thresholds = [{"percent": t,
                   **overlap_counts(x >= scales[0]*(t/100), y >= scales[1]*(t/100))}
                  for t in THRESHOLDS]
    return {"outside_mask": int(np.count_nonzero(~support)),
            "missing_within_mask": int(np.count_nonzero(support & ~valid)),
            **correlations(x, y), "thresholds": thresholds, "rank_agreement": ranks,
            "score_distributions": scores,
            "interpretation": "descriptive; cuts are fractions of each score scale"}


def factorial_report(cells, support):
    """Cells contain (raster, scale); absent cells have no invented contrasts."""
    if any(k not in CONDITIONS for k in cells):
        raise ValueError("Condition factorielle inconnue.")
    if support.ndim != 2 or support.dtype != bool or any(
            array.shape != support.shape for array, _ in cells.values()):
        raise ValueError("Les conditions doivent partager la grille V/U et son masque.")
    common = support.copy()
    for array, _ in cells.values():
        common &= np.isfinite(array)
    results = {}
    missing = []
    for a, b in combinations(CONDITIONS, 2):
        key = f"{a}/{b}"
        if a not in cells or b not in cells:
            missing.append(key)
            continue
        x, sa = cells[a]
        y, sb = cells[b]
        results[key] = summarize_pair(x, y, common, (sa, sb))
    interaction = None
    n = int(common.sum())
    if n and len(cells) == len(CONDITIONS):
        ap, am, bp, bm = (rankdata(cells[k][0][common])/n for k in CONDITIONS)
        change = (ap-am) - (bp-bm)
        interaction = {"definition": "difference of Z contrasts in within-condition midranks",
                       "mean_absolute": float(np.mean(np.abs(change))),
                       "p90_absolute": float(np.percentile(np.abs(change), 90)),
                       "paired_pixels": n}
    return {"conditions": {k: "available" if k in cells else "checkpoint_missing" for k in CONDITIONS},
            "common_pixels": n, "masked": int(np.count_nonzero(~support)),
            "missing_within_mask": int(support.sum())-n, "contrasts": results,
            "unavailable_contrasts": missing, "rank_interaction": interaction}
