"""Eligibility gates and measurements for a frozen CT-to-optical evaluation."""

import hashlib
import json

import numpy as np
from scipy.ndimage import distance_transform_edt, shift

THRESHOLDS = (.20, .35, .50, .65, .80)


def independence_status(reference, training, *, exhaustive=False):
    """Training includes all data-development stages, copies and known derivatives."""
    if (not reference.get("manuscript") or not reference.get("sample")
            or not reference.get("sha256")):
        raise ValueError("The reference manuscript, sample and digest are required")
    levels = []
    digests = {reference["sha256"], *reference.get("ancestors", ())}
    for sample in training:
        related = {sample.get("sha256"), *sample.get("ancestors", ())} - {None}
        if digests & related or (sample.get("sample") == reference["sample"]
                                 and sample.get("manuscript") == reference["manuscript"]):
            levels.append("same_source")
        elif sample.get("manuscript") == reference["manuscript"]:
            levels.append("same_manuscript")
        elif not sample.get("manuscript") or not sample.get("sha256"):
            levels.append("unknown")
    return next((level for level in ("same_source", "same_manuscript", "unknown") if level in levels),
                "independent" if exhaustive else "unknown")


def _ratio(a, b):
    return float(a/b) if b else None


def measures(scores, label, support):
    scores, label, support = map(np.asarray, (scores, label, support))
    if (scores.shape != label.shape or scores.shape != support.shape
            or label.dtype != bool or support.dtype != bool):
        raise ValueError("Scores, binary annotations and validity must share a grid")
    valid = support & np.isfinite(scores)
    y, x = label[valid], scores[valid]
    if not len(y) or np.min(x) < 0 or np.max(x) > 1:
        raise ValueError("Paired normalized scores in [0,1] are required")
    positives, negatives = int(y.sum()), int(len(y)-y.sum())
    thresholds = []
    for t in THRESHOLDS:
        hit = x >= t
        tp, fp = int(np.sum(hit & y)), int(np.sum(hit & ~y))
        fn, tn = positives-tp, negatives-fp
        thresholds.append({"threshold": t, "tp": tp, "tn": tn, "fp": fp, "fn": fn,
                           "precision": _ratio(tp, tp+fp), "recall": _ratio(tp, positives),
                           "specificity": _ratio(tn, negatives), "dice": _ratio(2*tp, 2*tp+fp+fn),
                           "jaccard": _ratio(tp, tp+fp+fn)})
    curves = None
    if positives and negatives:
        desc = np.argsort(-x, kind="stable")
        positions = np.r_[np.flatnonzero(np.diff(x[desc])), len(y)-1]
        tp = np.r_[0, y[desc].cumsum()[positions]]
        fp = np.r_[0, positions+1] - tp
        recall, fpr = tp/positives, fp/negatives
        precision = np.r_[1., tp[1:] / (tp[1:]+fp[1:])]
        trapezoid = getattr(np, "trapezoid", None)
        if trapezoid is None:
            trapezoid = np.trapz
        curves = {"threshold": [None, *x[desc][positions].tolist()], "precision": precision.tolist(),
                  "recall": recall.tolist(), "fpr": fpr.tolist(),
                  "roc_auc": float(trapezoid(recall, fpr)), "pr_auc": float(trapezoid(precision, recall)),
                  "average_precision": float(np.sum(np.diff(recall)*precision[1:]))}
    return {"pixels": len(y), "positive_pixels": positives, "thresholds": thresholds, "curves": curves}


def geometry_sha256(audit, identity, pitch, support):
    """Fingerprint the geometry and its usable support before opening the ink layers."""
    record = {key:value for key,value in identity.items() if key != "frozen_geometry_sha256"}
    document = {"registration": audit, "identity": record, "ct_pitch_um": list(pitch),
                "mask_shape": list(support.shape),
                "mask_sha256": hashlib.sha256(np.packbits(support).tobytes()).hexdigest()}
    return hashlib.sha256(json.dumps(document, sort_keys=True, allow_nan=False).encode()).hexdigest()


def evaluate_registered(pair, label, support, pitch, audit, identity, independence):
    """Apply the same frozen geometry, mask and fixed thresholds to both orientations."""
    if (not audit.get("quality_gate") or identity.get("location") != "confirmed"
            or identity.get("face") != "confirmed" or identity.get("scale") != "confirmed"
            or identity.get("frozen_geometry_sha256") != geometry_sha256(audit, identity, pitch, support)
            or set(pair) != {"A+", "A-"}):
        raise ValueError("Evaluation requires frozen geometry, scale, location, face and held-out quality")
    usable = support & np.isfinite(pair["A+"]) & np.isfinite(pair["A-"])
    uncertainty = audit["check_p90_um"]
    distances = (distance_transform_edt(label, sampling=pitch)
                 + distance_transform_edt(~label, sampling=pitch))
    interior = usable & (distances > uncertainty+max(pitch)/2)
    report = {"status": "independent" if independence == "independent" else "exploratory",
              "geometry_sha256": identity["frozen_geometry_sha256"],
              "boundary_exclusion_um": float(uncertainty+max(pitch)/2),
              "both_orientations": {}, "translations": []}
    for key, scores in pair.items():
        report["both_orientations"][key] = {
            "full": measures(scores, label, usable),
            "away_from_boundary": measures(scores, label, interior) if interior.any() else None,
        }
    for axis in range(2):
        for direction in (-1, 1):
            displacement = [0, 0]
            displacement[axis] = direction * max(1, int(np.ceil(uncertainty/pitch[axis])))
            shifted = shift(label, displacement, order=0, cval=False)
            common = usable & shift(support, displacement, order=0, cval=False)
            if common.any():
                report["translations"].append({"ct_yx_px": displacement, "results": {
                    k: measures(x, shifted, common)["thresholds"] for k, x in pair.items()
                }})
    return report
