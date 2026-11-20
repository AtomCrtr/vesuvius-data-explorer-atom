"""Run the pinned public canonical checkpoint on one PHerc0500P2 tile in both orders."""

import argparse
import hashlib
import json
import platform
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter
from urllib.request import urlopen

import numpy as np

COMMIT = "baf5e605bb42a3d55a62b7c5c728e0908137225c"
CODE_URL = f"https://raw.githubusercontent.com/ScrollPrize/villa/{COMMIT}/ink-detection/optimized_inference"
CODE = {
    "model_resnet3d_3d_decoder.py": "7b2b2cfc6c7fb963a3da1bf128543ceadf8ad887f32a319bc0a38fb378f9e2ca",
    "models/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "models/resnetall.py": "2b49ac430d77bae189cf002ed9c2748f940a6cd92b809a23db6f7dba381afbf6",
}
HF_REVISION = "e154062e55513a1d4110f40fceeddb90eaa0f022"
CHECKPOINT = "r152_3ddec_v2_l5_epoch13.ckpt"
WEIGHTS_SHA = "36dd0de84b7b7aa6590184192c7415466cd8a1ba7c1e59f42c6373846373c3e0"
HF = f"https://huggingface.co/scrollprize/ink_canonical_2um/resolve/{HF_REVISION}"
SHAPE = (62, 256, 256)
TILE_SHA = "d5043abc0b66eeed3defb7d22053c617af346a2d05d2d622213fe4d84b35aea0"
CLIP = 200


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def prepare_tile(tile, reverse=False):
    """Match the public clip/divide rule and reverse Z only, preserving the input."""
    if tile.shape != SHAPE or tile.dtype != np.uint8:
        raise ValueError(f"Expected uint8 CT tile in ZVU order, shape {SHAPE}")
    valid = np.any(tile != 0, axis=0)
    ordered = tile[::-1] if reverse else tile
    tensor = np.minimum(ordered, CLIP).astype(np.float32) / CLIP
    return tensor[None, None], valid


def prepare_sources(work, manifest):
    """Fetch the pinned Python architecture and four uncompressed public CT chunks."""
    audit = json.loads(manifest.read_bytes())
    stack = audit["stack"]["uri"]
    https = stack.replace("s3://vesuvius-challenge-open-data/", "https://vesuvius-challenge-open-data.s3.amazonaws.com/")
    work.mkdir(parents=True, exist_ok=True)

    def fetch(url, size):
        with urlopen(url, timeout=45) as response:
            raw = response.read(size+1)
        if len(raw) > size:
            raise ValueError(f"Oversize response at {url}")
        return raw

    for relative, expected in CODE.items():
        path = work / "villa" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file():
            path.write_bytes(fetch(f"{CODE_URL}/{relative}", 1<<20))
        if digest(path) != expected:
            raise ValueError(f"Source digest mismatch at {path}")
    z = json.loads(fetch(https+"/0/.zarray", 32768))
    if (z["shape"], z["chunks"], z["dtype"], z["order"], z["compressor"]) != (
            [118, 1160, 1400], [118, 128, 128], "|u1", "C", None):
        raise ValueError("Unexpected published surface grid")
    tile = np.empty(SHAPE, "u1")
    blocks = {}
    keys = [(v, u) for v in (4, 5) for u in (4, 5)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for (v, u), raw in zip(keys, pool.map(
            lambda point: fetch(f"{https}/0/0/{point[0]}/{point[1]}", 118*128*128), keys
        )):
            blocks[f"0/0/{v}/{u}"] = hashlib.sha256(raw).hexdigest()
            tile[:, (v-4)*128:(v-3)*128, (u-4)*128:(u-3)*128] = (
                np.frombuffer(raw, "u1").reshape(118, 128, 128)[28:90])
    path = work / "ct-v512-u512.npy"
    np.save(path, tile)
    if digest(path) != TILE_SHA:
        raise ValueError("The published CT tile changed")
    meta = {"uri": stack, "origin_vu": [512, 512], "stop_vu": [768, 768], "layer_slice": [28, 90],
            "axes": ["z", "v", "u"], "resolution_um": 2.215, "chunk_hashes": blocks}
    (work/"ct-v512-u512.json").write_text(json.dumps(meta, indent=2)+"\n", encoding="utf-8")


def run(work, dtype):
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available")
    root = work / "villa"
    for name, sha in CODE.items():
        if digest(root/name) != sha:
            raise ValueError(f"Source digest mismatch at {name}")
    sys.path.insert(0, str(root.resolve()))
    from model_resnet3d_3d_decoder import RegressionModel, _strip_known_prefixes

    path = work/"canonical"/CHECKPOINT
    if digest(path) != WEIGHTS_SHA:
        raise ValueError("Checkpoint digest mismatch")
    tile_path = work/"ct-v512-u512.npy"
    if digest(tile_path) != TILE_SHA:
        raise ValueError("CT digest mismatch")
    tile = np.load(tile_path, allow_pickle=False)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cuda.matmul.allow_tf32 = False
    device = torch.device("cuda:0")
    free, total = torch.cuda.mem_get_info(device)
    budget = min(9*2**30, free - 512*2**20)
    if budget < 2**30:
        raise RuntimeError("Available GPU memory is below the pilot requirement")
    torch.cuda.set_per_process_memory_fraction(budget/total, device)

    started = perf_counter()
    blob = torch.load(path, map_location="cpu", weights_only=True, mmap=True)
    state = _strip_known_prefixes(blob["state_dict"])
    with torch.device("meta"):
        model = RegressionModel(with_norm=any(key.startswith("normalization.") for key in state))
    model.load_state_dict(state, strict=True, assign=True)
    model = model.eval().to(device)
    hyper_parameters = blob["hyper_parameters"]
    epoch, global_step = blob["epoch"], blob["global_step"]
    del blob, state
    torch.cuda.synchronize()
    load_ms = 1000*(perf_counter()-started)

    result = {
        "scope": "same public checkpoint, one tile, two Z orders, no stitching",
        "weights": {"uri": f"{HF}/{CHECKPOINT}", "sha256": WEIGHTS_SHA, "bytes": path.stat().st_size,
                    "epoch": epoch, "global_step": global_step, "hyper_parameters": hyper_parameters},
        "code": {"uri": CODE_URL, "sha256_files": CODE, "script_sha256": digest(Path(__file__))},
        "data": {**json.loads((work/"ct-v512-u512.json").read_bytes()), "npy_sha256": TILE_SHA},
        "runtime": {"python": platform.python_version(), "torch": torch.__version__,
                    "cuda": torch.version.cuda, "cudnn": torch.backends.cudnn.version(),
                    "device": torch.cuda.get_device_name(), "memory_bytes": total,
                    "free_start_bytes": free, "allocator_limit_bytes": budget},
        "settings": {"input_shape_bczvu": [1, 1, *SHAPE], "clip_and_divisor": CLIP,
                     "eval": True, "autocast": dtype, "tf32": False, "cudnn_deterministic": True,
                     "warmups_each": 1, "timed_runs_each": 3, "interpolation": "bilinear mask"},
        "load_ms": load_ms, "runs": {},
    }
    for name, reverse in (("normal", False), ("reversed_z", True)):
        image, valid = prepare_tile(tile, reverse)
        tensor = torch.from_numpy(image).to(device)
        rows, hashes = [], []
        torch.cuda.reset_peak_memory_stats(device)
        for i in range(4):
            torch.cuda.synchronize()
            started = perf_counter()
            with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16, enabled=dtype=="amp"):
                logits = model(tensor)
                resized = torch.nn.functional.interpolate(logits.sigmoid().float(), size=SHAPE[1:],
                                                            mode="bilinear", align_corners=False)
            torch.cuda.synchronize()
            if i:
                rows.append(1000*(perf_counter()-started))
                native = logits[0, 0].float().cpu().numpy()
                scores = resized[0, 0].cpu().numpy()
                if not np.isfinite(native).all() or not np.isfinite(scores).all():
                    raise ValueError("The network produced a non-finite score")
                hashes.append(hashlib.sha256(native.tobytes()).hexdigest())
            del logits, resized
        if len(set(hashes)) != 1:
            raise RuntimeError(f"Non-reproducible CUDA logits for {name}")
        np.save(work/f"{dtype}-{name}-logits.npy", native)
        np.save(work/f"{dtype}-{name}-scores.npy", scores)
        result["runs"][name] = {
            "times_ms": rows, "logits_shape": native.shape, "logits_range": [float(native.min()), float(native.max())],
            "logits_sha256": hashes[0], "scores_sha256": hashlib.sha256(scores.tobytes()).hexdigest(),
            "nonzero_input_stack_pixels": int(valid.sum()),
            "peak_allocated_bytes": torch.cuda.max_memory_allocated(device),
            "peak_reserved_bytes": torch.cuda.max_memory_reserved(device),
        }
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("--prepare", type=Path, metavar="PHASE5_PROVENANCE")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dtype", choices=("fp32", "amp"), default="fp32")
    args = parser.parse_args()
    if args.prepare:
        prepare_sources(args.work, args.prepare)
    else:
        if args.output is None:
            parser.error("--output is required to run the model")
        args.output.write_text(json.dumps(run(args.work, args.dtype), indent=2)+"\n", encoding="utf-8")
