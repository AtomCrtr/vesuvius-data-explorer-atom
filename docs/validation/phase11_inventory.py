"""Phase 11: recursive listing of the public Frag4 / PHercParis1Fr39 volume package.

Only directory indexes and small text files (config/meta/README/LICENSE, < 64 KiB) are fetched.
Long runs of numbered slices are summarised (count, first/last name, total bytes) instead of listed.

    python -I docs/validation/phase11_inventory.py docs/validation/phase11-frag4-inventory.json
"""

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from urllib.parse import unquote, urljoin
from urllib.request import Request, urlopen

ROOT = "https://dl.ash2txt.org/fragments/Frag4/PHercParis1Fr39.volpkg/"
UA = {"User-Agent": "vesuvius-explorer-inventory/0.1"}
ROW = re.compile(r'<a href="([^"?][^"]*)"[^>]*>.*?</a></td><td[^>]*>([^<]*)</td><td[^>]*>([^<]*)</td>', re.S)
SMALL_TEXT = re.compile(
    r"(config|meta|readme|license|notes?|info)[^/]*\.(json|txt|md)$|\.json$|^\.z(array|attrs|group)$",
    re.I)
UNITS = {"B": 1, "KiB": 2**10, "MiB": 2**20, "GiB": 2**30, "TiB": 2**40}
MAX_TEXT = 64 * 2**10
MAX_DEPTH = 6


def fetch(url, limit=4 * 2**20):
    with urlopen(Request(url, headers=UA), timeout=60) as response:
        raw = response.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(f"oversize response {url}")
    return raw


def size_bytes(text):
    text = text.strip()
    if text in ("-", ""):
        return None
    value, unit = text.split()
    return int(float(value) * UNITS[unit])


def listing(url):
    rows = []
    print(url, file=sys.stderr, flush=True)
    for href, size, date in ROW.findall(fetch(url, 32 * 2**20).decode("utf-8", "replace")):
        if href.startswith("../") or href.startswith("/"):
            continue
        rows.append({"name": unquote(href), "bytes": size_bytes(size), "date": date.strip()})
    return rows


def summarise(files):
    """Group numbered files (e.g. 00.tif .. 64.tif) sharing an extension."""
    groups, rest = {}, []
    for f in files:
        m = re.fullmatch(r"(\d+)(\.[A-Za-z0-9]+)", f["name"])
        (groups.setdefault(m.group(2), []).append(f) if m else rest.append(f))
    out = list(rest)
    for ext, members in groups.items():
        if len(members) < 8:
            out.extend(members)
            continue
        members.sort(key=lambda f: int(f["name"].split(".")[0]))
        sizes = [f["bytes"] or 0 for f in members]
        out.append({"series": f"*{ext}", "count": len(members), "first": members[0]["name"],
                    "last": members[-1]["name"], "bytes_total": sum(sizes),
                    "bytes_each_min_max": [min(sizes), max(sizes)]})
    return out


def walk(url, depth=0):
    node = {"url": url, "dirs": {}, "files": []}
    rows = listing(url)
    files = [r for r in rows if not r["name"].endswith("/")]
    for f in files:
        if SMALL_TEXT.search(f["name"]) and (f["bytes"] or 0) <= MAX_TEXT:
            raw = fetch(urljoin(url, f["name"]), MAX_TEXT)
            f["sha256"] = hashlib.sha256(raw).hexdigest()
            f["text"] = raw.decode("utf-8", "replace")
    node["files"] = summarise(files)
    subdirs = [r for r in rows if r["name"].endswith("/")]
    chunk_dirs = [d for d in subdirs if re.fullmatch(r"\d+/", d["name"])]
    group = any(f["name"] in (".zgroup", ".zattrs", "zarr.json") for f in files)
    is_array = any(f["name"] == ".zarray" for f in files)
    # A multiscale group's numbered children are pyramid levels (descend); an array's numbered
    # children, or long numbered runs elsewhere, are chunk trees (count only).
    if chunk_dirs and (is_array or (not group and len(chunk_dirs) > 8)):
        # Zarr chunk trees hold thousands of directories: record their count, never descend.
        node["chunk_dirs"] = {"count": len(chunk_dirs), "first": chunk_dirs[0]["name"],
                              "last": chunk_dirs[-1]["name"]}
        subdirs = [d for d in subdirs if d not in chunk_dirs]
    for d in subdirs:
        if depth >= MAX_DEPTH:
            node["dirs"][d["name"]] = {"url": urljoin(url, d["name"]), "truncated": True}
        else:
            node["dirs"][d["name"]] = walk(urljoin(url, d["name"]), depth + 1)
    return node


if __name__ == "__main__":
    tree = walk(ROOT)
    out = {"root": ROOT, "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "method": "HTML index parsing; small text files only; numbered series summarised",
           "tree": tree}
    with open(sys.argv[1], "w", encoding="utf-8") as stream:
        json.dump(out, stream, indent=1, ensure_ascii=False)
    print("ok", sys.argv[1])
