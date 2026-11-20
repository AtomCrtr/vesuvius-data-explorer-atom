"""Fixed spatial windows and block-resampled summaries for paired orientations."""

import numpy as np

from .ink_disagreement import top_masks
from .ink_factorial import summarize_pair


def windows(shape, side):
    if len(shape) != 2 or min(shape) < 1 or type(side) is not int or side < 1:
        raise ValueError("Grille V/U et taille de bloc positive requises.")
    height, width = shape
    return [(v, u, min(side, height-v), min(side, width-u))
            for v in range(0, height, side) for u in range(0, width, side)]


def block_interval(values, valid, *, block=32, draws=499, seed=208):
    """Percentile interval for a mean, resampling nonempty contiguous V/U blocks."""
    if values.ndim != 2 or values.shape != valid.shape or valid.dtype != bool or draws < 1:
        raise ValueError("Valeurs, masque et réplications incompatibles.")
    valid = valid & np.isfinite(values)
    sums, counts = [], []
    for v, u, h, w in windows(values.shape, block):
        box = np.s_[v:v+h, u:u+w]
        sample = values[box][valid[box]]
        if sample.size:
            sums.append(float(sample.sum(dtype=np.float64)))
            counts.append(sample.size)
    result = {"block_side": block, "blocks": len(counts), "draws": draws, "seed": seed,
              "interval_95": None, "estimate": sum(sums)/sum(counts) if counts else None}
    if len(counts) >= 4:
        ids = np.random.default_rng(seed).integers(0, len(counts), (draws, len(counts)))
        means = np.array(sums)[ids].sum(axis=1)/np.array(counts)[ids].sum(axis=1)
        result["interval_95"] = np.percentile(means, [2.5, 97.5]).tolist()
    return result


def effect(a, b, valid):
    """Summarize support, score dispersion and orientation change on one window."""
    comparison = summarize_pair(a, b, valid, (1, 1))
    paired = valid & np.isfinite(a) & np.isfinite(b)
    delta = a-b
    top = top_masks(a, b, paired, 0.05)
    stats = []
    for z, selected, distribution in zip((a, b), top, comparison["score_distributions"]):
        values = z[paired]
        if not values.size:
            stats.append({"variance": None, "entropy_bits": None, "almost_constant": None,
                          "top5_max_block_share": None})
            continue
        variance = float(np.var(values, dtype=np.float64))
        counts = np.asarray(distribution["counts"])
        probability = counts[counts > 0]/counts.sum()
        max_count = max(int(selected[v:v+h, u:u+w].sum())
                        for v, u, h, w in windows(z.shape, 16))
        stats.append({"variance": variance, "almost_constant": variance < 0.005**2,
                      "entropy_bits": float(-(probability*np.log2(probability)).sum()),
                      "top5_max_block_share": max_count/int(selected.sum())})
    return {"agreement": comparison, "valid_fraction": int(paired.sum())/paired.size,
            "score_stats": stats, "absolute_Z_effect_block32": block_interval(np.abs(delta), paired),
            "absolute_Z_effect_block64": block_interval(np.abs(delta), paired, block=64),
            "signed_Z_effect": float(delta[paired].mean()) if paired.any() else None}
