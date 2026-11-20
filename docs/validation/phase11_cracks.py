"""Phase 11, step B3: perpendicular misregistration along the two cracks shared by CT and IR (Frag4).

Cracks are physical, ink-independent landmarks. Ink labels and predictions are never read. Windows
(1/4-scale pixels) were fixed from the visible crack geometry before any measurement (``CRACKS``).
For every 8-column bin: CT crack centre = minimum of local texture (air gap), IR crack = maximum of a
thin-dark-line ridge filter (difference of Gaussians, sigma 1.5 vs 6, disfavouring wider ink strokes).
Bins whose trace jumps more than ``MAX_JUMP`` px from the running median are rejected.
Run 1 also required amplitude tests (CT texture < half the window median, IR ridge > median + 4 MAD);
on overlays both tracers followed the cracks while those tests kept 23 bins, some off-crack. Run 2
(this version) keeps the continuity rule only, over a 9-bin median. Run 1 is kept in data/phase11.

    python -I docs/validation/phase11_cracks.py data/phase11 docs/validation/phase11-cracks.json
"""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image
from scipy import ndimage

SCALE, PITCH_UM, BIN, MAX_JUMP = 4, 3.24, 8, 6
CRACKS = {"upper": {"cols": (280, 1450), "rows": (770, 930)},
          "lower": {"cols": (1040, 1240), "rows": (1920, 2020)}}


def down(a):
    h, w = a.shape[0] // SCALE * SCALE, a.shape[1] // SCALE * SCALE
    return a[:h, :w].reshape(h // SCALE, SCALE, w // SCALE, SCALE).mean((1, 3))


def running_ok(y):
    med = ndimage.median_filter(y, size=9, mode="nearest")
    return np.abs(y - med) <= MAX_JUMP


def trace(ct_tex, ir_ridge, rows, cols):
    r0, r1 = rows
    out = []
    for c in range(cols[0], cols[1] - BIN + 1, BIN):
        t = ndimage.gaussian_filter1d(ct_tex[r0:r1, c:c + BIN].mean(1), 2)
        g = ndimage.gaussian_filter1d(ir_ridge[r0:r1, c:c + BIN].mean(1), 1)
        mad = np.median(np.abs(g - np.median(g))) or 1e-9
        out.append({"col": c + BIN / 2, "ct_row": r0 + float(np.argmin(t)), "ir_row": r0 + float(np.argmax(g)),
                    "ct_contrast": float(t.min() / np.median(t)),
                    "ir_ridge_mads": float((g.max() - np.median(g)) / mad), "ct_ok": True, "ir_ok": True})
    ct_y = np.array([b["ct_row"] for b in out])
    ir_y = np.array([b["ir_row"] for b in out])
    for b, a, i in zip(out, running_ok(ct_y), running_ok(ir_y)):
        b["ct_ok"] &= bool(a)
        b["ir_ok"] &= bool(i)
    return out


def stats(d):
    a = np.abs(d)
    q = PITCH_UM * SCALE
    return {"n": int(d.size), "median_signed_px": float(np.median(d)), "median_abs_px": float(np.median(a)),
            "rms_px": float(np.sqrt(np.mean(d**2))), "p90_abs_px": float(np.quantile(a, .9)),
            "median_abs_um_nominal": float(np.median(a)) * q, "rms_um_nominal": float(np.sqrt(np.mean(d**2))) * q,
            "p90_abs_um_nominal": float(np.quantile(a, .9)) * q}


def main(work, out):
    work = Path(work)
    ct = tifffile.imread(work / "raw/sv_32.tif").astype(np.float32)
    ir = np.asarray(Image.open(work / "raw/ir_aligned.png")).astype(np.float32)
    c, i = down(ct), down(ir)
    m = ndimage.gaussian_filter(c, 2)
    tex = np.sqrt(np.maximum(ndimage.gaussian_filter(c**2, 2) - m**2, 0))
    ridge = ndimage.gaussian_filter(i, 6) - ndimage.gaussian_filter(i, 1.5)
    result = {"inputs": {n: hashlib.sha256((work / "raw" / n).read_bytes()).hexdigest()
                         for n in ("sv_32.tif", "ir_aligned.png")},
              "blind": "ink labels and predictions not read", "scale": SCALE,
              "pixel_um_nominal": PITCH_UM * SCALE, "bin_cols": BIN, "max_jump_px": MAX_JUMP,
              "windows": CRACKS, "sign": "dy = IR row - CT row (1/4-scale px), perpendicular to the crack",
              "cracks": {}}
    pooled = []
    for name, w in CRACKS.items():
        bins = trace(tex, ridge, w["rows"], w["cols"])
        d = np.array([b["ir_row"] - b["ct_row"] for b in bins if b["ct_ok"] and b["ir_ok"]])
        pooled.extend(d.tolist())
        result["cracks"][name] = {"bins": bins, "bins_total": len(bins),
                                  "summary": stats(d) if d.size else None}
    result["pooled"] = stats(np.array(pooled)) if pooled else None
    Path(out).write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps({k: v["summary"] for k, v in result["cracks"].items()} | {"pooled": result["pooled"]},
                     indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:3])
