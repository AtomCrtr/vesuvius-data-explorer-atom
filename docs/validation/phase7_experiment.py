"""Freeze the PHerc0500P2 tile plan, run verified A in both orders, and cache raw outputs."""

import argparse
import ctypes
import json
import platform
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter
from urllib.error import HTTPError
from urllib.request import urlopen

import numpy as np
from phase6_cuda import CHECKPOINT, CODE, COMMIT, SHAPE, WEIGHTS_SHA, digest, prepare_tile

STACK_SHAPE = (118, 1160, 1400)
CHUNK = (118, 128, 128)
REGIONS = {"review": (388, 508, 384, 384), "distant": (896, 768, 128, 256)}


def grid(length, tile=256, stride=128):
    end = max(0, length-tile)
    return sorted({*range(0, end+1, stride), end})


def plan(regions=REGIONS):
    tiles = set()
    for v, u, h, w in regions.values():
        tiles.update((y, x) for y in grid(STACK_SHAPE[1]) for x in grid(STACK_SHAPE[2])
                     if y < v+h and y+256 > v and x < u+w and x+256 > u)
    return sorted(tiles)


def tile_keys(v, u):
    return [(y, x) for y in range(v//128, (v+255)//128+1)
            for x in range(u//128, (u+255)//128+1)]


def read_tile(chunks, v, u):
    result = np.empty(SHAPE, np.uint8)
    for y, x in tile_keys(v, u):
        oy, ox = y*128-v, x*128-u
        a, b, c, d = max(0, oy), min(256, oy+128), max(0, ox), min(256, ox+128)
        result[:, a:b, c:d] = chunks[y, x][28:90, a-oy:b-oy, c-ox:d-ox]
    return result


def fetch(url, limit):
    with urlopen(url, timeout=40) as response:
        data = response.read(limit+1)
    if len(data) > limit:
        raise ValueError(f"Response exceeds the download budget: {url}")
    return data


def prepare(work, audit_path):
    info = json.loads(audit_path.read_bytes())
    uri = info["stack"]["uri"]
    public = uri.replace("s3://vesuvius-challenge-open-data/",
                         "https://vesuvius-challenge-open-data.s3.amazonaws.com/")
    folder = work/"chunks"
    folder.mkdir(parents=True, exist_ok=True)
    header = folder/"zarray.json"
    if not header.is_file():
        header.write_bytes(fetch(public+"/0/.zarray", 32768))
    z = json.loads(header.read_bytes())
    if (tuple(z["shape"]), tuple(z["chunks"]), z["dtype"], z["compressor"], z["order"],
            z["dimension_separator"], z["fill_value"]) != (STACK_SHAPE, CHUNK, "|u1", None, "C", "/", 0):
        raise ValueError("Unexpected volume layout")
    keys = sorted({key for v, u in plan() for key in tile_keys(v, u)})
    chunk_bytes = int(np.prod(CHUNK))
    if chunk_bytes*len(keys) > 128*2**20:
        raise ValueError("The fixed plan exceeds its network budget")

    def load(key):
        path = folder/f"{key[0]}-{key[1]}.raw"
        absent = path.with_suffix(".absent")
        if not path.is_file():
            try:
                data = fetch(f"{public}/0/0/{key[0]}/{key[1]}", chunk_bytes)
            except HTTPError as error:
                if error.code != 404:
                    raise
                data = bytes(chunk_bytes)
                absent.touch()
            if len(data) != chunk_bytes:
                raise ValueError("Partial chunk")
            stage = path.with_suffix(".tmp")
            stage.write_bytes(data)
            stage.replace(path)
        if path.stat().st_size != chunk_bytes:
            raise ValueError("Incomplete cached chunk")
        missing = absent.is_file()
        return {"key": key, "sha256": digest(path), "payload_bytes": 0 if missing else chunk_bytes,
                "storage": "absent_zarr_fill" if missing else "s3_object"}

    with ThreadPoolExecutor(max_workers=5) as workers:
        records = list(workers.map(load, keys))
    document = {"uri": uri, "zarr_header_sha256": digest(header), "shape_zvu": STACK_SHAPE,
                "axes": ["z", "v", "u"], "layers": [28, 90], "uv_pitch_um": 2.215,
                "stride": 128, "tiles": plan(), "regions_vuhw": REGIONS, "chunks": records,
                "data_bytes": sum(r["payload_bytes"] for r in records)}
    (work/"input-plan.json").write_text(json.dumps(document, indent=2)+"\n", encoding="utf-8")
    return document


def working_set_peak():
    if sys.platform != "win32":
        return None
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD),
                    ("peak", ctypes.c_size_t), ("other", ctypes.c_size_t*7)]

    data = Counters(cb=ctypes.sizeof(Counters))
    ctypes.windll.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    ok = ctypes.windll.psapi.GetProcessMemoryInfo(
        wintypes.HANDLE(ctypes.windll.kernel32.GetCurrentProcess()), ctypes.byref(data), data.cb)
    return int(data.peak) if ok else None


def run(work, phase6, audit_path, output):
    import torch

    meta = json.loads((work/"input-plan.json").read_bytes())
    audit = json.loads(audit_path.read_bytes())
    if audit["available_for_intervention"] != ["A"] or audit["public_A"]["sha256"] != WEIGHTS_SHA:
        raise ValueError("The current experiment requires explicitly audited A and absent B")
    ckpt = phase6/"canonical"/CHECKPOINT
    if not ckpt.is_file() or digest(ckpt) != WEIGHTS_SHA:
        raise ValueError("The pinned A checkpoint is missing or altered")
    for name, expected in CODE.items():
        if digest(phase6/"villa"/name) != expected:
            raise ValueError(f"Source code changed: {name}")
    sys.path.insert(0, str((phase6/"villa").resolve()))
    from model_resnet3d_3d_decoder import RegressionModel, _strip_known_prefixes

    device = torch.device("cuda:0")
    torch.cuda.set_device(device)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.allow_tf32 = torch.backends.cuda.matmul.allow_tf32 = False
    free, maximum = torch.cuda.mem_get_info(device)
    if free < 3*2**30:
        raise RuntimeError("Insufficient GPU memory")
    torch.cuda.set_per_process_memory_fraction(min(9*2**30, free-512*2**20)/maximum, device)
    runtime = {"python": platform.python_version(), "torch": torch.__version__, "cuda": torch.version.cuda,
               "cudnn": torch.backends.cudnn.version(), "gpu": torch.cuda.get_device_name(0)}
    inputs = {"plan_sha256": digest(work/"input-plan.json"), "audit_sha256": digest(audit_path),
              "script_sha256": digest(Path(__file__)), "runtime": runtime, "weights_sha256": WEIGHTS_SHA,
              "architecture_revision": COMMIT, "inference": "eval_fp32_no_tf32_deterministic_cudnn"}
    output.mkdir(parents=True, exist_ok=True)
    trace = output/"run.json"
    raw = output/"tiles.npz"
    if trace.exists() and raw.exists():
        prior = json.loads(trace.read_bytes())
        if prior["inputs"] == inputs and prior["outputs_sha256"] == digest(raw):
            print("Verified cache hit; inference skipped", flush=True)
            return prior
    chunks = {}
    for row in meta["chunks"]:
        y, x = row["key"]
        path = work/"chunks"/f"{y}-{x}.raw"
        if digest(path) != row["sha256"]:
            raise ValueError("CT chunk changed since the plan was frozen")
        chunks[y, x] = np.memmap(path, "u1", "r", shape=CHUNK)
    started = perf_counter()
    blob = torch.load(ckpt, map_location="cpu", weights_only=True, mmap=True)
    state = _strip_known_prefixes(blob["state_dict"])
    with torch.device("meta"):
        model = RegressionModel(with_norm=any(key.startswith("normalization.") for key in state))
    model.load_state_dict(state, strict=True, assign=True)
    model = model.eval().to(device)
    del blob, state
    torch.cuda.synchronize()
    load_ms = 1000*(perf_counter()-started)

    def forward(array):
        tensor = torch.from_numpy(array).to(device)
        torch.cuda.synchronize()
        start = perf_counter()
        with torch.inference_mode():
            logits = model(tensor)
            resized = torch.nn.functional.interpolate(logits.sigmoid(), size=(256, 256),
                                                       mode="bilinear", align_corners=False)
        torch.cuda.synchronize()
        ms = 1000*(perf_counter()-start)
        return logits[0, 0].cpu().numpy(), resized[0, 0].cpu().numpy(), ms

    tiles, rows, masks = {}, [], []
    warm = read_tile(chunks, 512, 512)
    for reverse in (False, True):
        forward(prepare_tile(warm, reverse)[0])
    torch.cuda.reset_peak_memory_stats(device)
    for v, u in meta["tiles"]:
        tile = read_tile(chunks, v, u)
        row = {"origin_vu": [v, u]}
        valid = np.any(tile, axis=0)
        masks.append(valid)
        for label, reverse in (("A_plus", False), ("A_minus", True)):
            inp, oriented_valid = prepare_tile(tile, reverse)
            np.testing.assert_array_equal(oriented_valid, valid)
            logits, values, ms = forward(inp)
            if not np.isfinite(logits).all() or not np.isfinite(values).all():
                raise ValueError("CUDA returned a non-finite value")
            arrays = tiles.setdefault(label, {"logits": [], "scores": []})
            arrays["logits"].append(logits)
            arrays["scores"].append(values)
            row[label+"_ms"] = ms
        rows.append(row)
    np.savez_compressed(raw, origins=np.array(meta["tiles"]), valid=masks,
                        **{f"{label}_{kind}": arrays[kind] for label, arrays in tiles.items()
                           for kind in ("logits", "scores")})
    result = {"inputs": inputs, "outputs_sha256": digest(raw), "tiles": rows,
              "matrix": {"A+": "measured", "A-": "measured",
                         "B+": "checkpoint_missing", "B-": "checkpoint_missing"},
              "load_ms": load_ms, "peak_allocated_vram": torch.cuda.max_memory_allocated(device),
              "peak_reserved_vram": torch.cuda.max_memory_reserved(device), "peak_ram": working_set_peak()}
    trace.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("--prepare", type=Path, metavar="PHASE5_PROVENANCE")
    parser.add_argument("--phase6", type=Path, default=Path("data/phase6"))
    parser.add_argument("--audit", type=Path, default=Path("docs/validation/phase7-checkpoints.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.prepare:
        report = prepare(args.work, args.prepare)
        print(f"{len(report['tiles'])} tiles, {report['data_bytes']} bytes")
    else:
        report = run(args.work, args.phase6, args.audit, args.output or args.work/"cuda")
        print(f"{len(report['tiles'])} tiles, {report['matrix']}")
