"""Verify the grid averaging identity and measure the top-k margins of the central CPU pilot."""

import argparse
import json
import math
from itertools import product
from pathlib import Path

import numpy as np
import phase18_cpu_pilot as pilot
import phase18_eval as phase
from phase6_cuda import WEIGHTS_SHA


def phase_mosaics(predictions):
    """Return the common core under each of the four non-overlapping grid phases."""
    mosaics = []
    for dv, du in product((0, pilot.TILE // 2), repeat=2):
        field = np.full((pilot.PATCH, pilot.PATCH), np.nan)
        for (v, u), tile in predictions.items():
            if (v % pilot.TILE, u % pilot.TILE) == (dv, du):
                field[v:v + pilot.TILE, u:u + pilot.TILE] = tile
        core = field[pilot.CORE, pilot.CORE]
        if not np.isfinite(core).all():
            raise ValueError(f"Incomplete core for grid offset {(dv, du)}")
        mosaics.append(core)
    return np.stack(mosaics)


def margin_check(reference, alternative, k):
    """A strict cutoff gap greater than twice the maximum change certifies top-k membership."""
    a, b = np.asarray(reference, dtype=np.float64), np.asarray(alternative, dtype=np.float64)
    if a.shape != b.shape or not 0 < k < a.size or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("Top-k needs finite, co-located scores and 0 < k < N")
    cutoff = np.partition(a.ravel(), (-k - 1, -k))
    gap = float(cutoff[-k] - cutoff[-k - 1])
    change = float(np.abs(a - b).max())
    return {"top_k": k, "cutoff_gap": gap, "max_change": change, "certifies_top_k": gap > 2 * change}


def run(phase6, threads):
    import torch

    torch.set_num_threads(threads)
    torch.use_deterministic_algorithms(True)
    protocol = phase.read_protocol()
    work = phase.work_dir(protocol)
    mask = phase.load_mask(work / "raw" / protocol["fragment"]["mask"])
    origin = pilot.choose_patch(mask)
    stack = phase.open_stack(protocol)
    infer = phase.make_tile_infer(phase6, torch.device("cpu"))
    window = protocol["inputs"]["primary_window"]
    maps, diagnostics = {}, {}
    k = math.ceil(0.01 * pilot.TILE**2)
    for order in pilot.ORDERS:
        tiles, _ = pilot.predict_tiles(stack, infer, window, origin, order, "central")
        mosaics = phase_mosaics(tiles)
        uniform = pilot.stitch_core(tiles, 128, uniform=True)
        averaged = mosaics.mean(axis=0).astype(np.float32)
        delta = float(np.abs(uniform - averaged).max())
        if delta > np.finfo(np.float32).eps:
            raise ValueError(f"Uniform overlap differs from averaging the four grid phases: {delta}")
        maps[order] = {256: mosaics[0].astype(np.float32), 128: pilot.stitch_core(tiles, 128)}
        diagnostics[order] = {
            "uniform_vs_four_phase_mean_max_error": delta,
            "mean_pixel_range_across_grid_phases": float(np.ptp(mosaics, axis=0).mean()),
            "grid_shift_256": margin_check(maps[order][256], mosaics[-1].astype(np.float32), k),
            "hann_at_stride_128": margin_check(uniform, maps[order][128], k),
        }
    return {"scope": "central PHerc0343P core, score geometry without labels or infrared",
            "protocol_sha256": phase.PROTOCOL_SHA[phase.PROTOCOL.name],
            "prepare_manifest_sha256": phase.sha(phase.PREPARE_JSON), "weights_sha256": WEIGHTS_SHA,
            "torch": torch.__version__, "cpu_threads": threads, "window_inclusive": window,
            "core_origin_vu": [v + pilot.CORE.start for v in origin], "core_pixels": pilot.TILE**2,
            "grid_offsets_vu": [[0, 0], [0, 128], [128, 0], [128, 128]], "within_order": diagnostics,
            "depth_reversal": {stride: {**margin_check(maps["Z_in"][stride], maps["Z_out"][stride], k),
                                        **pilot.compare(maps["Z_in"][stride], maps["Z_out"][stride])}
                               for stride in pilot.STRIDES}}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--phase6", type=Path, default=Path("data/phase6"))
    cli.add_argument("--threads", type=int, default=2)
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    result = run(args.phase6, args.threads)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
