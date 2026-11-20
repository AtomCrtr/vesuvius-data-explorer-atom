"""Reproduce PHerc0500P2 diagnostics from the phase 5 public artefact identities."""

import argparse
import json
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import tifffile
from phase4_ink import MODELS, ORIGIN, SIDE, dump, sha
from scipy.ndimage import distance_transform_cdt
from scipy.signal import fftconvolve

from vesuvius_data_explorer.core.consensus import _distribution, overlap_counts, rank_agreement
from vesuvius_data_explorer.core.ink_disagreement import correlations, shift_metrics, top_masks
from vesuvius_data_explorer.core.tifxyz import load_tifxyz

FRACTIONS = (0.001, 0.005, 0.01, 0.02, 0.05, 0.10, 0.20)
THRESHOLDS = (20, 35, 50, 65, 80, 90)


def fetch(uri, path, limit=1<<20):
    if path.is_file():
        return path.read_bytes()
    bucket, key = uri.removeprefix("s3://").split("/", 1)
    with urlopen(f"https://{bucket}.s3.amazonaws.com/{key}", timeout=30) as response:
        raw = response.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("The downloaded artefact exceeds its budget")
    path.write_bytes(raw)
    return raw


def describe(a, b, mask):
    valid = mask & np.isfinite(a) & np.isfinite(b)
    x, y = a[valid], b[valid]
    return {
        "excluded": int(a.size - valid.sum()),
        "non_finite": int(np.count_nonzero(~(np.isfinite(a) & np.isfinite(b)))),
        "zero_codes": [int(np.count_nonzero(z == 0)) for z in (x, y)],
        **correlations(x, y),
        "rank_agreement": rank_agreement(x, y, FRACTIONS),
        "thresholds": [{"percent_of_255": t, **overlap_counts(x >= 255*(t/100), y >= 255*(t/100))}
                       for t in THRESHOLDS],
        "score_distributions": [_distribution(z, 255) for z in (x, y)],
    }


def localize(a, b, support, top):
    """Count fixed global top ranks in a non-overlapping 128 px grid."""
    rows = []
    for v in range(0, a.shape[0], 128):
        for u in range(0, a.shape[1], 128):
            box = np.s_[v:v+128, u:u+128]
            n = int(support[box].sum())
            if n:
                rows.append({"start_vu": [v, u], "paired_pixels": n,
                             "top_pixels": [int(z[box].sum()) for z in top]})
    return rows


def peak_overlap(top, radius):
    """Screen every offset for overlap, with fixed top sets and no wraparound."""
    a, b = top
    mid_v, mid_u = (n-1 for n in a.shape)
    corr = fftconvolve(a.astype(float), b[::-1, ::-1].astype(float), mode="full")
    window = corr[mid_v-radius:mid_v+radius+1, mid_u-radius:mid_u+radius+1]
    counts = np.rint(window).astype(int)
    maximum = int(counts.max())
    offsets = np.argwhere(counts == maximum) - radius
    distance = int(distance_transform_cdt(~b, metric="chessboard")[a].min()) if a.any() and b.any() else None
    return {"radius_px": radius, "overlap_at_identity": int(counts[radius, radius]),
            "max_overlap": maximum, "count_offsets_at_max": len(offsets),
            "nearest_top_pixel_distance_linf_px": distance,
            "tested_offsets": counts.size}


def run(source, work):
    work.mkdir(parents=True, exist_ok=True)
    audit = json.loads(source.read_bytes())
    maps = []
    for model in MODELS:
        row = audit["maps"][model]
        path = work / f"{model}.full.tif"
        raw = fetch(row["uri"], path)
        if sha(raw) != row["sha256_tiff"]:
            raise ValueError(f"Unexpected public TIFF checksum: {model}")
        maps.append(tifffile.imread(path))
    a, b = maps
    assert a.shape == b.shape and a.dtype == b.dtype == np.uint8
    mesh = work / "historical.tifxyz"
    mesh.mkdir(exist_ok=True)
    for part in ("x.tif", "y.tif", "z.tif", "meta.json"):
        fetch(f"{audit['meshes']['historical']['uri']}/{part}", mesh / part)
    valid_mesh = load_tifxyz(str(mesh.resolve())).valid.repeat(20, axis=0).repeat(20, axis=1)
    common = (a > 0) & (b > 0)
    top = top_masks(a, b, common, 0.01)
    v, u = ORIGIN
    box = np.s_[v:v+SIDE, u:u+SIDE]
    fixed_shifts = [(0, 0), *((d, 0) for d in (-60, -16, -4, 4, 16, 60)),
                    *((0, d) for d in (-60, -16, -4, 4, 16, 60))]
    tested = peak_overlap(top, 60)
    orientations = {}
    for name, transform in (("flip_v", lambda z: z[::-1]), ("flip_u", lambda z: z[:, ::-1]),
                            ("rotate_180", lambda z: z[::-1, ::-1])):
        other = transform(common)
        paired = common & other
        orientations[name] = {"support": overlap_counts(common, other),
                              **correlations(a[paired], transform(b)[paired]),
                              "top": overlap_counts(top[0][paired], transform(top[1])[paired])}
    return {
        "interpretation": "descriptive; no registration optimized against scores",
        "source_audit_sha256": sha(source.read_bytes()), "models": MODELS,
        "shape_vu": a.shape, "axis_shifts": [shift_metrics(a, b, common, top, d) for d in fixed_shifts],
        "shift_screen_top_1_percent": tested, "orientation_sensitivity": orientations,
        "regions_grid_128": localize(a, b, common, top),
        "full_grid": describe(a, b, np.ones_like(common)), "full_nonzero": describe(a, b, common),
        "mesh_support": describe(a, b, valid_mesh),
        "nonzero_inside_mesh": describe(a, b, common & valid_mesh),
        "phase4_window": {"origin_vu": ORIGIN, **describe(a[box], b[box], np.ones_like(common[box]))},
        "phase4_window_nonzero": describe(a[box], b[box], common[box]),
        "support_vs_mesh": overlap_counts(common.ravel(), valid_mesh.ravel()),
    }


def plot(path, report):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(11, 3.6), layout="constrained")
    height, width = report["shape_vu"]
    grid = np.full((2, (height+127)//128, (width+127)//128), np.nan)
    for row in report["regions_grid_128"]:
        v, u = row["start_vu"]
        grid[:, v//128, u//128] = row["top_pixels"]
    for axis, counts, name in zip(axes, grid, ("A", "B")):
        view = axis.imshow(counts, interpolation="nearest", vmin=0, vmax=float(np.nanmax(grid)),
                           cmap="viridis", extent=(0, 128*counts.shape[1], 128*counts.shape[0], 0))
        axis.set(title=f"Top 1 % · Carte {name}", xlabel="U (pixels)", ylabel="V (pixels)")
    fig.colorbar(view, ax=axes[:2], label="Pixels par bloc de 128²", shrink=0.76)
    for key, label in (("full_grid", "Grille entière"), ("full_nonzero", "Support non nul"),
                       ("phase4_window", "Fenêtre CT")):
        rows = report[key]["rank_agreement"]
        axes[2].plot([r["fraction"]*100 for r in rows], [r["jaccard"] for r in rows], "o-", label=label)
    axes[2].set(title="Recouvrement par rang", xlabel="Fraction cible (%)", ylabel="Jaccard", xscale="log")
    axes[2].legend(fontsize=8)
    fig.savefig(path, dpi=155)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provenance", type=Path)
    parser.add_argument("work", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--plot", type=Path)
    args = parser.parse_args()
    result = run(args.provenance, args.work)
    dump(args.output, result)
    if args.plot:
        plot(args.plot, result)
