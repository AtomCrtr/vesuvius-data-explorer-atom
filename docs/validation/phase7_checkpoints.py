"""Check the local A release and look for an attributable public B checkpoint."""

import argparse
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from phase6_cuda import CHECKPOINT, HF, HF_REVISION, WEIGHTS_SHA, digest

B_KEYS = ("mrg20736_1um_s1z2", "mrg20736-1um-s1z2", "20260709123958", "mrg20736")


def request(url, *, parse=False):
    try:
        with urlopen(url, timeout=20) as response:
            result = {"url": url, "status": response.status}
            if parse:
                result["payload"] = json.loads(response.read(2**20))
            return result
    except HTTPError as exc:
        return {"url": url, "status": exc.code}
    except (URLError, TimeoutError) as exc:
        return {"url": url, "status": None, "error_kind": type(exc).__name__}


def run(work, provenance):
    a = work / "canonical" / CHECKPOINT
    if not a.is_file() or digest(a) != WEIGHTS_SHA:
        raise ValueError("The pinned A checkpoint is missing or its SHA-256 differs")
    atlas = json.loads(provenance.read_bytes())
    hf_tree = request(f"https://huggingface.co/api/models/scrollprize/ink_canonical_2um/tree/{HF_REVISION}",
                      parse=True)
    listed = next((row for row in hf_tree.get("payload", []) if row["path"] == CHECKPOINT), None)
    if listed is not None and (listed["lfs"]["oid"], listed["size"]) != (WEIGHTS_SHA, a.stat().st_size):
        raise ValueError("Hugging Face LFS metadata differs from the verified local checkpoint")
    searches = []
    for key in B_KEYS:
        result = request("https://huggingface.co/api/models?"+urlencode({"search": key, "limit": 50}),
                         parse=True)
        searches.append({**result, "payload": [m["id"] for m in result.get("payload", [])]})
    registry = []
    for key in ("new_canon_autoresearch_recipe", B_KEYS[0]):
        url = "https://scrollprize-models-registry.s3.amazonaws.com/?" + urlencode(
            {"list-type": 2, "prefix": f"ink-detection/{key}/", "max-keys": 20})
        registry.append(request(url))
    return {
        "phase5_audit_sha256": digest(provenance),
        "public_A": {"status": "available", "uri": f"{HF}/{CHECKPOINT}", "sha256": WEIGHTS_SHA,
                     "size_bytes": a.stat().st_size, "licence": "MIT", "release": HF_REVISION,
                     "public_lfs_attestation": listed, "lfs_lookup_http": hf_tree["status"]},
        "production_bindings": {key: {"model": row["atlas_model"], "id": key, "uri": row["uri"],
                                      "workflow": row["atlas_entry"]["creation_info"],
                                      "sha256_tiff": row["sha256_tiff"],
                                      "checkpoint_sha256": None}
                                for key, row in atlas["maps"].items()},
        "B_searches": searches, "anonymous_registry_queries": registry,
        "available_for_intervention": ["A"], "unavailable_for_intervention": ["B"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase6", type=Path)
    parser.add_argument("provenance", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(run(args.phase6, args.provenance), indent=2)+"\n", encoding="utf-8")
