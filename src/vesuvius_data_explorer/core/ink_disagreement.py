"""Rank and spatial diagnostics for two score rasters on a declared grid."""

from math import ceil

import numpy as np
from scipy.stats import rankdata

from .comparison import orientation_pair
from .consensus import analyze_pair, overlap_counts


def _pearson(a, b):
    if a.size < 2 or np.min(a) == np.max(a) or np.min(b) == np.max(b):
        return None
    return float(np.corrcoef(a, b)[0, 1])


def correlations(a, b):
    """Pearson and midrank Spearman on finite, co-located score vectors."""
    valid = np.isfinite(a) & np.isfinite(b)
    x, y = a[valid], b[valid]
    linear = _pearson(x, y)
    ranked = _pearson(rankdata(x), rankdata(y)) if linear is not None else None
    return {"paired_pixels": int(x.size), "pearson": linear, "spearman": ranked}


def inspect_pair(comparison, models, roi, thresholds):
    report = analyze_pair(comparison, models, roi, thresholds)
    v, u, h, w = roi
    a, b = (comparison.predictions[i-1] for i in models)
    x, y = (p.image.pixels[v:v+h, u:u+w] for p in (a, b))
    report["correlations"] = correlations(x, y)
    if orientation_pair(a, b):
        from .ink_spatial import block_interval

        valid = np.isfinite(x) & np.isfinite(y)
        delta = (x.astype(float)-y.astype(float))/a.score_scale
        report["z_sensitivity"] = block_interval(np.abs(delta), valid)
    report["surface"] = {"revision": comparison.surface_revision, "volume": comparison.volume_id,
                         "segment": comparison.segment_id, "pixel_size_um_vu": comparison.pixel_size_um_vu}
    return report


def top_masks(a, b, eligible, fraction):
    """Take all scores tied at the k-th order statistic within eligible pixels."""
    if not 0 < fraction <= 1:
        raise ValueError("La fraction top-k doit être comprise dans ]0,1].")
    valid = eligible & np.isfinite(a) & np.isfinite(b)
    n = int(valid.sum())
    if not n:
        return np.zeros_like(valid), np.zeros_like(valid)
    index = n - ceil(fraction*n)
    return tuple(valid & (scores >= np.partition(scores[valid], index)[index])
                 for scores in (a, b))


def shift_windows(shape, delta):
    """Return the overlapping windows when B moves by (delta V, delta U), without wrap."""
    if len(delta) != 2 or any(type(d) is not int for d in delta):
        raise ValueError("Décalage V/U entier requis.")
    if any(abs(d) >= size for d, size in zip(delta, shape)):
        raise ValueError("Le décalage excède la portée de la grille.")
    a = tuple(slice(max(0, d), min(size, size+d)) for d, size in zip(delta, shape))
    b = tuple(slice(max(0, -d), min(size, size-d)) for d, size in zip(delta, shape))
    return a, b


def shift_metrics(a, b, support, masks, delta):
    """Evaluate a fixed shift without changing either raster's top masks."""
    ra, rb = shift_windows(a.shape, delta)
    va, vb = support[ra], support[rb]
    valid = va & vb & np.isfinite(a[ra]) & np.isfinite(b[rb])
    return {"delta_vu_for_b": delta, **correlations(a[ra][valid], b[rb][valid]),
            "support": overlap_counts(va, vb),
            "top": overlap_counts(masks[0][ra][valid], masks[1][rb][valid]),
            "autocorrelation": [_pearson(m[ra][valid], m[rb][valid]) for m in (a, b)]}
