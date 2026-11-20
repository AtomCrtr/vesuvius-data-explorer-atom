"""Search for coarse structural signatures in the published frontal CT overview."""

import argparse
import json
from pathlib import Path

import numpy as np
from phase9_optical import sha
from PIL import Image
from scipy.ndimage import gaussian_filter, zoom
from scipy.signal import fftconvolve

FIGURE_URL = "https://arxiv.org/html/2606.29085v1/edfig5.png"
CT_CROP = (43, 628, 18, 418)
CT_PREVIEW_PITCH_UM = 5000 / 57


def gradient(image, sigma):
    dy, dx = np.gradient(gaussian_filter(image, sigma))
    values = np.hypot(dy, dx)
    return np.clip(values, 0, np.quantile(values, .99))


def nc_map(image, template, select):
    n = int(select.sum())
    local = template[select]
    shape = np.where(select, template-local.mean(), 0)
    def correlate(values, kernel):
        return fftconvolve(values, kernel[::-1,::-1], mode="valid")
    n2 = correlate(image**2, select) - correlate(image, select)**2/n
    with np.errstate(invalid="ignore", divide="ignore"):
        return correlate(image, shape) / np.sqrt(np.sum(shape**2)*n2)


def search(work, audit):
    figure = work/"front-reference-figure.png"
    with Image.open(figure) as source:
        gray = np.asarray(source.convert("L"))
    if gray.shape != (697, 865):
        raise ValueError("The fixed axes refer to the exact published panel")
    v, ve, u, ue = CT_CROP
    ct = gray[v:ve,u:ue].astype(float)
    structure = gradient(ct,.9)
    with np.load(work/"optical-preview.npz") as data:
        relief = data["height"]
    measured = np.isfinite(relief)
    filled = np.where(measured, relief, float(np.nanmedian(relief)))
    results = []
    for name, pitch in (("numeric_export", audit["axis_x"]["pitch_um"]), ("article", .34)):
        factor = pitch*4/CT_PREVIEW_PITCH_UM
        averaged = gaussian_filter(filled, max(1, .45/factor))
        native = gradient(zoom(averaged, factor, order=1), .65)
        valid = zoom(gaussian_filter(measured.astype("f4"), max(1, .45/factor)), factor,
                     order=1) >= .98
        for turn in range(4):
            for mirror in (False, True):
                def orient(a):
                    a = np.rot90(a, turn)
                    return a[:,::-1] if mirror else a
                template, support = orient(native), orient(valid)
                iy, ix = np.indices(template.shape)
                block = max(2, min(template.shape)//5)
                checker = ((iy//block + ix//block) % 2) == 0
                fit = checker & support
                check = ~checker & support
                score = nc_map(structure, template, fit)
                on_papyrus = fftconvolve((ct>24).astype(float), np.ones(template.shape),
                                         mode="valid") >= .95*template.size
                score = np.where(on_papyrus & np.isfinite(score), score, -np.inf)
                held = nc_map(structure, template, check)
                # Retain three disjoint places for each orientation, with holdout scores at the same translations.
                for rank in range(3):
                    a,b = np.unravel_index(np.argmax(score), score.shape)
                    if not np.isfinite(score[a,b]):
                        break
                    results.append({"scale":name,"quarter_turns":turn,"mirror":mirror,
                                    "fit_rank":rank+1, "start_figure_yx":[int(a+v),int(b+u)],
                                    "shape_preview_yx":list(template.shape),
                                    "fit_ncc":float(score[a,b]),
                                    "holdout_ncc":float(held[a,b]) if np.isfinite(held[a,b]) else None})
                    score[max(0,a-template.shape[0]):a+template.shape[0]+1,
                          max(0,b-template.shape[1]):b+template.shape[1]+1] = -np.inf
    results.sort(key=lambda item: -item["fit_ncc"])
    return {"figure_url":FIGURE_URL,"figure_sha256":sha(figure),"ct_panel_crop_yx":list(CT_CROP),
            "figure_pitch_um_estimated_from_5mm_bar":CT_PREVIEW_PITCH_UM,
            "input":"optical relief gradients and CT intensity gradients, no scores or optical annotations",
            "control":"two fixed pitches, 4 quarter turns, optional reflection, spatial holdout blocks",
            "status":"coarse_diagnostic_only", "candidate_translations_by_fit_score":results}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=Path)
    p.add_argument("audit", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    args.output.write_text(json.dumps(search(args.work,json.loads(args.audit.read_bytes())),indent=2,
                                      allow_nan=False)+"\n",encoding="utf8")
