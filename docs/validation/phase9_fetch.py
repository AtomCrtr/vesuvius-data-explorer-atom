"""Fetch only the pinned pilot field, metadata and frontal CT geometry."""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

from phase9_optical import CASE, REVISION, sha

HF = "https://huggingface.co/datasets/scrollprize/profilometer"
ATLAS = ("https://vesuvius-challenge-open-data.s3.amazonaws.com/PHerc0500P2")
FRONT = f"{ATLAS}/segments/20250628074500-500P2_front"
FRONT_STACK = f"{FRONT}/surface-volumes/2.215um-0.4m-111keV-volume-20250526151718.zarr"
FIGURE = "https://arxiv.org/html/2606.29085v1/edfig5.png"
META = ("README.md", "manifest.csv", "configs/sampling.json", "configs/experiment.json",
        "configs/case_manifest.json", "folds/splits_final.json")


def fetch(url, path, limit, *, expected=None, size=None):
    def check(file):
        if ((size is not None and file.stat().st_size != size)
                or (expected is not None and sha(file) != expected) or file.stat().st_size > limit):
            raise ValueError(f"Unexpected size or fingerprint for {file}")
    if path.exists():
        check(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix+".part")
    try:
        with urlopen(url, timeout=45) as source, part.open("wb") as content:
            remaining = limit
            while block := source.read(1<<20):
                remaining -= len(block)
                if remaining < 0:
                    raise ValueError(f"Object exceeds download budget at {url}")
                content.write(block)
        check(part)
        part.replace(path)
    finally:
        part.unlink(missing_ok=True)


def download(work):
    root = work/"optical"
    for key in META:
        fetch(f"{HF}/resolve/{REVISION}/{key}", root/key, 256*1024)
    fetch(f"https://huggingface.co/api/datasets/scrollprize/profilometer/tree/{REVISION}/data/pherc0500p2",
          root/"tree.json", 256*1024)
    case = next(c for c in json.loads((root/"configs/case_manifest.json").read_bytes())["samples"]
                if c["case_id"] == CASE)
    keys = {case[k] for k in ("raw_height_txt", "normalized_height_tif", "brightfield_tif", "label_png")}
    tree = {x["path"]:x for x in json.loads((root/"tree.json").read_bytes())}
    def pilot(key):
        obj = tree[key]
        fetch(f"{HF}/resolve/{REVISION}/{quote(key)}", root/key, 165*2**20,
              expected=obj["lfs"]["oid"], size=obj["size"])
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(pilot, sorted(keys)))
    front = "20250628074500-on-20250526151718-2.215um"
    for folder, remote in (("front.tifxyz",front), ("front-t2.tifxyz",front+"-t2")):
        for name in ("meta.json","x.tif","y.tif","z.tif"):
            fetch(f"{FRONT}/mesh/{remote}.tifxyz/{name}",work/folder/name,8*2**20)
    fetch(f"{ATLAS}/photos/PHerc0500P2_photo.jpg",work/"PHerc0500P2_photo.jpg",2**20)
    fetch(f"{FRONT_STACK}/.zattrs",work/"front-zattrs.json",65536)
    fetch(FIGURE,work/"front-reference-figure.png",2**20)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=Path)
    download(p.parse_args().work)
