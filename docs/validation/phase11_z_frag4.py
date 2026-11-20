"""Phase 11, step E (label-free part): depth-order sensitivity of checkpoint A on Frag4.

No ink label is read: this measures how much A's scores change between the two depth orders on an
out-of-recipe input, not whether they detect ink. Three steps, two interpreters:

    .venv/Scripts/python.exe docs/validation/phase11_z_frag4.py data/phase11 --prepare
    data/phase6-cuda/Scripts/python.exe docs/validation/phase11_z_frag4.py data/phase11
    .venv/Scripts/python.exe docs/validation/phase11_z_frag4.py data/phase11 --report docs/validation/phase11-z-frag4.json

Input recipe (documented in docs/PHASE11_CHECKPOINT_COMPATIBILITY.md):
- ROIs centred on patches 2 and 5 of the frozen geometric list of phase11_geometry.select_patches;
- 1024 x 1024 output pixels at 2.215 um from the 3.24 um surface volume (nominal pitch), 62 planes at
  depths (k - 58.5) * 2.215 um, k in [28, 90), around layer 32, trilinear in (layer, row, col);
- uint16 -> uint8 by >> 8 (Villa training reader), then the inference rule clip 200 / 200 (phase 6);
- Z_out: plane index increasing toward air (ascending Frag4 layers); Z_in: the reverse.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from phase6_cuda import CHECKPOINT, CODE, WEIGHTS_SHA, digest, prepare_tile  # noqa: E402

OUT_PX, OUT_UM, NATIVE_UM, PLANES, CENTER_A, CENTER_F4 = 1024, 2.215, 3.24, 62, 58.5, 32
DEPTHS_A = np.arange(28, 90)
TILE, STRIDE = 256, 128
ROI_PATCHES = (2, 5)


def layer_coords():
    """Fractional Frag4 layer of each A plane, ascending toward air (Z_out)."""
    return CENTER_F4 + (DEPTHS_A - CENTER_A) * OUT_UM / NATIVE_UM


def prepare(work):
    from phase11_geometry import PATCH, Ranges, select_patches
    from PIL import Image
    from scipy import ndimage

    mask = np.asarray(Image.open(work / "raw/mask.png")) > 0
    patches = select_patches(mask[::8, ::8])
    ranges = Ranges()
    span = OUT_PX * OUT_UM / NATIVE_UM  # ~700 native px
    layers = layer_coords()
    lo, hi = int(np.floor(layers.min())), int(np.ceil(layers.max()))
    manifest = {"layers_read": [lo, hi], "layer_coords": layers.tolist(), "rois": []}
    for index in ROI_PATCHES:
        r, c = patches[index]
        r0 = int(round(r + PATCH / 2 - span / 2)) - 2
        c0 = int(round(c + PATCH / 2 - span / 2)) - 2
        n = int(np.ceil(span)) + 5
        block = np.stack([ranges.layer(k, r0, c0, n, n) for k in range(lo, hi + 1)]).astype(np.float32)
        grid = 2 + np.arange(OUT_PX) * OUT_UM / NATIVE_UM
        yy, xx = np.meshgrid(grid, grid, indexing="ij")
        # Separable trilinear: linear between the two bracketing layers, then bilinear in-plane.
        below = np.floor(layers - lo).astype(int)
        frac = (layers - lo) - below
        planes = [(1 - f) * block[b] + f * block[min(b + 1, len(block) - 1)] for b, f in zip(below, frac)]
        resampled = np.stack([ndimage.map_coordinates(plane, [yy, xx], order=1, mode="nearest")
                              for plane in planes])
        u8 = (np.clip(resampled, 0, 65535).astype(np.uint16) >> 8).astype(np.uint8)
        roi_mask = ndimage.map_coordinates(mask[r0:r0 + n, c0:c0 + n].astype(np.float32),
                                           [yy, xx], order=0) > 0.5
        name = f"roi{index}"
        np.save(work / f"{name}-zout.npy", u8)
        np.save(work / f"{name}-mask.npy", roi_mask)
        manifest["rois"].append({"name": name, "patch_index": index, "native_origin_rc": [r0, c0],
                                 "native_size": n, "npy_sha256": digest(work / f"{name}-zout.npy"),
                                 "mask_fraction": float(roi_mask.mean())})
    (work / "z-frag4-prepare.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(json.dumps(manifest["rois"], indent=1))


def hann():
    w = np.hanning(TILE + 2)[1:-1]
    return np.outer(w, w).astype(np.float64)


def run(work, phase6):
    import torch

    manifest = json.loads((work / "z-frag4-prepare.json").read_bytes())
    ckpt = phase6 / "canonical" / CHECKPOINT
    if digest(ckpt) != WEIGHTS_SHA or any(digest(phase6 / "villa" / p) != h for p, h in CODE.items()):
        raise ValueError("The checkpoint or the audited model code changed")
    sys.path.insert(0, str((phase6 / "villa").resolve()))
    from model_resnet3d_3d_decoder import RegressionModel, _strip_known_prefixes

    dev = torch.device("cuda:0")
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.allow_tf32 = torch.backends.cuda.matmul.allow_tf32 = False
    blob = torch.load(ckpt, map_location="cpu", weights_only=True, mmap=True)
    state = _strip_known_prefixes(blob["state_dict"])
    with torch.device("meta"):
        model = RegressionModel(with_norm=any(k.startswith("normalization.") for k in state))
    model.load_state_dict(state, strict=True, assign=True)
    model = model.to(dev).eval()
    del blob, state
    weight = hann()
    origins = [(v, u) for v in range(0, OUT_PX - TILE + 1, STRIDE) for u in range(0, OUT_PX - TILE + 1, STRIDE)]
    outputs, repeat = {}, {}
    for roi in manifest["rois"]:
        path = work / f"{roi['name']}-zout.npy"
        if digest(path) != roi["npy_sha256"]:
            raise ValueError(f"{path} changed since --prepare")
        volume = np.load(path, allow_pickle=False)
        for label, reverse in (("Z_out", False), ("Z_in", True)):
            acc = np.zeros((OUT_PX, OUT_PX))
            wsum = np.zeros((OUT_PX, OUT_PX))
            for v, u in origins:
                tile = volume[:, v:v + TILE, u:u + TILE]
                if not tile.any():
                    continue
                prepared, _ = prepare_tile(tile, reverse)
                with torch.inference_mode():
                    logits = model(torch.from_numpy(prepared).to(dev))
                    score = torch.nn.functional.interpolate(logits.sigmoid(), size=(TILE, TILE),
                                                            mode="bilinear", align_corners=False)
                score = score[0, 0].cpu().numpy().astype(np.float64)
                if (v, u) == origins[len(origins) // 2]:
                    repeat.setdefault(f"{roi['name']}_{label}", []).append(score)
                acc[v:v + TILE, u:u + TILE] += weight * score
                wsum[v:v + TILE, u:u + TILE] += weight
            with np.errstate(invalid="ignore", divide="ignore"):
                outputs[f"{roi['name']}_{label}"] = (acc / wsum).astype(np.float32)
            outputs[f"{roi['name']}_weight"] = wsum.astype(np.float32)
        # Determinism: the central tile again, both orders, in the same process.
        v, u = origins[len(origins) // 2]
        for label, reverse in (("Z_out", False), ("Z_in", True)):
            prepared, _ = prepare_tile(volume[:, v:v + TILE, u:u + TILE], reverse)
            with torch.inference_mode():
                logits = model(torch.from_numpy(prepared).to(dev))
                score = torch.nn.functional.interpolate(logits.sigmoid(), size=(TILE, TILE),
                                                        mode="bilinear", align_corners=False)
            repeat[f"{roi['name']}_{label}"].append(score[0, 0].cpu().numpy().astype(np.float64))
    np.savez_compressed(work / "z-frag4-scores.npz", **outputs)
    run_report = {"weights_sha256": WEIGHTS_SHA, "torch": torch.__version__, "cuda": torch.version.cuda,
                  "gpu": torch.cuda.get_device_name(), "tiles_per_map": len(origins),
                  "inference": "eval_fp32_no_tf32_deterministic_cudnn",
                  "repeat_max_abs_diff": {k: float(np.abs(a[0] - a[1]).max()) for k, a in repeat.items()},
                  "scores_npz_sha256": digest(work / "z-frag4-scores.npz")}
    (work / "z-frag4-run.json").write_text(json.dumps(run_report, indent=1), encoding="utf-8")
    print(json.dumps(run_report, indent=1))


def report(work, out):
    from scipy import ndimage

    from vesuvius_data_explorer.core.ink_disagreement import correlations, top_masks
    from vesuvius_data_explorer.core.ink_spatial import block_interval

    manifest = json.loads((work / "z-frag4-prepare.json").read_bytes())
    run_report = json.loads((work / "z-frag4-run.json").read_bytes())
    if digest(work / "z-frag4-scores.npz") != run_report["scores_npz_sha256"]:
        raise ValueError("Scores changed since the CUDA run")
    scores = np.load(work / "z-frag4-scores.npz")
    result = {"blind": "ink labels not read; label-free comparison of two depth orders",
              "recipe": __doc__.split("Input recipe")[1].strip(), "prepare": manifest, "run": run_report,
              "rois": {}}
    for roi in manifest["rois"]:
        name = roi["name"]
        a, b = scores[f"{name}_Z_out"].astype(float), scores[f"{name}_Z_in"].astype(float)
        weight = scores[f"{name}_weight"]
        support = np.load(work / f"{name}-mask.npy")
        support = ndimage.binary_erosion(support, iterations=16)
        valid = support & (weight >= 0.25 * weight.max()) & np.isfinite(a) & np.isfinite(b)
        delta = np.abs(a - b)
        tops = {}
        for fraction in (0.01, 0.05, 0.10):
            ta, tb = top_masks(a, b, valid, fraction)
            tops[f"top{int(fraction * 100)}"] = {"shared": int((ta & tb).sum()), "selected_each": int(ta.sum()),
                                                 "jaccard": float((ta & tb).sum() / max((ta | tb).sum(), 1))}
        result["rois"][name] = {
            "valid_pixels": int(valid.sum()), "correlations": correlations(a[valid], b[valid]),
            "mean_abs_change": float(delta[valid].mean()),
            "mean_abs_change_block64": block_interval(delta, valid, block=64),
            "score_mean": {"Z_out": float(a[valid].mean()), "Z_in": float(b[valid].mean())},
            "score_p99": {"Z_out": float(np.quantile(a[valid], .99)), "Z_in": float(np.quantile(b[valid], .99))},
            "fraction_above_0.5": {"Z_out": float((a[valid] > .5).mean()), "Z_in": float((b[valid] > .5).mean())},
            "top_overlap": tops}
    Path(out).write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result["rois"], indent=1))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("work", type=Path)
    cli.add_argument("--phase6", type=Path, default=Path("data/phase6"))
    cli.add_argument("--prepare", action="store_true")
    cli.add_argument("--report", type=Path)
    args = cli.parse_args()
    if args.prepare:
        prepare(args.work)
    elif args.report:
        report(args.work, args.report)
    else:
        run(args.work, args.phase6)
