"""Phase 14, discovery set: can a label-free statistic of A's two score maps predict which order ranks ink?

Uses only ROIs whose labels are already open (Frag4 ROIs 2-5 from phases 12-13, Frag1, Frag3). Exploratory by
construction: the candidates below are screened here, and only the rule frozen afterwards in
phase14-protocol.json is tested on held-out fragments.

    .venv/Scripts/python.exe docs/validation/phase14_discovery.py docs/validation/phase14-discovery.json

Label-free candidates, per ROI, computed on valid pixels of each order's map:
- std: spatial standard deviation of the score;
- p99_minus_median: upper tail of the score;
- smooth_share: variance of a Gaussian-smoothed map (sigma 8 px) over the raw variance (spatial coherence);
- surface_corr: |Spearman| between the score and the surface intensity (input planes 30-31).
A rule "pick the order with the larger candidate" is scored by how often it picks the order with the higher
ROC-AUC. Order-free combinations are also scored: rank average and maximum of the two maps.
"""

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage, stats

sys.path.insert(0, str(Path(__file__).parent))
from phase12_ink_eval import BINS, binned, ranking, sample_labels  # noqa: E402

SETS = {  # fragment: (work dir, labels, ROI names or None for all)
    "Frag4": [(Path("data/phase11"), Path("data/phase11/raw/inklabels.png"), ("roi2", "roi5")),
              (Path("data/phase13/frag4"), Path("data/phase11/raw/inklabels.png"), ("roi3", "roi4"))],
    "Frag1": [(Path("data/phase13/frag1"), Path("data/phase13/frag1/inklabels.png"), None)],
    "Frag3": [(Path("data/phase13/frag3"), Path("data/phase13/frag3/inklabels.png"), None)],
}


def roc(score, truth, valid):
    i = binned(score)
    return ranking(np.bincount(i[valid & truth], minlength=BINS), np.bincount(i[valid & ~truth], minlength=BINS))[1]


def rank01(score, valid):
    out = np.zeros_like(score)
    out[valid] = stats.rankdata(score[valid]) / valid.sum()
    return out


def candidates(score, valid, surface):
    v = score[valid]
    smooth = ndimage.gaussian_filter(np.where(valid, score, v.mean()), 8)[valid]
    return {"std": float(v.std()), "p99_minus_median": float(np.quantile(v, .99) - np.median(v)),
            "smooth_share": float(smooth.var() / max(v.var(), 1e-12)),
            "surface_corr": float(abs(stats.spearmanr(v, surface[valid]).statistic))}


def main(out):
    rows = []
    for fragment, sets in SETS.items():
        for work, label_path, names in sets:
            labels = np.asarray(Image.open(label_path).convert("L")) > 127
            prep = json.loads((work / "z-frag4-w2-prepare.json").read_bytes())
            scores = np.load(work / "z-frag4-w2-scores.npz")
            for roi in prep["rois"]:
                name = roi["name"]
                if names and name not in names:
                    continue
                weight = scores[f"{name}_weight"]
                z = {o: scores[f"{name}_{o}"].astype(float) for o in ("Z_out", "Z_in")}
                support = ndimage.binary_erosion(np.load(work / f"{name}-mask.npy"), iterations=16)
                valid = support & (weight >= 0.25 * weight.max()) & np.isfinite(z["Z_out"]) & np.isfinite(z["Z_in"])
                truth = sample_labels(labels, roi["native_origin_rc"], 0)
                if (valid & truth).sum() < 1000 or (valid & ~truth).sum() < 1000:
                    continue
                surface = np.load(work / f"{name}-zout-w2.npy")[30:32].astype(float).mean(0)
                ranks = {o: rank01(m, valid) for o, m in z.items()}
                rows.append({"fragment": fragment, "roi": name,
                             "roc": {o: roc(m, truth, valid) for o, m in z.items()},
                             "roc_rank_mean": roc((ranks["Z_out"] + ranks["Z_in"]) / 2, truth, valid),
                             "roc_rank_max": roc(np.maximum(ranks["Z_out"], ranks["Z_in"]), truth, valid),
                             "features": {o: candidates(m, valid, surface) for o, m in z.items()}})
                print(fragment, name, file=sys.stderr, flush=True)
    names = list(rows[0]["features"]["Z_out"])
    screen = {}
    for f in names:
        larger = [r["features"]["Z_out"][f] > r["features"]["Z_in"][f] for r in rows]
        picks = [lg == (r["roc"]["Z_out"] > r["roc"]["Z_in"]) for lg, r in zip(larger, rows)]
        chosen = [r["roc"]["Z_out"] if lg else r["roc"]["Z_in"] for lg, r in zip(larger, rows)]
        screen[f] = {"correct_picks": int(sum(picks)), "rois": len(rows), "mean_roc_of_pick": float(np.mean(chosen))}
    summary = {"rois": len(rows),
               "mean_roc": {k: float(np.mean([r["roc"][k] for r in rows])) for k in ("Z_out", "Z_in")},
               "mean_roc_oracle": float(np.mean([max(r["roc"].values()) for r in rows])),
               "mean_roc_rank_mean": float(np.mean([r["roc_rank_mean"] for r in rows])),
               "mean_roc_rank_max": float(np.mean([r["roc_rank_max"] for r in rows])),
               "screen_pick_larger": screen}
    Path(out).write_text(json.dumps({"rows": rows, "summary": summary}, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    for r in rows:
        print(r["fragment"], r["roi"], {k: round(v, 3) for k, v in r["roc"].items()}, round(r["roc_rank_mean"], 3),
              {f: (round(r["features"]["Z_out"][f], 3), round(r["features"]["Z_in"][f], 3)) for f in names})


if __name__ == "__main__":
    main(sys.argv[1])
