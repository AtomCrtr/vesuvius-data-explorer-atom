"""Plot fixed-grid Z sensitivity and registered review specimens."""

import argparse
import json
from pathlib import Path

import numpy as np


def spatial_figure(plt, scores, spatial, output):
    a, b = scores
    display = np.full(a.shape, np.nan, dtype="f4")
    rows = [r for r in spatial["regions"] if r["status"] == "compared"]
    for row in rows:
        v, u, h, w = row["roi_vuhw"]
        value = row["statistics"]["agreement"]["spearman"]
        if value is not None:
            display[v:v+h, u:u+w] = np.where(np.isfinite(a[v:v+h, u:u+w]), value, np.nan)
    fig, ax = plt.subplots(2, 3, figsize=(12.5, 7.2), layout="constrained")
    for axis, pixels, cmap, title, bounds in (
        (ax[0, 0], np.abs(a-b), "magma", "Écart absolu |A+ − A−|", (0, 1)),
        (ax[0, 1], a-b, "coolwarm", "Contraste signé A+ − A−", (-1, 1)),
        (ax[0, 2], display, "BrBG", "Spearman, fenêtres 128²", (-1, 1)),
    ):
        palette = plt.get_cmap(cmap).copy()
        palette.set_bad("#dadbdd")
        layer = axis.imshow(pixels, interpolation="nearest", cmap=palette, vmin=bounds[0], vmax=bounds[1])
        axis.set(title=title, xlabel="U (pixels)", ylabel="V (pixels)")
        fig.colorbar(layer, ax=axis, shrink=.77)
    for axis, key, label in zip(ax[1],
        ("support_border_median_px", "ct_p90_minus_p10", "tifxyz_bend_median_deg"),
        ("Distance médiane au bord (px)", "Contraste CT P90 − P10", "Variation de normale (°)")):
        valid = [r for r in rows if r["covariates"][key] is not None]
        x = [r["covariates"][key] for r in valid]
        y = [r["statistics"]["absolute_Z_effect_block32"]["estimate"] for r in valid]
        rho = spatial["covariate_associations"][key]["spearman"]
        axis.scatter(x, y, s=17, color="#285786", alpha=.8)
        axis.set(xlabel=label, ylabel="Écart Z moyen", ylim=(0, 1),
                 title=f"Association descriptive · ρ = {rho:.2f}")
        axis.grid(alpha=.17)
    fig.savefig(output, dpi=145)
    plt.close(fig)


def candidate_sheet(plt, scores, ct, review, output):
    fig, panels = plt.subplots(len(review["regions"]), 4, figsize=(8.6, 8.0), layout="constrained")
    for row, regions in zip(panels, review["regions"]):
        v, u = regions["start_vu"]
        ve, ue = regions["stop_vu"]
        window = np.s_[v:ve, u:ue]
        a, b = scores[:, window[0], window[1]]
        entries = ((ct[window]/255, "gray", f"{regions['neutral_id']} · CT 59"),
                   (a, "gray", "A+"), (b, "gray", "A−"), (np.abs(a-b), "magma", "|A+ − A−|"))
        for axis, (pixels, cmap, title) in zip(row, entries):
            axis.imshow(pixels, cmap=cmap, vmin=0, vmax=1, interpolation="nearest")
            axis.set_title(title)
            axis.set_axis_off()
    fig.savefig(output, dpi=120)
    plt.close(fig)


if __name__ == "__main__":
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    p = argparse.ArgumentParser(description=__doc__)
    for name in ("surface", "spatial_report", "review_report", "spatial_png", "review_png"):
        p.add_argument(name, type=Path)
    args = p.parse_args()
    with np.load(args.surface, allow_pickle=False) as data:
        scores, ct = data["scores"], data["ct59"]
    spatial_figure(plt, scores, json.loads(args.spatial_report.read_bytes()), args.spatial_png)
    candidate_sheet(plt, scores, ct, json.loads(args.review_report.read_bytes()), args.review_png)
