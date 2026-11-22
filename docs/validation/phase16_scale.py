"""Phase 16 (task T2): real lateral pitch from the mesh PPM versus the nominal 3.24 um pitch, checkpoint A.

Protocol: docs/validation/phase16-protocol.json, committed with this script before any real-pitch volume or
score. Same ROIs, window, direction and depth coordinates as phases 13-14; only the lateral grid changes:
each axis is resampled with the ROI's median PPM pitch so that an output pixel spans 2.215 um on the mesh.

    .venv/Scripts/python.exe docs/validation/phase16_scale.py --prepare Frag1          # each fragment
    data/phase6-cuda/Scripts/python.exe docs/validation/phase11_z_frag4.py data/phase16/frag1 \
        --window docs/validation/phase16-prepare-frag1.json                         # A, both orders
    .venv/Scripts/python.exe docs/validation/phase16_scale.py --report docs/validation/phase16-eval.json

``--prepare`` reads no label. ``--report`` compares with the nominal scores already computed in phases 13-14.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage, stats

sys.path.insert(0, str(Path(__file__).parent))
import phase13_eval as ev  # noqa: E402
from phase11_geometry import PATCH  # noqa: E402
from phase11_window import moments_u8  # noqa: E402
from phase11_z_frag4 import NATIVE_UM, OUT_PX, OUT_UM  # noqa: E402
from phase12_ink_eval import BINS, binned, ranking, sample_labels  # noqa: E402

PROTOCOL = ev.HERE / "phase16-protocol.json"
LATTICE = 16
DRAWS, SEED = 9999, 216
NOMINAL_STEP = OUT_UM / NATIVE_UM


def lattice_pitch(points, valid):
    """Pitch statistics of a PPM sampled on a LATTICE grid: points (h, w, 3) in voxels, valid (h, w)."""
    dc = np.linalg.norm(points[:, 1:] - points[:, :-1], axis=-1) / LATTICE
    dr = np.linalg.norm(points[1:] - points[:-1], axis=-1) / LATTICE
    ok_c, ok_r = valid[:, 1:] & valid[:, :-1], valid[1:] & valid[:-1]
    both = ok_c[:-1] & ok_r[:, :-1]
    u = (points[:-1, 1:] - points[:-1, :-1])[both]
    v = (points[1:, :-1] - points[:-1, :-1])[both]
    cos = np.abs((u * v).sum(-1)) / (np.linalg.norm(u, axis=-1) * np.linalg.norm(v, axis=-1))
    iqr = lambda a: [float(np.percentile(a, 25)), float(np.percentile(a, 75))]  # noqa: E731
    return {"pitch_col_vox": float(np.median(dc[ok_c])), "pitch_row_vox": float(np.median(dr[ok_r])),
            "pitch_col_iqr": iqr(dc[ok_c]), "pitch_row_iqr": iqr(dr[ok_r]),
            "abs_cos_median": float(np.median(cos)), "lattice_pairs": int(both.sum())}


def read_lattice(surface, ppm_url, mask, r0, c0, n):
    """PPM positions on a LATTICE grid over the box [r0, r0 + n) x [c0, c0 + n), one HTTP range per row."""
    head = surface.fs.cat_file(ppm_url, start=0, end=1024)
    assert f"width: {mask.shape[1]}".encode() in head and f"height: {mask.shape[0]}".encode() in head
    offset, width = head.index(b"<>\n") + 3, mask.shape[1]
    rows = np.arange(r0, r0 + n, LATTICE)
    starts = [offset + (r * width + c0) * 48 for r in rows]
    raw = surface.fs.cat_ranges([ppm_url] * len(rows), starts, [s + n * 48 for s in starts])
    ppm = np.stack([np.frombuffer(b, "<f8").reshape(n, 6) for b in raw])[:, ::LATTICE]
    valid = np.any(ppm != 0, axis=-1) & mask[np.ix_(rows, np.arange(c0, c0 + n, LATTICE))]
    return ppm[..., :3], valid


def grid(steps):
    return [2 + np.arange(OUT_PX) * s for s in steps]


def extract_scaled(surface, mask, patch, coords, w2, steps):
    """phase13_eval.extract with a per-axis step (native px per output px), same centre and margins."""
    centre = [p + PATCH / 2 for p in patch]
    origin = [int(round(m - OUT_PX * s / 2)) - 2 for m, s in zip(centre, steps)]
    nr, nc = (int(np.ceil(OUT_PX * s)) + 5 for s in steps)
    lo, hi = int(np.floor(coords.min())), int(np.ceil(coords.max()))
    block = np.stack([surface.layer(k, origin[0], origin[1], nr, nc) for k in range(lo, hi + 1)]).astype(np.float32)
    yy, xx = np.meshgrid(*grid(steps), indexing="ij")
    below = np.floor(coords - lo).astype(int)
    frac = (coords - lo) - below
    planes = [(1 - f) * block[b] + f * block[min(b + 1, len(block) - 1)] for b, f in zip(below, frac)]
    volume = np.stack([ndimage.map_coordinates(p, [yy, xx], order=1, mode="nearest") for p in planes])
    sub = mask[origin[0]:origin[0] + nr, origin[1]:origin[1] + nc].astype(np.float32)
    roi_mask = ndimage.map_coordinates(sub, [yy, xx], order=0) > 0.5
    return moments_u8(volume, w2["w2_mean_u16"], w2["w2_std_u16"]), roi_mask, origin


def sample_labels_scaled(labels, origin, steps):
    rows, cols = (np.clip(np.rint(o + g).astype(int), 0, size - 1)
                  for o, g, size in zip(origin, grid(steps), labels.shape))
    return labels[np.ix_(rows, cols)]


def prepare(fragment):
    protocol = ev.read_frozen_protocol(PROTOCOL)
    entry = protocol["fragments"][fragment]
    nominal = Path(entry["nominal"])
    prep = json.loads((nominal / "z-frag4-w2-prepare.json").read_bytes())
    if ev.sha(nominal / "mask.png") != prep["mask_sha256"]:
        raise ValueError(f"{fragment}: mask changed since the nominal preparation")
    mask = np.asarray(Image.open(nominal / "mask.png")) > 0
    surface = ev.Surface(fragment, mask.shape)
    ppm_url = surface.base + entry["ppm"]
    coords = np.asarray(prep["z_out_layer_coords"])
    w2 = {k: prep[k] for k in ("w2_depth_layers", "w2_mean_u16", "w2_std_u16", "w2_target_mean_std_over_200")}
    work = ev.WORK / fragment.lower()
    work.mkdir(parents=True, exist_ok=True)
    summary = {"blind": "ink labels not read", "fragment": fragment, "nominal_prepare": str(nominal),
               "mask_sha256": prep["mask_sha256"], "mask_shape": prep["mask_shape"], "ppm": ppm_url,
               "z_out_layer_coords": prep["z_out_layer_coords"], **w2, "rois": []}
    nominal_rois = {r["patch_index"]: r for r in prep["rois"]}
    for index in entry["patches"]:
        box = nominal_rois[index]
        points, valid = read_lattice(surface, ppm_url, mask, *box["native_origin_rc"], box["native_size"])
        pitch = lattice_pitch(points, valid)
        steps = [OUT_UM / (NATIVE_UM * pitch["pitch_row_vox"]), OUT_UM / (NATIVE_UM * pitch["pitch_col_vox"])]
        u8, roi_mask, origin = extract_scaled(surface, mask, prep["patches_rc"][index], coords, w2, steps)
        name = f"roi{index}"
        np.save(work / f"{name}-zout-w2.npy", u8)
        np.save(work / f"{name}-mask.npy", roi_mask)
        summary["rois"].append({"name": name, "patch_index": index, "native_origin_rc": origin,
                                "steps_native_px": steps, **pitch, "npy_sha256": ev.sha(work / f"{name}-zout-w2.npy"),
                                "mask_fraction": float(roi_mask.mean())})
        print(fragment, name, {k: round(pitch[k], 3) for k in ("pitch_row_vox", "pitch_col_vox", "abs_cos_median")},
              file=sys.stderr, flush=True)
    text = json.dumps(summary, indent=1)
    (work / "z-frag4-w2-prepare.json").write_text(text, encoding="utf-8")
    (ev.HERE / f"phase16-prepare-{fragment.lower()}.json").write_text(text, encoding="utf-8")


def roc(score, truth, valid):
    i = binned(score)
    return ranking(np.bincount(i[valid & truth], minlength=BINS), np.bincount(i[valid & ~truth], minlength=BINS))[1]


def load(work, labels, sampler):
    """Maps, truth and valid pixels per ROI of a prepared and scored work directory (phases 13-14 rules)."""
    prep = json.loads((work / "z-frag4-w2-prepare.json").read_bytes())
    run = json.loads((work / "z-frag4-w2-run.json").read_bytes())
    if ev.sha(work / "z-frag4-w2-scores.npz") != run["scores_npz_sha256"]:
        raise ValueError(f"{work}: scores changed since the CUDA run")
    scores = np.load(work / "z-frag4-w2-scores.npz")
    out = {}
    for roi in prep["rois"]:
        name = roi["name"]
        weight = scores[f"{name}_weight"]
        maps = {"Z_out": scores[f"{name}_Z_out"].astype(float), "Z_in": scores[f"{name}_Z_in"].astype(float)}
        maps["B1"], maps["B2"] = ev.baselines(np.load(work / f"{name}-zout-w2.npy"))
        support = ndimage.binary_erosion(np.load(work / f"{name}-mask.npy"), iterations=16)
        valid = support & (weight >= 0.25 * weight.max()) & np.isfinite(maps["Z_out"]) & np.isfinite(maps["Z_in"])
        truth = sampler(labels, roi)
        ok = (valid & truth).sum() >= ev.MIN_CLASS and (valid & ~truth).sum() >= ev.MIN_CLASS
        out[name] = (maps, truth, valid, ok, roi)
    return out


def summary_of(maps, truth, valid):
    z = maps["Z_out"][valid]
    return {"ROC_Z_out": roc(maps["Z_out"], truth, valid), "ROC_Z_in": roc(maps["Z_in"], truth, valid),
            "share_Z_out_gt_0p5": float((z > 0.5).mean()), "max_Z_out": float(z.max())}


def distortion(roi):
    a, b = roi["pitch_col_vox"], roi["pitch_row_vox"]
    return abs(np.log(a * b)) + abs(np.log(a / b))


def report(out):
    protocol = ev.read_frozen_protocol(PROTOCOL)
    result = {"protocol_sha256": ev.PROTOCOL_SHA[PROTOCOL.name], "label_of_results": protocol["label_of_results"],
              "fragments": {}}
    deltas = []
    Image.MAX_IMAGE_PIXELS = None  # Published label images exceed PIL's default bomb limit.
    for fragment, entry in protocol["fragments"].items():
        nominal = Path(entry["nominal"])
        labels_path = Path("data/phase11/raw/inklabels.png") if fragment == "Frag4" else nominal / "inklabels.png"
        if fragment == "Frag4" and ev.sha(labels_path) != ev.FRAG4_LABELS_SHA:
            raise ValueError("Frag4 labels changed since phase 12")
        labels = np.asarray(Image.open(labels_path).convert("L")) > 127
        nom = load(nominal, labels, lambda lab, roi: sample_labels(lab, roi["native_origin_rc"], 0))
        real = load(ev.WORK / fragment.lower(), labels,
                    lambda lab, roi: sample_labels_scaled(lab, roi["native_origin_rc"], roi["steps_native_px"]))
        rois, pool = {}, []
        for name, (maps, truth, valid, ok, roi) in real.items():
            n_maps, n_truth, n_valid, n_ok, _ = nom[name]
            row = {"pitch_row_vox": roi["pitch_row_vox"], "pitch_col_vox": roi["pitch_col_vox"],
                   "abs_cos_median": roi["abs_cos_median"], "distortion": distortion(roi),
                   "included": bool(ok and n_ok), "nominal": summary_of(n_maps, n_truth, n_valid) if n_ok else None,
                   "real": summary_of(maps, truth, valid) if ok else None}
            if row["included"]:
                row["delta_ROC_Z_out"] = row["real"]["ROC_Z_out"] - row["nominal"]["ROC_Z_out"]
                row["delta_ROC_Z_in"] = row["real"]["ROC_Z_in"] - row["nominal"]["ROC_Z_in"]
                row["delta_share_gt_0p5"] = row["real"]["share_Z_out_gt_0p5"] - row["nominal"]["share_Z_out_gt_0p5"]
                deltas.append(row["delta_ROC_Z_out"])
                pool.append((maps, truth, valid))
            rois[name] = row
        pooled = ev.pooled({s: np.hstack([p[0][s] for p in pool]) for s in ev.SCORES},
                           np.hstack([p[1] for p in pool]), np.hstack([p[2] for p in pool])) if pool else None
        included = [r for r in rois.values() if r["included"]]
        result["fragments"][fragment] = {
            "rois": rois, "pooled_real_Z_out": pooled and {k: pooled["Z_out"][k] for k in ("ROC_AUC", "ROC_AUC_95")},
            "mean_delta_ROC_Z_out": float(np.mean([r["delta_ROC_Z_out"] for r in included])) if included else None}
        print(fragment, "done", file=sys.stderr, flush=True)
    deltas = np.asarray(deltas)
    draws = np.random.default_rng(SEED).integers(0, len(deltas), (DRAWS, len(deltas)))
    lo, hi = np.percentile(deltas[draws].mean(1), [2.5, 97.5])
    frag_means = [e["mean_delta_ROC_Z_out"] for e in result["fragments"].values()
                  if e["mean_delta_ROC_Z_out"] is not None]
    rows = [r for e in result["fragments"].values() for r in e["rois"].values() if r["included"]]
    result["primary"] = {"included_rois": len(deltas), "mean_delta_ROC_Z_out": float(deltas.mean()),
                         "interval_95": [float(lo), float(hi)], "min_fragment_mean_delta": float(min(frag_means)),
                         "adopt_real_pitch": bool(lo > 0 and min(frag_means) >= -0.02)}
    result["secondary"] = {
        "mean_delta_ROC_Z_in": float(np.mean([r["delta_ROC_Z_in"] for r in rows])),
        "mean_delta_share_Z_out_gt_0p5": float(np.mean([r["delta_share_gt_0p5"] for r in rows])),
        "spearman_distortion_vs_delta": float(stats.spearmanr([r["distortion"] for r in rows],
                                                               [r["delta_ROC_Z_out"] for r in rows]).statistic)}
    Path(out).write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps({"primary": result["primary"], "secondary": result["secondary"],
                      "per_fragment": {f: (e["mean_delta_ROC_Z_out"], e["pooled_real_Z_out"])
                                       for f, e in result["fragments"].items()}}, indent=1))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cli.add_argument("--prepare", choices=sorted(ev.FILES))
    cli.add_argument("--report", type=Path)
    args = cli.parse_args()
    ev.use_protocol(PROTOCOL)
    if args.prepare:
        prepare(args.prepare)
    elif args.report:
        report(args.report)
    else:
        cli.error("--prepare FRAGMENT or --report")
