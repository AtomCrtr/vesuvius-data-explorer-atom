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


def choose_patch(mask):
    """Choose the fully masked core nearest the mask centroid, with V/U tie-breaking."""
    count = mask.sum()
    if count == 0:
        raise ValueError("Empty fragment mask")
    cv, cu = (np.dot(np.arange(n), mask.sum(axis=axis)) / count
              for axis, n in [(1, mask.shape[0]), (0, mask.shape[1])])
    candidates = [((v + TILE - cv) ** 2 + (u + TILE - cu) ** 2, v, u)
                  for v, u in phase.tile_origins((mask.shape[0] - TILE, mask.shape[1] - TILE), TILE)
                  if mask[v + CORE.start:v + CORE.stop, u + CORE.start:u + CORE.stop].all()]
    if not candidates:
        raise ValueError("No aligned patch with a fully masked core")
    _, v, u = min(candidates)
    return v, u


def local_origins(stride):
    return phase.tile_origins((PATCH, PATCH), stride)


def stitch_core(predictions, stride):
    """Use the phase 18 Hann rule and keep the core covered by every neighboring tile."""
    acc, weights = np.zeros((PATCH, PATCH)), np.zeros((PATCH, PATCH))
    weight = phase.hann()
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


def run(phase6, threads):
    import torch

    started = perf_counter()
    torch.set_num_threads(threads)
    torch.use_deterministic_algorithms(True)
    protocol = phase.read_protocol()
    work = phase.work_dir(protocol)
    mask = phase.load_mask(work / "raw" / protocol["fragment"]["mask"])
    v0, u0 = choose_patch(mask)
    stack = phase.open_stack(protocol)
    infer = phase.make_tile_infer(phase6, torch.device("cpu"))
    window = protocol["inputs"]["primary_window"]
    maps = {}
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
            print(f"{order} {index}/9 {(vv, uu)} · {tile_seconds[-1]:.1f} s", flush=True)
        for stride in STRIDES:
            maps[order, stride] = stitch_core(predictions, stride)
    return {"scope": "one PHerc0343P core; score agreement without ink labels or infrared",
            "protocol_sha256": phase.PROTOCOL_SHA[phase.PROTOCOL.name],
            "prepare_manifest_sha256": phase.sha(phase.PREPARE_JSON), "weights_sha256": WEIGHTS_SHA,
            "torch": torch.__version__, "cpu_threads": threads, "elapsed_s": round(perf_counter() - started, 1),
            "median_tile_inference_s": round(float(np.median(tile_seconds)), 2),
            "window_inclusive": window, "patch_origin_vu": [v0, u0], "patch_size_px": PATCH,
            "core_origin_vu": [v0 + CORE.start, u0 + CORE.start], "core_size_px": TILE,
            "unique_tile_inferences": len(tile_seconds),
            "order_effect": {stride: compare(maps["Z_in", stride], maps["Z_out", stride]) for stride in STRIDES},
            "tiling_effect": {order: compare(maps[order, 256], maps[order, 128]) for order in ORDERS}}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--phase6", type=Path, default=Path("data/phase6"))
    cli.add_argument("--threads", type=int, default=2)
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    result = run(args.phase6, args.threads)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
