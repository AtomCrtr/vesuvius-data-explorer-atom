"""Open every catalogued ome-zarr volume with our core; record format, codecs and ROI reads."""
import json
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor

import s3fs

from vesuvius_data_explorer.core.volume import get_array, list_levels, open_volume_store, read_slice

fs = s3fs.S3FileSystem(anon=True)
vols = json.load(open(sys.argv[1]))
roi_every = int(sys.argv[3])

def codecs(path):
    base = "vesuvius-challenge-open-data/" + path.rstrip("/")
    for name in ("0/.zarray", "0/zarr.json"):
        try:
            meta = json.loads(fs.cat(f"{base}/{name}"))
        except FileNotFoundError:
            continue
        if name.endswith(".zarray"):
            c = meta.get("compressor") or {}
            return {"zarr": 2, "codec": c.get("id"), "cname": c.get("cname"),
                    "chunks": meta.get("chunks"), "sharded": False}
        cs = meta.get("codecs", [])
        names = [x.get("name") for x in cs]
        inner = []
        for x in cs:
            if x.get("name") == "sharding_indexed":
                inner = [y.get("name") for y in x.get("configuration", {}).get("codecs", [])]
        return {"zarr": 3, "codec": names, "inner": inner, "sharded": "sharding_indexed" in names,
                "chunks": meta.get("chunk_grid", {}).get("configuration", {}).get("chunk_shape")}
    return {"zarr": None}

def check(i_v):
    i, (sid, vid, fmt, px, path, roots) = i_v
    row = {"sample": sid, "volume": vid, "path": path, "pixel_um": px}
    try:
        row.update(codecs(path))
        t = time.time()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            root = open_volume_store("s3://vesuvius-challenge-open-data/" + path)
            levels = list_levels(root)
        row.update(levels=len(levels), shape0=list(levels[0].shape), dtype=levels[0].dtype,
                   scale0=list(levels[0].scale), scale_from_metadata=levels[0].scale_from_metadata,
                   ome_ngff=("0.5" if "ome" in dict(root.attrs) else "0.4" if "multiscales" in dict(root.attrs) else None),
                   warnings=[str(x.message)[:80] for x in w], open_s=round(time.time() - t, 1))
        if i % roi_every == 0:
            t = time.time()
            arr = get_array(root, levels[-1].key)
            z, y, x = levels[-1].shape
            data = read_slice(arr, "z", z // 2, max(0, y // 2 - 32), max(0, x // 2 - 32), width=64)
            row.update(roi_ok=True, roi_shape=list(data.shape), roi_max=int(data.max()), roi_s=round(time.time() - t, 1))
        row["ok"] = True
    except Exception as e:
        row.update(ok=False, error=f"{type(e).__name__}: {str(e)[:160]}")
    return row

with ThreadPoolExecutor(8) as pool:
    rows = list(pool.map(check, enumerate(vols)))
json.dump(rows, open(sys.argv[2], "w"), indent=1)
print("ok", sum(r["ok"] for r in rows), "/", len(rows))
