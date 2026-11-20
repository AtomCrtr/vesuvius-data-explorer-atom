"""Phase 12: first exploratory ink evaluation of checkpoint A on Frag4, under the frozen protocol.

Protocol: docs/validation/phase12-protocol.json (committed in 5c0602f, SHA-256 checked below). This
script was committed before the ink labels were downloaded; the interpretation rules below fill the
gaps the protocol leaves and are fixed with it.

    .venv/Scripts/python.exe docs/validation/phase12_ink_eval.py data/phase11 --download
    .venv/Scripts/python.exe docs/validation/phase12_ink_eval.py data/phase11 --report docs/validation/phase12-ink-eval.json

Interpretation rules (fixed before labels):
- Scores: phase 11 maps ``z-frag4-w2-scores.npz`` (primary, W2) and ``z-frag4-scores.npz`` (secondary,
  >> 8), checked against the run manifests. Valid pixels exactly as in phase11_z_frag4.report: ROI mask
  eroded by 16 output px, Hann weight >= 25 % of max, both scores finite.
- Labels: sampled at native (row, col) = origin + 2 + i * 2.215 / 3.24, nearest neighbour, positive if
  > 127 after conversion to 8-bit grey. Sampled on a grid padded by the tolerance and the largest shift
  so that label edges outside the ROI count in distances.
- Ranking metrics (PR-AUC = average precision, ROC-AUC) use all valid pixels: the protocol restricts the
  tolerance exclusion to pixel metrics. H2 compares PR-AUC with the positive prevalence on that same set.
  Scores are binned in 4096 bins on [0, 1]; ties inside a bin are grouped (step AP, trapezoid ROC).
- Pixel metrics at threshold 0.5 (score > 0.5) and at the per-ROI 95th score percentile (score >= it) use
  valid pixels farther than the tolerance from every label edge. Undefined when one class is empty there.
- Tolerance metrics: precision_tol = share of predicted positives within the tolerance of a positive
  label pixel; recall_tol = share of valid positive label pixels within the tolerance of a predicted
  positive.
- Intervals: 64 x 64 output blocks resampled with replacement (499 draws, seed 208), percentile 95 %;
  half-width = (upper - lower) / 2.
- Shift sensitivity: labels displaced by s um along rows, then along columns (s in the protocol list);
  PR-AUC point estimates only, primary window.
- Both depth orders and both windows are reported in full, whatever the result.
"""

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

import numpy as np

PROTOCOL = Path(__file__).parent / "phase12-protocol.json"
PROTOCOL_SHA = "dd7807746f203dd79d1a828749c4945d5c5b8e693c636acbe562819cb335174e"
LABEL_URL = ("https://dl.ash2txt.org/fragments/Frag4/PHercParis1Fr39.volpkg/working/"
             "54keV_exposed_surface/PHercParis1Fr39_54keV_inklabels.png")
LABEL_FILE = "raw/inklabels.png"
OUT_PX, OUT_UM, NATIVE_UM = 1024, 2.215, 3.24
BINS, BLOCK, DRAWS, SEED = 4096, 64, 499, 208
ORDERS = ("Z_in", "Z_out")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def binned(score):
    return np.clip((score * BINS).astype(int), 0, BINS - 1)


def ranking(pos_hist, neg_hist):
    """Average precision and ROC-AUC from score histograms (bins ascending in score)."""
    tp, fp = pos_hist[::-1].astype(float), neg_hist[::-1].astype(float)
    p, n = tp.sum(), fp.sum()
    if p == 0 or n == 0:
        return None, None
    ctp, cfp = np.cumsum(tp), np.cumsum(fp)
    precision = np.divide(ctp, ctp + cfp, out=np.zeros_like(ctp), where=(ctp + cfp) > 0)
    return float((tp / p * precision).sum()), float((fp * (ctp - tp / 2)).sum() / (p * n))


def pixel_metrics(pred, truth):
    tp, fp = int((pred & truth).sum()), int((pred & ~truth).sum())
    fn, tn = int((~pred & truth).sum()), int((~pred & ~truth).sum())
    counts = {"TP": tp, "FP": fp, "FN": fn, "TN": tn}
    if tp + fn == 0 or fp + tn == 0:
        return {**counts, "defined": False}
    return {**counts, "defined": True, "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn), "Dice": 2 * tp / (2 * tp + fp + fn), "Jaccard": tp / (tp + fp + fn)}


def ranking_with_interval(score, truth, valid):
    """Point estimates and block-bootstrap intervals for AP, ROC-AUC and prevalence."""
    idx = binned(score)
    pos, neg = [], []
    for v in range(0, score.shape[0], BLOCK):
        for u in range(0, score.shape[1], BLOCK):
            box = np.s_[v:v + BLOCK, u:u + BLOCK]
            ok, t, i = valid[box], truth[box], idx[box]
            if ok.any():
                pos.append(np.bincount(i[ok & t], minlength=BINS))
                neg.append(np.bincount(i[ok & ~t], minlength=BINS))
    pos, neg = np.array(pos), np.array(neg)
    counts = np.random.default_rng(SEED).integers(0, len(pos), (DRAWS, len(pos)))
    counts = np.stack([np.bincount(d, minlength=len(pos)) for d in counts])  # draws x blocks
    boot_pos, boot_neg = counts @ pos, counts @ neg
    boot = np.array([ranking(a, b) for a, b in zip(boot_pos, boot_neg)], dtype=float)
    out = {"blocks": len(pos)}
    for k, (name, estimate) in enumerate(zip(("PR_AUC", "ROC_AUC"), ranking(pos.sum(0), neg.sum(0)))):
        lo, hi = np.nanpercentile(boot[:, k], [2.5, 97.5])
        out[name] = {"estimate": estimate, "interval_95": [float(lo), float(hi)], "half_width": float((hi - lo) / 2)}
    prevalence = boot_pos.sum(1) / (boot_pos.sum(1) + boot_neg.sum(1))
    out["prevalence"] = {"estimate": float(truth[valid].mean()),
                         "interval_95": np.percentile(prevalence, [2.5, 97.5]).tolist()}
    return out


def sample_labels(labels, origin, pad, shift_px=(0.0, 0.0)):
    grid = 2 + np.arange(-pad, OUT_PX + pad) * OUT_UM / NATIVE_UM
    rows = np.clip(np.rint(origin[0] + grid + shift_px[0]).astype(int), 0, labels.shape[0] - 1)
    cols = np.clip(np.rint(origin[1] + grid + shift_px[1]).astype(int), 0, labels.shape[1] - 1)
    return labels[np.ix_(rows, cols)]


def edge_distance(truth):
    """Distance (px) from each pixel to the nearest pixel of the other class, i.e. to a label edge."""
    from scipy import ndimage

    # One term is zero on every pixel; the sum is the distance in its own class (fixed after f9c965d).
    return ndimage.distance_transform_edt(truth) + ndimage.distance_transform_edt(~truth)


def evaluate_map(score, truth_padded, valid, pad, tol_px):
    from scipy import ndimage

    crop = np.s_[pad:pad + OUT_PX, pad:pad + OUT_PX]
    truth = truth_padded[crop]
    to_positive = ndimage.distance_transform_edt(~truth_padded)[crop]
    edge_dist = edge_distance(truth_padded)[crop]
    core = valid & (edge_dist > tol_px)
    positives = valid & truth
    result = {"ranking": ranking_with_interval(score, truth, valid), "thresholds": {}}
    for name, threshold in (("0.5", 0.5), ("top5", float(np.quantile(score[valid], 0.95)))):
        pred = valid & ((score > threshold) if name == "0.5" else (score >= threshold))
        to_pred = ndimage.distance_transform_edt(~pred) if pred.any() else np.full(pred.shape, np.inf)
        result["thresholds"][name] = {
            "threshold": threshold, "predicted_fraction": float(pred[valid].mean()),
            "pixel_outside_tolerance_band": {**pixel_metrics(pred[core], truth[core]), "pixels": int(core.sum())},
            "tolerance": {"precision_tol": float((to_positive[pred] <= tol_px).mean()) if pred.any() else None,
                          "recall_tol": float((to_pred[positives] <= tol_px).mean()) if positives.any() else None}}
    return result


def download(work):
    target = work / LABEL_FILE
    if not target.exists():
        request = urllib.request.Request(LABEL_URL, headers={"User-Agent": "vesuvius-data-explorer"})
        with urllib.request.urlopen(request, timeout=120) as response:
            target.write_bytes(response.read())
    print(f"{target}: {target.stat().st_size} bytes, sha256 {sha(target)}")


def report(work, out):
    from PIL import Image
    from scipy import ndimage

    if sha(PROTOCOL) != PROTOCOL_SHA:
        raise ValueError("The frozen protocol changed")
    protocol = json.loads(PROTOCOL.read_bytes())
    tol_um = protocol["registration_tolerance"]["tolerance_um"]
    tol_px = tol_um / OUT_UM
    pad = int(np.ceil((tol_um + 100) / OUT_UM)) + 2
    image = Image.open(work / LABEL_FILE)
    labels = np.asarray(image.convert("L")) > 127
    if labels.shape != (9791, 6064):
        raise ValueError(f"Unexpected label grid {labels.shape}")
    result = {"protocol_sha256": PROTOCOL_SHA, "label_of_results": protocol["label_of_results"],
              "labels": {"url": LABEL_URL, "sha256": sha(work / LABEL_FILE), "mode": image.mode,
                         "positive_fraction_whole_grid": float(labels.mean())},
              "tolerance": {"um": tol_um, "output_px": tol_px},
              "rules": __doc__.split("Interpretation rules")[1].strip(), "windows": {}}
    for window, tag in (("W2", "-w2"), (">> 8", "")):
        prep = json.loads((work / f"z-frag4{tag}-prepare.json").read_bytes())
        run = json.loads((work / f"z-frag4{tag}-run.json").read_bytes())
        if sha(work / f"z-frag4{tag}-scores.npz") != run["scores_npz_sha256"]:
            raise ValueError("Scores changed since the phase 11 run")
        scores = np.load(work / f"z-frag4{tag}-scores.npz")
        result["windows"][window] = {}
        for roi in prep["rois"]:
            name, origin = roi["name"], roi["native_origin_rc"]
            weight = scores[f"{name}_weight"]
            support = ndimage.binary_erosion(np.load(work / f"{name}-mask.npy"), iterations=16)
            maps = {o: scores[f"{name}_{o}"].astype(float) for o in ORDERS}
            valid = support & (weight >= 0.25 * weight.max()) & np.isfinite(maps["Z_in"]) & np.isfinite(maps["Z_out"])
            truth_padded = sample_labels(labels, origin, pad)
            entry = {"valid_pixels": int(valid.sum()),
                     "label_positive_fraction": float(truth_padded[pad:-pad, pad:-pad][valid].mean())}
            for order in ORDERS:
                entry[order] = evaluate_map(maps[order], truth_padded, valid, pad, tol_px)
            if window == "W2":
                idx = {o: binned(m) for o, m in maps.items()}
                entry["shift_pr_auc"] = {}
                for s in protocol["metrics"]["shift_sensitivity_um"]:
                    for axis in ("row", "col")[: 1 if s == 0 else 2]:
                        shift = (s / NATIVE_UM, 0.0) if axis == "row" else (0.0, s / NATIVE_UM)
                        t = sample_labels(labels, origin, pad, shift)[pad:-pad, pad:-pad]
                        entry["shift_pr_auc"]["0" if s == 0 else f"{axis}{s:+d}um"] = {
                            o: ranking(np.bincount(i[valid & t], minlength=BINS),
                                       np.bincount(i[valid & ~t], minlength=BINS))[0] for o, i in idx.items()}
            result["windows"][window][name] = entry
    primary = result["windows"]["W2"]
    pr = {r: {o: primary[r][o]["ranking"] for o in ORDERS} for r in sorted(primary)}
    h1 = {r: {o: v[o]["PR_AUC"]["estimate"] for o in ORDERS} for r, v in pr.items()}
    h2 = {r: {"PR_AUC_Z_in": v["Z_in"]["PR_AUC"]["estimate"], "prevalence": v["Z_in"]["prevalence"]["estimate"],
              "half_width": v["Z_in"]["PR_AUC"]["half_width"]} for r, v in pr.items()}
    result["hypotheses"] = {
        "H1": {"statement": protocol["hypotheses"]["H1"], "per_roi": h1,
               "supported": all(v["Z_in"] > v["Z_out"] for v in h1.values())},
        "H2": {"statement": protocol["hypotheses"]["H2"], "per_roi": h2,
               "supported": all(v["PR_AUC_Z_in"] - v["prevalence"] > v["half_width"] for v in h2.values())}}
    Path(out).write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result["hypotheses"], indent=1))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cli.add_argument("work", type=Path)
    cli.add_argument("--download", action="store_true")
    cli.add_argument("--report", type=Path)
    args = cli.parse_args()
    if args.download:
        download(args.work)
    elif args.report:
        report(args.work, args.report)
    else:
        cli.error("--download or --report")
