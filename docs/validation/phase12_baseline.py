"""Phase 12, post-hoc control (not in the frozen protocol): does raw CT intensity rank the ink labels?

Added after phase12-ink-eval.json showed Z_out ranking the labels (ROC-AUC 0.86, 0.89) and Z_in at chance.
Descriptive only; no hypothesis is tested. Same ROIs, valid pixels and labels as phase12_ink_eval.

    .venv/Scripts/python.exe docs/validation/phase12_baseline.py data/phase11 docs/validation/phase12-baseline.json

Features, from the W2 input volume fed to A (``roiN-zout-w2.npy``, 62 planes, index increasing toward air):
- surface: mean of planes 30 and 31 (Frag4 layer ~ 32, the published surface);
- all_planes: mean of the 62 planes;
- per_plane: ROC-AUC of each plane alone (depth profile).
ROC-AUC below 0.5 means the label is darker; both raw values are reported, no sign is chosen.
"""

import json
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).parent))
from phase12_ink_eval import BINS, LABEL_FILE, binned, ranking, ranking_with_interval, sample_labels  # noqa: E402


def main(work, out):
    from PIL import Image

    labels = np.asarray(Image.open(work / LABEL_FILE).convert("L")) > 127
    prep = json.loads((work / "z-frag4-w2-prepare.json").read_bytes())
    scores = np.load(work / "z-frag4-w2-scores.npz")
    result = {"post_hoc": __doc__.split("\n")[0], "rois": {}}
    for roi in prep["rois"]:
        name = roi["name"]
        weight = scores[f"{name}_weight"]
        a, b = scores[f"{name}_Z_in"], scores[f"{name}_Z_out"]
        support = ndimage.binary_erosion(np.load(work / f"{name}-mask.npy"), iterations=16)
        valid = support & (weight >= 0.25 * weight.max()) & np.isfinite(a) & np.isfinite(b)
        truth = sample_labels(labels, roi["native_origin_rc"], 0)
        volume = np.load(work / f"{name}-zout-w2.npy").astype(np.float32) / 255
        features = {"surface": volume[30:32].mean(0), "all_planes": volume.mean(0)}
        entry = {k: ranking_with_interval(f, truth, valid) for k, f in features.items()}
        entry["per_plane_roc"] = [ranking(np.bincount(i[valid & truth], minlength=BINS),
                                          np.bincount(i[valid & ~truth], minlength=BINS))[1]
                                  for i in (binned(p) for p in volume)]
        result["rois"][name] = entry
    Path(out).write_text(json.dumps(result, indent=1), encoding="utf-8")
    for name, e in result["rois"].items():
        print(name, {k: (round(e[k]["ROC_AUC"]["estimate"], 3), round(e[k]["PR_AUC"]["estimate"], 4))
                     for k in ("surface", "all_planes")})
        print("  per-plane ROC:", " ".join(f"{v:.2f}" for v in e["per_plane_roc"]))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
