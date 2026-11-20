"""Extend the verified A+/A- intervention to the complete historical UV raster."""

import argparse
import json
import platform
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter
from urllib.error import HTTPError

import numpy as np
from phase6_cuda import CHECKPOINT, CODE, COMMIT, WEIGHTS_SHA, digest, prepare_tile
from phase7_experiment import (
    CHUNK,
    STACK_SHAPE,
    fetch,
    grid,
    read_tile,
    tile_keys,
    working_set_peak,
)


def prepare(work, previous):
    prior = json.loads((previous/"input-plan.json").read_bytes())
    old = {tuple(row["key"]): row for row in prior["chunks"]}
    storage = work/"chunks"
    storage.mkdir(parents=True, exist_ok=True)
    header = previous/"chunks"/"zarray.json"
    if digest(header) != prior["zarr_header_sha256"]:
        raise ValueError("The verified Zarr header changed")
    z = json.loads(header.read_bytes())
    if (tuple(z["shape"]), tuple(z["chunks"]), z["dtype"], z["compressor"], z["order"],
            z["dimension_separator"], z["fill_value"]) != (STACK_SHAPE, CHUNK, "|u1", None, "C", "/", 0):
        raise ValueError("Unexpected Zarr header")
    public = prior["uri"].replace("s3://vesuvius-challenge-open-data/",
                                  "https://vesuvius-challenge-open-data.s3.amazonaws.com/")
    tiles = [(v, u) for v in grid(STACK_SHAPE[1]) for u in grid(STACK_SHAPE[2])]
    keys = sorted({key for v, u in tiles for key in tile_keys(v, u)})
    chunk_bytes = int(np.prod(CHUNK))
    if len(set(keys)-old.keys())*chunk_bytes > 128*2**20:
        raise ValueError("Too many additional chunks")

    def load(key):
        name = f"{key[0]}-{key[1]}.raw"
        cached = key in old
        path = (previous/"chunks" if cached else storage)/name
        absent = path.with_suffix(".absent")
        if not path.exists() and not cached:
            try:
                raw = fetch(f"{public}/0/0/{key[0]}/{key[1]}", chunk_bytes)
            except HTTPError as error:
                if error.code != 404:
                    raise
                raw = bytes(chunk_bytes)
                absent.touch()
            if len(raw) != chunk_bytes:
                raise ValueError(f"Unexpected chunk length at {key}")
            stage = path.with_suffix(".tmp")
            stage.write_bytes(raw)
            stage.replace(path)
        if path.stat().st_size != chunk_bytes:
            raise ValueError(f"Invalid chunk length at {key}")
        hash_value = digest(path)
        if cached and hash_value != old[key]["sha256"]:
            raise ValueError(f"Phase 7 chunk changed at {key}")
        if cached and absent.is_file() != (old[key]["storage"] == "absent_zarr_fill"):
            raise ValueError(f"Phase 7 mask provenance changed at {key}")
        return {"key": key, "sha256": hash_value, "previous_cache": cached,
                "storage": "absent_zarr_fill" if absent.is_file() else "s3_object",
                "additional_payload_bytes": chunk_bytes if not cached and not absent.is_file() else 0}

    with ThreadPoolExecutor(max_workers=5) as pool:
        chunks = list(pool.map(load, keys))
    report = {"uri": prior["uri"], "shape_zvu": STACK_SHAPE, "layers": [28, 90], "axes": ["z", "v", "u"],
              "pixel_size_um": 2.215, "tile_size": 256, "stride": 128, "tiles": tiles, "chunks": chunks,
              "prior_plan_sha256": digest(previous/"input-plan.json"),
              "new_payload_bytes": sum(row["additional_payload_bytes"] for row in chunks)}
    (work/"input-plan.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    return report


def open_chunks(metadata, work, previous):
    result = {}
    for row in metadata["chunks"]:
        v, u = row["key"]
        source = previous if row["previous_cache"] else work
        path = source/"chunks"/f"{v}-{u}.raw"
        if digest(path) != row["sha256"]:
            raise ValueError("A CT chunk changed after the plan was frozen")
        result[v, u] = np.memmap(path, "u1", "r", shape=CHUNK)
    return result


def run(work, previous, phase6, output, *, repeat=False):
    import torch

    plan_path = work/"input-plan.json"
    plan = json.loads(plan_path.read_bytes())
    prior = json.loads((previous/"cuda"/"run.json").read_bytes())
    old_raw = previous/"cuda"/"tiles.npz"
    expected = {"weights_sha256": WEIGHTS_SHA, "architecture_revision": COMMIT,
                "inference": "eval_fp32_no_tf32_deterministic_cudnn"}
    if digest(old_raw) != prior["outputs_sha256"] or any(prior["inputs"][k] != x for k, x in expected.items()):
        raise ValueError("Phase 7 outputs do not match the same audited checkpoint and settings")
    if prior["inputs"]["plan_sha256"] != plan["prior_plan_sha256"]:
        raise ValueError("Phase 7 chunks and inferred tiles belong to different plans")
    ckpt = phase6/"canonical"/CHECKPOINT
    if digest(ckpt) != WEIGHTS_SHA or any(digest(phase6/"villa"/p) != h for p, h in CODE.items()):
        raise ValueError("The checkpoint or the audited model code changed")
    sys.path.insert(0, str((phase6/"villa").resolve()))
    from model_resnet3d_3d_decoder import RegressionModel, _strip_known_prefixes

    dev = torch.device("cuda:0")
    torch.cuda.set_device(dev)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.allow_tf32 = torch.backends.cuda.matmul.allow_tf32 = False
    free, total = torch.cuda.mem_get_info()
    if free < 3*2**30:
        raise RuntimeError("Insufficient VRAM")
    torch.cuda.set_per_process_memory_fraction(min(9*2**30, free-512*2**20)/total)
    runtime = {"python": platform.python_version(), "torch": torch.__version__, "cuda": torch.version.cuda,
               "cudnn": torch.backends.cudnn.version(), "gpu": torch.cuda.get_device_name()}
    if prior["inputs"]["runtime"] != runtime:
        raise ValueError("Phase 7 cache was created in a different runtime")
    fingerprints = {"runtime": runtime, **expected, "input_plan_sha256": digest(plan_path),
                    "prior_tiles_sha256": digest(old_raw), "script_sha256": digest(Path(__file__)),
                    "repeat": repeat}
    output.mkdir(parents=True, exist_ok=True)
    report_path, tiles_path = output/"run.json", output/"tiles.npz"
    if report_path.is_file() and tiles_path.is_file():
        cached = json.loads(report_path.read_bytes())
        if cached["fingerprints"] == fingerprints and cached["sha256_raw_tiles"] == digest(tiles_path):
            print("Verified cache hit")
            return cached
    chunks = open_chunks(plan, work, previous)
    with np.load(old_raw, allow_pickle=False) as archive:
        old = {name: archive[name] for name in archive.files}
    old_indices = {tuple(origin): i for i, origin in enumerate(old["origins"])}
    positions = [tuple(pos) for pos in plan["tiles"]]
    if repeat:
        eligible = [pos for pos in positions if pos not in old_indices and np.any(read_tile(chunks, *pos))]
        positions = [eligible[i] for i in np.linspace(0, len(eligible)-1, min(8, len(eligible)), dtype=int)]
    started = perf_counter()
    blob = torch.load(ckpt, map_location="cpu", weights_only=True, mmap=True)
    state = _strip_known_prefixes(blob["state_dict"])
    with torch.device("meta"):
        model = RegressionModel(with_norm=any(k.startswith("normalization.") for k in state))
    model.load_state_dict(state, strict=True, assign=True)
    model = model.to(dev).eval()
    del blob, state
    torch.cuda.synchronize()
    load_ms = 1000*(perf_counter()-started)

    def predict(tile, reversed_z):
        prepared, _ = prepare_tile(tile, reversed_z)
        image = torch.from_numpy(prepared).to(dev)
        torch.cuda.synchronize()
        t0 = perf_counter()
        with torch.inference_mode():
            logits = model(image)
            full = torch.nn.functional.interpolate(logits.sigmoid(), size=(256, 256),
                                                    mode="bilinear", align_corners=False)
        torch.cuda.synchronize()
        return (logits[0, 0].cpu().numpy(), full[0, 0].cpu().numpy(), 1000*(perf_counter()-t0))

    warm = read_tile(chunks, 512, 512)
    for orientation in (False, True):
        predict(warm, orientation)
    torch.cuda.reset_peak_memory_stats()
    records, maps, masks = [], {name: [] for name in old if name not in ("valid", "origins")}, []
    for pos in positions:
        tile = read_tile(chunks, *pos)
        mask = np.any(tile, axis=0)
        masks.append(mask)
        row = {"origin_vu": pos, "valid_pixels": int(mask.sum())}
        if pos in old_indices and not repeat:
            i = old_indices[pos]
            np.testing.assert_array_equal(mask, old["valid"][i])
            for name in maps:
                maps[name].append(old[name][i])
            row["cache"] = "phase7"
        elif not mask.any():
            for name in maps:
                maps[name].append(np.full((64, 64) if name.endswith("logits") else (256, 256), np.nan, "f4"))
            row["cache"] = "empty_support"
        else:
            for label, reverse in (("A_plus", False), ("A_minus", True)):
                logits, scores, time_ms = predict(tile, reverse)
                if not np.isfinite(logits).all() or not np.isfinite(scores).all():
                    raise ValueError("Invalid model output")
                maps[label+"_logits"].append(logits)
                maps[label+"_scores"].append(scores)
                row[label+"_ms"] = time_ms
            row["cache"] = "computed"
        records.append(row)
    np.savez_compressed(tiles_path, origins=positions, valid=masks, **maps)
    report = {"fingerprints": fingerprints, "sha256_raw_tiles": digest(tiles_path), "tiles": records,
              "load_ms": load_ms, "peak_allocated_vram": torch.cuda.max_memory_allocated(),
              "peak_reserved_vram": torch.cuda.max_memory_reserved(), "peak_ram": working_set_peak()}
    report_path.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("work", type=Path)
    cli.add_argument("--phase7", type=Path, default=Path("data/phase7"))
    cli.add_argument("--phase6", type=Path, default=Path("data/phase6"))
    cli.add_argument("--prepare", action="store_true")
    cli.add_argument("--repeat", action="store_true")
    args = cli.parse_args()
    if args.prepare:
        answer = prepare(args.work, args.phase7)
        print(len(answer["tiles"]), len(answer["chunks"]), answer["new_payload_bytes"])
    else:
        report = run(args.work, args.phase7, args.phase6,
                     args.work/("cuda-repeat" if args.repeat else "cuda"), repeat=args.repeat)
        print(len(report["tiles"]), report["sha256_raw_tiles"])
