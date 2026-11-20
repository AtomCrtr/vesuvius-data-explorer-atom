"""Inventory independent modalities, provenance limits and public checkpoint leads."""

import argparse
import csv
import gzip
import io
import json
from pathlib import Path
from urllib.request import urlopen

from phase6_cuda import digest
from phase6_review import audit_references
from phase7_checkpoints import request

OPTICAL_REV = "a806bead2f3b9100c20e19de37814fb285cfeefd"
OPTICAL = f"https://huggingface.co/datasets/scrollprize/profilometer/resolve/{OPTICAL_REV}"


def optical_metadata():
    from hashlib import sha256

    files, values = {}, {}
    for name in ("manifest.csv", "configs/case_manifest.json", "configs/sampling.json"):
        url = f"{OPTICAL}/{name}"
        with urlopen(url, timeout=18) as reader:
            content = reader.read((1<<18)+1)
        if len(content) > 1<<18:
            raise ValueError("Unexpectedly large metadata")
        files[name] = {"url": url, "sha256": sha256(content).hexdigest(), "bytes": len(content)}
        values[name] = content
    rows = list(csv.DictReader(io.StringIO(values["manifest.csv"].decode())))
    cases = [r for r in rows if r["papyrus_dir"] == "pherc0500p2"]
    return {"revision": OPTICAL_REV, "record_count": len(rows), "matching_specimen_records": cases,
            "metadata": files, "case_manifest_keys": list(json.loads(values["configs/case_manifest.json"])),
            "sampling": json.loads(values["configs/sampling.json"]), "license": "CC BY-NC 4.0",
            "evidence": "height and brightfield/ink labels registered within each optical acquisition",
            "ct_uv_transform_found": False, "confirmed_excluded_from_checkpoint_training": False,
            "tier": "exploratory_same_specimen"}


def inspect_catalogue(path):
    data = path.read_bytes()
    atlas = json.loads(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)
    sample = atlas["samples"]["PHerc0500P2"]
    segment = sample["segments"]["20250919184428"]
    return {"sha256": digest(path), "sample": sample["sample"], "original_volume_id": segment["original_volume_id"],
            "segment_id": segment["long_id"], "roles": sorted({item["type"] for item in segment["data"]}),
            "volume_ids": sorted(sample["volumes"]), "model_B": atlas["models"]["20260709123958"]}


def catalogue():
    references = audit_references(Path("docs/validation/phase5-reference-windows.json"),
                                  Path("data/phase5-reference"))
    for row in references:
        row["tier"] = ("geometry_control" if row["id"].endswith("/mask_edge_artifact") else
                       "exploratory_evaluation")
    return {"educe_lab": references, "independent_ink_evaluation_confirmed": [],
            "atlas": inspect_catalogue(Path("data/rust2/catalog.json")),
            "optical_profilometry": optical_metadata(),
            "other_public_controls": [
                {"kind": "synthetic_leaded_ink", "doi": "10.18434/mds2-4227",
                 "study": "https://doi.org/10.1371/journal.pone.0353485", "tier": "tooling_control",
                 "directly_applicable_to_Herculaneum_carbon_ink": False},
                {"kind": "curated_scroll_pseudo_labels", "tier": "not_independent_for_ink",
                 "uri": "https://scrollprize.org/data_datasets#ink-labels-2026-07"}],
            "model_B": {"production_id": "20260709123958", "checkpoint_found": False,
                        "official_hf_record_probe": request(
                            "https://huggingface.co/api/models/scrollprize/mrg20736_1um_s1z2"),
                        "registry_evidence": "docs/validation/phase7-checkpoints.json",
                        "public_contact": "https://github.com/ScrollPrize/villa/issues/1377",
                        "maintainer": "erdpx"}}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    args.output.write_text(json.dumps(catalogue(), ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
