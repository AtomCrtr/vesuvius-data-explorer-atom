"""Build small, registered EduceLab reference crops from the public archive."""

import argparse
import io
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import urlopen

import fsspec
import numpy as np
import tifffile
from phase4_ink import dump, sha
from PIL import Image

BASE = "https://dl.ash2txt.org/fragments"
PAPER = "https://arxiv.org/html/2304.02084v4"
LICENSE = "https://dl.ash2txt.org/LICENSE.txt"
SOURCES = {"Frag1": ("PHercParis2Fr47", "PHercParis2"),
           "Frag3": ("PHercParis1Fr34", "PHercParis1")}
SIDE = 128


def fetch(folder, name, url, limit):
    target = folder / name
    if target.exists():
        if target.stat().st_size > limit:
            raise ValueError(f"Cached source exceeds the size limit: {target}")
        return target.read_bytes()
    with urlopen(url, timeout=40) as response:
        data = response.read(limit + 1)
    if not data or len(data) > limit:
        raise ValueError(f"Invalid response size: {url}")
    target.write_bytes(data)
    return data


def decode(data, *, binary=False):
    with Image.open(io.BytesIO(data)) as image:
        if image.width * image.height > 60_000_000 or image.getexif().get(274, 1) != 1:
            raise ValueError("Unexpected image grid or orientation")
        if not binary:
            return np.asarray(image.convert("L"))
        values = np.asarray(image)
        if values.ndim != 2 or not np.isin(values, [0, 1, 255]).all():
            raise ValueError("Expected a binary mask")
        return values > 0


def select(support, ink):
    """Pick one disjoint window per stratum using labels and support alone."""
    area = SIDE**2
    rows = []
    for v in range(0, ink.shape[0] - SIDE + 1, SIDE):
        for u in range(0, ink.shape[1] - SIDE + 1, SIDE):
            box = np.s_[v:v+SIDE, u:u+SIDE]
            rows.append((v, u, int(support[box].sum()), int(ink[box].sum())))
    rules = {
        "ink": (lambda s, n: s == area and n >= 0.04*area,
                lambda s, n: abs(n - 0.18*area)),
        "background": (lambda s, n: s == area and n == 0, lambda s, n: 0),
        "sparse_traces": (lambda s, n: s == area and 0 < n <= 0.025*area,
                          lambda s, n: abs(n - 0.01*area)),
        "mask_edge_artifact": (lambda s, n: 0.25*area < s < 0.75*area and n == 0,
                               lambda s, n: abs(s - area/2)),
    }
    chosen = {}
    for kind, (eligible, rank) in rules.items():
        possible = ((rank(s, n), v, u) for v, u, s, n in rows if eligible(s, n))
        _, v, u = min(possible)
        chosen[kind] = v, u, SIDE, SIDE
    return chosen


def scan_fragment(work, fragment):
    sample, parent_scroll = SOURCES[fragment]
    base = f"{BASE}/{fragment}/{sample}.volpkg/working/54keV_exposed_surface"
    folder = work / fragment
    folder.mkdir(parents=True, exist_ok=True)
    sources = {}
    planes = []
    for name, binary, limit in (("mask.png", True, 1<<20), ("inklabels.png", True, 1<<20),
                                ("ir.png", False, 12<<20)):
        url = f"{base}/{name}"
        data = fetch(folder, name, url, limit)
        sources[name] = {"uri": url, "bytes": len(data), "sha256": sha(data)}
        planes.append(decode(data, binary=binary))
    support, labels, ir = planes
    if not support.shape == labels.shape == ir.shape:
        raise ValueError("The published surface planes do not share a grid")
    ink = labels & support
    selected = select(support, ink)
    meta_url = f"{base}/surface_volume/meta.json"
    meta = fetch(folder, "surface-meta.json", meta_url, 4096)
    surface = json.loads(meta)
    if (surface["height"], surface["width"]) != support.shape or surface["slices"] != 65:
        raise ValueError("Unexpected surface volume metadata")
    sources["surface-meta.json"] = {"uri": meta_url, "sha256": sha(meta), "bytes": len(meta),
                                    "published_metadata": surface}
    ct_url = f"{base}/surface_volume/32.tif"
    regions = []
    with fsspec.open(ct_url, "rb", block_size=1<<16, cache_type="none") as raw:
        with tifffile.TiffFile(raw) as tif:
            page = tif.pages[0]
            if (page.shape != support.shape or int(page.compression) != 1 or page.is_tiled
                    or page.dtype != np.uint16 or len(page.dataoffsets) != 1
                    or page.databytecounts[0] != support.size*2
                    or page.tags.valueof("Orientation", 1) != 1):
                raise ValueError("Unexpected CT TIFF layout; full download disabled")
            offset, endian = page.dataoffsets[0], tif.byteorder
        sources["ct"] = {"uri": ct_url, "plane": 32, "dtype": "uint16", "byteorder": endian,
                         "size_bytes": raw.size, "pixel_data_offset": offset}
        for kind, (v, u, h, w) in selected.items():
            window = np.s_[v:v+h, u:u+w]
            row_width = support.shape[1]
            first = offset + 2*(v*row_width + u)
            count = 2*((h-1)*row_width+w)
            raw.seek(first)
            strip = raw.read(count)
            if len(strip) != count:
                raise ValueError("Incomplete CT byte range")
            ct = np.ndarray((h, w), dtype=endian+"u2", buffer=strip, strides=(2*row_width, 2))
            ct = np.ascontiguousarray(ct, dtype="<u2")
            reference = np.where(support[window], ink[window], 255).astype(np.uint8)
            images = {"ct": ct, "ir": ir[window], "labels": reference}
            patch = folder / kind
            patch.mkdir(exist_ok=True)
            regions.append({"id": f"{fragment}/{kind}", "kind": kind, "start_vu": [v, u],
                            "stop_vu": [v+h, u+w], "ct_range": [first, first+count],
                            "labels": {str(code): int(np.count_nonzero(reference == code))
                                       for code in (0, 1, 255)},
                            "pixels_sha256": {k: sha(values.tobytes()) for k, values in images.items()},
                            "usage": "mask_qa_only" if kind == "mask_edge_artifact" else "reference_only"})
            for name, values in images.items():
                tifffile.imwrite(patch / f"{name}.tif", values, photometric="minisblack")
    return {"sample": sample, "parent_scroll": parent_scroll, "grid_shape_vu": support.shape,
            "face": "published exposed surface", "sources": sources, "regions": regions,
            "source_pixels": {"ink_inside_mask": int(ink.sum()),
                              "ink_outside_mask": int(np.count_nonzero(labels & ~support))}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with ThreadPoolExecutor(max_workers=2) as pool:
        reports = list(pool.map(lambda fragment: scan_fragment(args.work, fragment), SOURCES))
    dump(args.output, {"axes": ["v", "u"], "bounds": "half_open", "license": LICENSE,
                       "publication": PAPER, "split": "reference_only",
                       "glyph_reference": {"sample": "PHercParis1Fr34", "figure": 3,
                                           "uri": PAPER + "#S2.F3",
                                           "region_registration": "figure_only"},
                       "fragments": reports})


if __name__ == "__main__":
    main()
