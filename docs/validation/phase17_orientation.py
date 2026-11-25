"""Phase 17. From the repository root: python docs/validation/phase17_orientation.py."""

import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import png
from phase11_geometry import PATCH, select_patches
from phase13_eval import AIR_ENDS, direction
from PIL import Image
from scipy import ndimage

HERE = Path(__file__).resolve().parent
PROTOCOL = HERE / "phase17-protocol.json"
PROTOCOL_SHA = {"phase17-protocol.json": "5e926b57b3a29ddcb8e9cfb5494cb494ff7810114f1b4cbe7f236cae12726542"}
SIDE = 64


def read_protocol(path):
    content = path.read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(content).hexdigest() != PROTOCOL_SHA.get(path.name):
        raise ValueError("Unknown or modified phase 17 protocol")
    return json.loads(content)


def fetch(meta, path, account, limit):
    """Reserve the whole attempt before opening the response. Reuse complete files."""
    size = meta["bytes"]
    if path.exists() and path.stat().st_size == size:
        return
    reserved = int(account.read_text()) + size
    if reserved > limit:
        raise ValueError("Fragment download budget exhausted")
    account.write_text(str(reserved))
    temp = path.with_suffix(".part")
    with urlopen(meta["url"], timeout=90) as response, temp.open("wb") as out:
        if response.status != 200 or int(response.headers["Content-Length"]) != size:
            raise ValueError("Unexpected response or changed asset")
        while block := response.read(min(1 << 20, size - out.tell())):
            out.write(block)
        if out.tell() != size:
            raise IOError("Incomplete download")
    temp.replace(path)


def stream_patches(path, boxes):
    """Scan grayscale rows without retaining the decoded plane."""
    with path.open("rb") as f:
        width, height, rows, info = png.Reader(file=f).read()
        if info["planes"] != 1 or info["bitdepth"] != 8:
            raise ValueError("Expected grayscale uint8")
        result = {box: np.empty((SIDE, SIDE), np.uint8) for box in boxes}
        for (r, c) in boxes:
            if min(r, c) < 0 or r + SIDE > height or c + SIDE > width:
                raise ValueError("Patch outside plane")
        for y, row in enumerate(rows):
            for (r, c), patch in result.items():
                if r <= y < r + SIDE:
                    patch[y-r] = row[c:c+SIDE]
    return result


def full_patches(path, boxes):
    with Image.open(path) as im:
        if im.mode != "L":
            raise ValueError("Expected grayscale uint8")
        return {(r, c): np.asarray(im.crop((c, r, c + SIDE, r + SIDE))) for r, c in boxes}


def load_mask(path):
    with Image.open(path) as im:
        if im.mode != "RGBA":
            raise ValueError("Expected published RGBA support")
        alpha = im.getchannel("A")
        gray = im.convert("L")
        support = np.asarray(alpha) > 0
        if gray.getextrema()[0] != gray.getextrema()[1] or alpha.getextrema()[0] == alpha.getextrema()[1]:
            support &= np.asarray(gray) > 0
    if not support.any() or support.all():
        raise ValueError("Uniform mask support")
    return support


def box_origins(patches):
    return [(r + PATCH // 2 - SIDE // 2, c + PATCH // 2 - SIDE // 2) for r, c in patches]


def summarize(samples, mask, patches, mapping, threshold):
    class Surface:
        def layer(self, k, r, c, h, w):
            return samples[mapping[k]][r, c]

    stats = direction(Surface(), mask, patches)
    profile = {mapping[k]: v for k, v in stats["layer_std_median"].items()}
    small, large = sorted(stats["end_mean_std"].values())
    ratio = large / small if small else (float("inf") if large else 1.0)
    return dict(layer_std_median=profile, end_mean_std=stats["end_mean_std"],
                ratio=ratio if np.isfinite(ratio) else "inf",
                air=stats["air"] if ratio >= threshold else "indéterminé",
                patch_count=len(patches), boxes_rc=box_origins(patches))


def analyze(fragment, base, files, protocol, reader):
    mask_name, = [n for n, m in files.items() if m["kind"] == "mask"]
    meta = files[mask_name]
    shape = meta["width"], meta["height"]
    for i in range(2, 64):
        m = files[f"layers/{i:02}.png"]
        if (m["width"], m["height"]) != shape or (m["bit_depth"], m["color_type"]) != (8, 0):
            raise ValueError("Layer geometry or format differs from inventory requirements")
    Image.MAX_IMAGE_PIXELS = shape[0] * shape[1]
    cache = Path("data/phase17") / fragment
    cache.mkdir(parents=True, exist_ok=True)
    account = cache / "reserved-bytes.txt"
    if not account.exists():
        account.write_text(str(33 * sum(m["kind"] != "metadata_only" for m in files.values())))
    hashes = {}

    def asset(name):
        item = files[name]
        if item["kind"] not in ("mask", "layer") or item["url"] != base + name:
            raise ValueError("Unexpected asset")
        path = cache / Path(name).name
        fetch(item, path, account, protocol["budget_bytes_per_fragment"])
        with path.open("rb") as f:
            hashes[name] = hashlib.file_digest(f, "sha256").hexdigest()
        with Image.open(path) as im:
            if im.size != shape:
                raise ValueError("Geometry changed since inventory")
        return path

    mask = load_mask(asset(mask_name))
    grid = mask[::8, ::8]
    primary = select_patches(grid)
    inner = ndimage.binary_erosion(grid, iterations=20, structure=np.ones((3, 3)))
    points = np.argwhere(inner)
    rng = np.random.default_rng(protocol["secondary_seed"])
    secondary = [(int(r)*8-PATCH//2, int(c)*8-PATCH//2)
                 for r, c in points[rng.choice(len(points), 8, replace=False)]]
    boxes = set(box_origins(primary + secondary))
    mapping = {}
    means, fractions, samples = {}, {}, {}
    for end in ("low", "high"):
        start, stop = protocol[end]
        near_zero = count = 0
        for old, k in zip(AIR_ENDS[end], range(start, stop + 1), strict=True):
            mapping[old] = k
            plane = reader(asset(f"layers/{k:02}.png"), boxes)
            samples[k] = plane
            values = np.concatenate([plane[r, c][mask[r:r+SIDE, c:c+SIDE]]
                                     for r, c in box_origins(primary)])
            near_zero += int(np.count_nonzero(values <= 2))
            count += values.size
            means[k] = float(values.mean())
            print(fragment, k, flush=True)
        fractions[end] = near_zero / count
    result = summarize(samples, mask, primary, mapping, protocol["minimum_ratio"])
    return dict(**result, pixel_type="uint8", sha256=hashes, mean_by_layer=means,
                max_mean_layer=max(means, key=means.get),
                max_std_layer=max(result["layer_std_median"], key=result["layer_std_median"].get),
                near_zero_fraction=fractions, reserved_bytes=int(account.read_text()),
                protocol_sha256=PROTOCOL_SHA[PROTOCOL.name],
                secondary=summarize(samples, mask, secondary, mapping, protocol["minimum_ratio"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=PROTOCOL)
    parser.add_argument("--stream", action="store_true", help="Decode layers row by row")
    args = parser.parse_args()
    protocol = read_protocol(args.protocol)
    inventory = json.loads((HERE / "phase17-inventory.json").read_text())
    results = {frag: analyze(frag, base, inventory[frag], protocol,
                             stream_patches if args.stream else full_patches)
               for frag, base in protocol["fragments"].items()}
    (HERE / "phase17-orientation.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
