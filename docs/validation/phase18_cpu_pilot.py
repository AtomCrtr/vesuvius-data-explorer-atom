"""Compare the four phase 18 conditions on one unlabeled PHerc0343P region (CPU)."""

import argparse
import json
from pathlib import Path
from time import perf_counter

import numpy as np
import phase18_eval as phase
from phase6_cuda import WEIGHTS_SHA

from vesuvius_data_explorer.core.consensus import rank_agreement
from vesuvius_data_explorer.core.ink_disagreement import correlations

TILE = phase.TILE
PATCH = 2 * TILE
CORE = slice(TILE // 2, TILE + TILE // 2)
STRIDES = (128, 256)
ORDERS = ("Z_in", "Z_out")


def choose_patch(mask, *, target_vu=None, excluded=()):
    """Choose the fully masked core nearest the target, with V/U tie-breaking."""
    if target_vu is None:
        count = mask.sum()
        if count == 0:
            raise ValueError("Empty fragment mask")
        target_vu = (np.dot(np.arange(mask.shape[0]), mask.sum(axis=1)) / count,
                     np.dot(np.arange(mask.shape[1]), mask.sum(axis=0)) / count)
    cv, cu = target_vu
    candidates = [((v + TILE - cv) ** 2 + (u + TILE - cu) ** 2, v, u)
                  for v, u in phase.tile_origins((mask.shape[0] - TILE, mask.shape[1] - TILE), TILE)
                  if all(abs(v - ev) >= PATCH or abs(u - eu) >= PATCH for ev, eu in excluded)
                  if mask[v + CORE.start:v + CORE.stop, u + CORE.start:u + CORE.stop].all()]
    if not candidates:
        raise ValueError("No aligned patch with a fully masked core")
    _, v, u = min(candidates)
    return v, u


def select_region(mask, region):
    """Anchor the outer regions to the quartiles of the mask's cumulative row area."""
    central = choose_patch(mask)
    if region == "central":
        return central
    row_area = mask.sum(axis=1).cumsum()
    col_centroid = np.dot(np.arange(mask.shape[1]), mask.sum(axis=0)) / row_area[-1]
    upper_target = np.searchsorted(row_area, 0.25 * row_area[-1]), col_centroid
    upper = choose_patch(mask, target_vu=upper_target, excluded=(central,))
    if region == "upper":
        return upper
    lower_target = np.searchsorted(row_area, 0.75 * row_area[-1]), col_centroid
    return choose_patch(mask, target_vu=lower_target, excluded=(central, upper))


def local_origins(stride):
    return phase.tile_origins((PATCH, PATCH), stride)


def stitch_core(predictions, stride, *, uniform=False):
    """Keep the core covered by every neighboring tile, using Hann or uniform weights."""
    acc, weights = np.zeros((PATCH, PATCH)), np.zeros((PATCH, PATCH))
    weight = 1.0 if uniform else phase.hann()
    for v, u in local_origins(stride):
        sl = np.s_[v:v + TILE, u:u + TILE]
        acc[sl] += weight * predictions[v, u]
        weights[sl] += weight
    return (acc[CORE, CORE] / weights[CORE, CORE]).astype(np.float32)


def compare(a, b):
    a, b = a.ravel(), b.ravel()
    return {**correlations(a, b),
            "mean_absolute_score_difference": float(np.abs(a - b).mean(dtype=np.float64)),
            "top_1_percent": rank_agreement(a, b, (0.01,))[0]}


def run(phase6, threads, region="central"):
    import torch

    started = perf_counter()
    torch.set_num_threads(threads)
    torch.use_deterministic_algorithms(True)
    protocol = phase.read_protocol()
    work = phase.work_dir(protocol)
    mask = phase.load_mask(work / "raw" / protocol["fragment"]["mask"])
    v0, u0 = select_region(mask, region)
    stack = phase.open_stack(protocol)
    infer = phase.make_tile_infer(phase6, torch.device("cpu"))
    window = protocol["inputs"]["primary_window"]
    maps = {}
    alternatives = {}
    tile_seconds = []
    for order in ORDERS:
        predictions = {}
        for index, (v, u) in enumerate(local_origins(128), 1):
            vv, uu = v0 + v, u0 + u
            tile = phase.read_stack_window(stack, window, order, slice(vv, vv + TILE), slice(uu, uu + TILE))
            start = perf_counter()
            predictions[v, u] = infer(tile)
            if not np.isfinite(predictions[v, u]).all():
                raise ValueError(f"Non-finite scores on {order} tile {(vv, uu)}")
            tile_seconds.append(perf_counter() - start)
            print(f"{region} {order} {index}/9 {(vv, uu)} · {tile_seconds[-1]:.1f} s", flush=True)
        for stride in STRIDES:
            maps[order, stride] = stitch_core(predictions, stride)
        alternatives[order] = {"shifted_256": predictions[TILE // 2, TILE // 2].astype(np.float32),
                               "uniform_128": stitch_core(predictions, 128, uniform=True)}
    return {"scope": "one PHerc0343P core; score agreement without ink labels or infrared",
            "protocol_sha256": phase.PROTOCOL_SHA[phase.PROTOCOL.name],
            "prepare_manifest_sha256": phase.sha(phase.PREPARE_JSON), "weights_sha256": WEIGHTS_SHA,
            "torch": torch.__version__, "cpu_threads": threads, "elapsed_s": round(perf_counter() - started, 1),
            "median_tile_inference_s": round(float(np.median(tile_seconds)), 2),
            "window_inclusive": window, "region": region, "patch_origin_vu": [v0, u0], "patch_size_px": PATCH,
            "core_origin_vu": [v0 + CORE.start, u0 + CORE.start], "core_size_px": TILE,
            "unique_tile_inferences": len(tile_seconds),
            "order_effect": {stride: compare(maps["Z_in", stride], maps["Z_out", stride]) for stride in STRIDES},
            "tiling_effect": {order: compare(maps[order, 256], maps[order, 128]) for order in ORDERS},
            "order_effect_sensitivity": {recipe: compare(alternatives["Z_in"][recipe], alternatives["Z_out"][recipe])
                                         for recipe in alternatives["Z_in"]},
            "tiling_components": {
                order: {
                    "shift_256_grid_by_128": compare(maps[order, 256], alternatives[order]["shifted_256"]),
                    "overlap_with_uniform_weights": compare(maps[order, 256], alternatives[order]["uniform_128"]),
                    "add_hann_at_stride_128": compare(alternatives[order]["uniform_128"], maps[order, 128]),
                }
                for order in ORDERS
            }}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--phase6", type=Path, default=Path("data/phase6"))
    cli.add_argument("--threads", type=int, default=2)
    cli.add_argument("--region", choices=("central", "upper", "lower"), default="central")
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    result = run(args.phase6, args.threads, args.region)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
