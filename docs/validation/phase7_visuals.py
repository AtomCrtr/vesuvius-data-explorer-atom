"""Draw aggregate diagnostics and a local CT / score review sheet."""

import argparse
import json
from pathlib import Path

import numpy as np

from vesuvius_data_explorer.core.comparison import load_comparison


def draw(report, manifest, figure, sheet):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = report["scoring"]
    candidates = {key: row for key, row in rows.items() if "reopen_id" in row}
    keys = ["review", "distant", *candidates]
    labels = ["Fenêtre CT", "Zone distante", "A seule", "B seule", "A et B", "Témoin bas"]
    fig, (left, right) = plt.subplots(1, 2, figsize=(10.3, 4.2), layout="constrained")
    for k, label in zip(keys, labels):
        data = rows[k]["factorial"]["ct_hann_support"]["contrasts"]["A+/A-"]["rank_agreement"]
        left.plot([100*p["fraction"] for p in data], [p["jaccard"] for p in data], "o-", label=label)
    left.set(xscale="log", xlabel="Fraction cible du top-k (%)", ylabel="Jaccard A+/A−",
             title="Accord par rang pour un même checkpoint")
    left.legend(fontsize=8)
    x = np.arange(len(keys))
    for i, (key, label) in enumerate((("public_A/A+", "A publié / A+"), ("public_A/A-", "A publié / A−"),
                                      ("public_B/A+", "B publié / A+"), ("public_B/A-", "B publié / A−"))):
        vals = [rows[k]["published_proximity_descriptive"][key]["spearman"] for k in keys]
        right.bar(x+(i-1.5)*.19, vals, width=.19, label=label)
    right.set(xticks=x, xticklabels=labels, ylabel="Spearman", ylim=(-1, 1),
              title="Proximité descriptive aux TIFF publics")
    right.tick_params(axis="x", labelrotation=25)
    right.legend(fontsize=8, loc="lower right")
    fig.savefig(figure, dpi=145)
    plt.close(fig)

    c = load_comparison(manifest)
    fig, axes = plt.subplots(4, 5, figsize=(10.4, 8.3), layout="constrained")
    for i, ((key, record), row) in enumerate(zip(candidates.items(), axes)):
        v, u = (p - o for p, o in zip(record["origin_vu"], c.origin_vu))
        h, w = record["shape_vu"]
        box = np.s_[v:v+h, u:u+w]
        images = [c.ct.pixels[box]/255,
                  *(p.image.pixels[box]/p.score_scale for p in c.predictions)]
        for j, (axis, values, label) in enumerate(zip(row, images, ("CT", "A publié", "B publié", "A+", "A−"))):
            axis.imshow(values, cmap="gray", vmin=0, vmax=1, interpolation="nearest")
            axis.set_axis_off()
            axis.set_title(label if j else f"{labels[i+2]} · {key[:6]}\n{record['origin_vu']}",
                           fontsize=9)
    fig.savefig(sheet, dpi=115)
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("report", type=Path)
    p.add_argument("manifest", type=Path)
    p.add_argument("figure", type=Path)
    p.add_argument("sheet", type=Path)
    args = p.parse_args()
    draw(json.loads(args.report.read_bytes()), args.manifest, args.figure, args.sheet)
