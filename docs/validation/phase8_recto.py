"""Probe the public surface label only along the six preselected CT witnesses."""

import argparse
import hashlib
import itertools
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import requests
from numcodecs import get_codec

SOURCE = ("https://huggingface.co/buckets/scrollprize/datasets/resolve/"
          "surfaces/2um_032726/0500p2_5217.zarr")
CONTROL = "0/100.60.78"


def fetch(cache, key, limit):
    local = cache / key.lstrip(".").replace("/", "_")
    miss = local.with_suffix(local.suffix + ".404")
    if miss.exists():
        return None
    if local.exists():
        return local.read_bytes()
    with requests.get(f"{SOURCE}/{key}", timeout=30, stream=True) as response:
        if response.status_code == 404 and key.startswith("0/"):
            miss.touch()
            return None
        response.raise_for_status()
        buffer = bytearray()
        for part in response.iter_content(65536):
            buffer.extend(part)
            if len(buffer) > limit:
                raise ValueError(f"Object exceeds the sparse probe budget: {key}")
    local.write_bytes(buffer)
    return buffer


def probe(cache, orientation):
    attrs_raw = fetch(cache, ".zattrs", 16_384)
    array_raw = fetch(cache, "0/.zarray", 4_096)
    attrs = json.loads(attrs_raw)
    array = json.loads(array_raw)
    transform = attrs["multiscales"][0]["datasets"][0]
    if (transform["path"] != "0" or tuple(array["shape"]) != tuple(orientation["raw_level_shape_zyx"])
            or transform["coordinateTransformations"] != [
                {"scale": [1., 1., 1.], "type": "scale"},
                {"translation": [0., 0., 0.], "type": "translation"},
            ] or Path(attrs["source_zarr"]).name.rsplit("-", 1)[0] != orientation["raw_volume"].split("/")[-1]):
        raise ValueError("The label does not claim the same index space and acquisition.")
    side = np.asarray(array["chunks"])
    offsets = np.arange(-64, 65)
    positions = {}
    for witness in orientation["witnesses"]:
        center = np.array(witness["raw_voxel_zyx"])
        normal = -np.asarray(witness["geometric_normal_xyz"])[::-1]
        e1 = np.cross(normal, np.eye(3)[np.argmin(np.abs(normal))])
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(normal, e1)
        tangent = np.array([a * e1 + b * e2 for a, b in itertools.product(range(-4, 5, 2), repeat=2)])
        points = center + offsets[:, None, None] * normal + tangent
        positions[tuple(witness["uv_vu"])] = np.rint(points).astype(int)
    indices = sorted({tuple(index) for points in positions.values()
                      for index in (points.reshape(-1, 3) // side)})
    codec = get_codec(array["compressor"])
    blank = np.full(tuple(side), array["fill_value"], dtype=array["dtype"])
    control = fetch(cache, CONTROL, 256 * 1024)
    if control is None or not np.any(np.frombuffer(codec.decode(control), dtype=array["dtype"])):
        raise ValueError("The listed positive control chunk must contain a label.")
    keys = ["0/" + ".".join(map(str, item)) for item in indices]
    with ThreadPoolExecutor(max_workers=6) as pool:
        blobs = dict(zip(indices, pool.map(lambda key: fetch(cache, key, 256 * 1024), keys), strict=True))
    chunks = {index: (blank if blob is None else
                      np.frombuffer(codec.decode(blob), dtype=array["dtype"]).reshape(tuple(side)))
              for index, blob in blobs.items()}
    report = {"source": SOURCE, "attributes": attrs, "array": array,
              "metadata_sha256": [hashlib.sha256(raw).hexdigest() for raw in (attrs_raw, array_raw)],
              "positive_control": {"path": CONTROL, "bytes": len(control),
                                   "sha256": hashlib.sha256(control).hexdigest()},
              "chunks": [{"path": key, "bytes": len(blob) if blob else 0,
                          "sha256": hashlib.sha256(blob).hexdigest() if blob else None}
                         for key, blob in zip(keys, blobs.values(), strict=True)],
              "samples_per_offset": 25, "offsets_in_voxels_toward_increasing_render_depth": offsets.tolist(),
              "witnesses": []}
    for vu, points in positions.items():
        values = np.array([chunks[tuple(point // side)][tuple(point % side)]
                           for point in points.reshape(-1, 3)], dtype=np.uint8).reshape(points.shape[:2])
        counts = np.count_nonzero(values, axis=1)
        occupied = offsets[counts > 0]
        report["witnesses"].append({"vu": list(vu), "nonzero_per_offset": counts.tolist(),
                                    "profiles_with_hits": int(np.count_nonzero(np.any(values, axis=0))),
                                    "nearest_offset": int(occupied[np.argmin(abs(occupied))]) if occupied.size else None})
    return report


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("cache", type=Path)
    cli.add_argument("orientation", type=Path)
    cli.add_argument("report", type=Path)
    args = cli.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    result = probe(args.cache, json.loads(args.orientation.read_text(encoding="utf-8")))
    args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
