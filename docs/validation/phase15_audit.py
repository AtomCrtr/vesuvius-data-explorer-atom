"""Phase 15: post-hoc audit of the phase 14 result (labels already read; exploratory by construction).

Questions, on the phase 14 fragments, scores and labels, unchanged:
1. Does H3 (lower 95 % bound of pooled ROC-AUC(Z_out) > 0.5) survive leaving out any single ROI, in particular
   the two near-perfect ones (Frag5 roi1, Frag6 roi7)?
2. Is the ranking fine-scale (strokes) or region-level (the labelled area differs as a whole)?
   - local ROC-AUC: mean over 64 x 64 blocks holding both classes, which removes between-region contrast;
   - shift curve: ROC-AUC with labels shifted by 25-200 um; a stroke-scale signal decays within a stroke width,
     a region-level one barely moves.
3. Label morphology per ROI: connected components, share of the largest one, positives near the support edge;
   per fragment (whole label image, also Frag1, Frag3, Frag4 for reference): component areas and widths.
4. Label-free edge bias: ROC-AUC of Z_out for "within 32 px of the support edge" among valid non-ink pixels;
   and ROC-AUC(Z_out) on the core, without that band.

    .venv/Scripts/python.exe docs/validation/phase15_audit.py docs/validation/phase15-audit.json [--figures DIR]

``--figures`` writes local PNG overlays (EduceLab data: never committed).
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).parent))
import phase13_eval as ev  # noqa: E402
from phase11_z_frag4 import NATIVE_UM  # noqa: E402
from phase12_ink_eval import BINS, BLOCK, binned, ranking, sample_labels  # noqa: E402

FLAGGED = {"Frag5": "roi1", "Frag6": "roi7"}  # ROC-AUC 0.987 and 1.000 in phase14-eval.json.
SHIFTS_UM = (25, 50, 100, 200, 500, 1000)
LOCAL_MIN = 200  # Pixels of each class for a block to enter the local ROC-AUC.
EDGE_PX = 32


def roc(score, truth, valid):
    i = binned(score)
    return ranking(np.bincount(i[valid & truth], minlength=BINS), np.bincount(i[valid & ~truth], minlength=BINS))[1]


def local_roc(score, truth, valid):
    """Mean ROC-AUC over BLOCK x BLOCK blocks holding at least LOCAL_MIN pixels of each class."""
    values = []
    for v in range(0, score.shape[0], BLOCK):
        for u in range(0, score.shape[1], BLOCK):
            box = np.s_[v:v + BLOCK, u:u + BLOCK]
            t, ok = truth[box], valid[box]
            if (ok & t).sum() >= LOCAL_MIN and (ok & ~t).sum() >= LOCAL_MIN:
                values.append(roc(score[box], t, ok))
    return {"mean": float(np.mean(values)) if values else None, "blocks": len(values)}


def shift_curve(score, labels, origin, valid):
    """ROC-AUC with the labels moved by d um in the four axis directions, averaged per d."""
    out = {}
    for d in SHIFTS_UM:
        px = d / NATIVE_UM
        values = [roc(score, sample_labels(labels, origin, 0, s), valid) for s in ((px, 0), (-px, 0), (0, px), (0, -px))]
        values = [v for v in values if v is not None]  # A shift can move every positive off the valid support.
        out[str(d)] = float(np.mean(values)) if values else None
    return out


def morphology(truth, valid, support):
    t = truth & valid
    components, n = ndimage.label(t, structure=np.ones((3, 3)))
    sizes = np.bincount(components.ravel())[1:]
    near_edge = ndimage.distance_transform_edt(support) <= EDGE_PX
    return {"components": int(n), "largest_share": float(sizes.max() / sizes.sum()) if n else None,
            "positives_near_edge_share": float((t & near_edge).sum() / max(t.sum(), 1))}


def edge_bias(score, truth, valid, support):
    near_edge = ndimage.distance_transform_edt(support) <= EDGE_PX
    return roc(score, near_edge, valid & ~truth)


def label_granularity(path, step=4):
    """Component areas (mm2) and maximal inscribed widths (um) of a whole label image, on a 1/step grid."""
    Image.MAX_IMAGE_PIXELS = None  # Published label images exceed PIL's default bomb limit.
    labels = np.asarray(Image.open(path).convert("L"))[::step, ::step] > 127
    components, n = ndimage.label(labels, structure=np.ones((3, 3)))
    px_um = step * NATIVE_UM
    areas = np.bincount(components.ravel())[1:] * px_um ** 2 / 1e6
    keep = np.flatnonzero(areas >= 0.01) + 1  # Ignore specks below 0.01 mm2.
    widths = 2 * px_um * np.asarray(ndimage.maximum(ndimage.distance_transform_edt(labels), components, keep))
    a = areas[keep - 1]
    return {"components_ge_0p01_mm2": int(len(keep)), "area_mm2_median": float(np.median(a)),
            "area_mm2_largest": float(a.max()), "largest_area_share": float(a.max() / a.sum()),
            "max_inscribed_width_um_median": float(np.median(widths)),
            "max_inscribed_width_um_p90": float(np.percentile(widths, 90))}


REFERENCE_LABELS = {"Frag1": "data/phase13/frag1/inklabels.png", "Frag3": "data/phase13/frag3/inklabels.png",
                    "Frag4": "data/phase11/raw/inklabels.png"}


def roi_data(fragment):
    work = ev.WORK / fragment.lower()
    prep = json.loads((work / "z-frag4-w2-prepare.json").read_bytes())
    run = json.loads((work / "z-frag4-w2-run.json").read_bytes())
    if ev.sha(work / "z-frag4-w2-scores.npz") != run["scores_npz_sha256"]:
        raise ValueError(f"{fragment}: scores changed since the CUDA run")
    scores = np.load(work / "z-frag4-w2-scores.npz")
    labels = np.asarray(Image.open(work / "inklabels.png").convert("L")) > 127
    for roi in prep["rois"]:  # Same maps, support and inclusion rule as phase13_eval.report.
        name = roi["name"]
        weight = scores[f"{name}_weight"]
        volume = np.load(work / f"{name}-zout-w2.npy")
        maps = {"Z_out": scores[f"{name}_Z_out"].astype(float), "Z_in": scores[f"{name}_Z_in"].astype(float)}
        maps["B1"], maps["B2"] = ev.baselines(volume)
        support = ndimage.binary_erosion(np.load(work / f"{name}-mask.npy"), iterations=16)
        valid = support & (weight >= 0.25 * weight.max()) & np.isfinite(maps["Z_out"]) & np.isfinite(maps["Z_in"])
        truth = sample_labels(labels, roi["native_origin_rc"], 0)
        included = (valid & truth).sum() >= ev.MIN_CLASS and (valid & ~truth).sum() >= ev.MIN_CLASS
        yield name, maps, truth, valid, support, included, labels, roi["native_origin_rc"], volume


def figure(path, maps, truth, valid, volume):
    """Surface | Z_out | Z_in, each with the label edge in red; local only."""
    edge = truth ^ ndimage.binary_erosion(truth, iterations=2)
    panels = []
    for img in (volume[30:32].mean(0) / 255, maps["Z_out"], maps["Z_in"]):
        g = np.where(valid, np.nan_to_num(img), 0)
        rgb = np.repeat((255 * np.clip(g, 0, 1))[..., None], 3, -1).astype(np.uint8)
        rgb[edge] = (255, 0, 0)
        panels.append(rgb[::2, ::2])
    Image.fromarray(np.hstack(panels)).save(path)


def pooled_h3(rows):
    p = ev.pooled({s: np.hstack([r[0][s] for r in rows]) for s in ev.SCORES},
                  np.hstack([r[1] for r in rows]), np.hstack([r[2] for r in rows]))
    return {"ROC_AUC": p["Z_out"]["ROC_AUC"], "ROC_AUC_95": p["Z_out"]["ROC_AUC_95"],
            "H3": p["Z_out"]["ROC_AUC_95"][0] > 0.5}


def main(out, figures):
    ev.use_protocol(ev.HERE / "phase14-protocol.json")
    result = {"label_of_results": "post hoc on labels read in phase 14; exploratory", "fragments": {}}
    for fragment in ("Frag2", "Frag5", "Frag6"):
        rows, rois = {}, {}
        for name, maps, truth, valid, support, included, labels, origin, volume in roi_data(fragment):
            if figures:
                figure(Path(figures) / f"{fragment}-{name}.png", maps, truth, valid, volume)
            if not included:
                continue
            rows[name] = (maps, truth, valid)
            rois[name] = {"ROC_AUC": {s: roc(m, truth, valid) for s, m in maps.items()},
                          "local_ROC_AUC": {s: local_roc(maps[s], truth, valid) for s in ("Z_out", "B2")},
                          "shift_ROC_AUC_Z_out": shift_curve(maps["Z_out"], labels, origin, valid),
                          "edge_bias_ROC_AUC_Z_out": edge_bias(maps["Z_out"], truth, valid, support),
                          "core_ROC_AUC_Z_out": roc(maps["Z_out"], truth,
                                                    valid & (ndimage.distance_transform_edt(support) > EDGE_PX)),
                          **morphology(truth, valid, support)}
            print(fragment, name, file=sys.stderr, flush=True)
        leave_one = {n: pooled_h3([r for k, r in rows.items() if k != n]) for n in rows}
        worst = min(leave_one, key=lambda n: leave_one[n]["ROC_AUC_95"][0])
        result["fragments"][fragment] = {"label_granularity": label_granularity(ev.WORK / fragment.lower() / "inklabels.png"),
                                         "rois": rois, "all": pooled_h3(list(rows.values())),
                                         "leave_one_out": leave_one, "worst_leave_one_out": worst,
                                         "H3_every_leave_one_out": all(v["H3"] for v in leave_one.values())}
        if fragment in FLAGGED:
            result["fragments"][fragment]["without_flagged"] = {"roi": FLAGGED[fragment],
                                                                **leave_one[FLAGGED[fragment]]}
    result["reference_label_granularity"] = {f: label_granularity(p) for f, p in REFERENCE_LABELS.items()}
    Path(out).write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps({f: e["label_granularity"] for f, e in result["fragments"].items()}
                     | result["reference_label_granularity"], indent=1))
    for f, e in result["fragments"].items():
        print(f, "all", e["all"], "worst LOO", e["worst_leave_one_out"], e["leave_one_out"][e["worst_leave_one_out"]])
        for n, r in e["rois"].items():
            print(" ", n, {s: round(v, 3) for s, v in r["ROC_AUC"].items()},
                  "local", {s: (v["mean"] and round(v["mean"], 3), v["blocks"]) for s, v in r["local_ROC_AUC"].items()},
                  "shift", {d: v and round(v, 3) for d, v in r["shift_ROC_AUC_Z_out"].items()},
                  "core", r["core_ROC_AUC_Z_out"] and round(r["core_ROC_AUC_Z_out"], 3), "edge", r["edge_bias_ROC_AUC_Z_out"] and round(r["edge_bias_ROC_AUC_Z_out"], 3), "comp", r["components"], round(r["largest_share"], 2), "pos@edge", round(r["positives_near_edge_share"], 2))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cli.add_argument("out", type=Path)
    cli.add_argument("--figures", type=Path)
    args = cli.parse_args()
    if args.figures:
        args.figures.mkdir(parents=True, exist_ok=True)
    main(args.out, args.figures)
