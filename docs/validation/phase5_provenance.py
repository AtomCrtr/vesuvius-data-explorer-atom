"""Verify public PHerc0500P2 score artifacts and bound their spatial provenance."""

import argparse
import gzip
import io
import json
from pathlib import Path

import fsspec
import numpy as np
import tifffile
from phase4_ink import MODELS, ORIGIN, SAMPLE, SEGMENT, SIDE, VOLUME, artifact, dump, sha

from vesuvius_data_explorer.core.consensus import rank_agreement
from vesuvius_data_explorer.core.tifxyz import load_tifxyz
from vesuvius_data_explorer.core.volume import open_volume_store


def iou(a, b):
    denominator = np.count_nonzero(a | b)
    return float(np.count_nonzero(a & b) / denominator) if denominator else None


def safe_entry(entry):
    """Keep the producing workflow, without arbitrary workflow parameters."""
    creation = entry["creation_info"]
    provenance = creation["provenance"]
    keys = ("model", "model-type", "s3-path", "start-layer", "end-layer", "tile-size",
            "stride", "batch-size", "force-reverse", "add-scale-bar", "segmentation-path",
            "scale", "group-idx", "rotate", "flip", "flip-normals", "num-slices",
            "crop-x", "crop-y", "crop-width", "crop-height", "voxel-size", "voxel-unit",
            "repo", "commit", "binary-path", "affine-matrix")
    return {**entry, "creation_info": {**creation, "provenance": {
        **provenance, "parameters": {k: provenance["parameters"][k] for k in keys
                                     if k in provenance["parameters"]}}}}


def run(atlas_file, previous_directory):
    raw = atlas_file.read_bytes()
    atlas = json.loads(gzip.decompress(raw) if raw.startswith(bytes((31, 139))) else raw)
    segment = atlas["samples"][SAMPLE]["segments"][SEGMENT]
    entries = [d for d in segment["data"]
               if (d.get("parameters") or {}).get("target_volume") == VOLUME]
    maps = {d["parameters"]["model_id"]: d for d in entries if d["type"] == "ink-detection"}
    stack_entry = next(d for d in entries if d["type"] == "layers-zarr")
    stack = artifact(stack_entry)
    root = open_volume_store(stack)
    meshes = {d["parameters"].get("transform_revision", "historical"): d for d in entries
              if d["type"] == "tifxyz-transformed"}
    historical = load_tifxyz(artifact(meshes["historical"]))
    latest = load_tifxyz(artifact(meshes["2"]))
    fs = fsspec.filesystem("s3", anon=True, max_concurrency=1)
    records, rasters = {}, {}
    v, u = ORIGIN
    for model in MODELS:
        uri = artifact(maps[model])
        key = uri.removeprefix("s3://")
        info = fs.info(key)
        if not 0 < info["size"] < 2**20:
            raise ValueError("Score TIFF size differs from the bounded audit budget")
        encoded = fs.cat_file(key)
        assert len(encoded) == info["size"]
        with tifffile.TiffFile(io.BytesIO(encoded)) as tif:
            page = tif.pages[0]
            assert len(tif.pages) == 1 and page.shape == (1160, 1400)
            scores = page.asarray()
            tags = {key: page.tags.valueof(key) for key in
                    ("Orientation", "XResolution", "YResolution", "ResolutionUnit",
                     "XPosition", "YPosition", "Software")}
            desc = json.loads(page.description)
        crop = scores[v:v+SIDE, u:u+SIDE]
        previous = tifffile.imread(previous_directory / f"{model}.tif")
        np.testing.assert_array_equal(crop, previous, strict=True)
        rasters[model] = scores
        records[model] = {"uri": uri, "sha256_tiff": sha(encoded), "etag": info.get("ETag"),
                          "sha256_previous_roi": sha(crop.tobytes()), "size_bytes": len(encoded),
                          "dtype": str(scores.dtype), "range": [int(scores.min()), int(scores.max())],
                          "shape_vu": scores.shape, "description": desc, "tags": tags,
                          "positive_code_pixels": int(np.count_nonzero(scores)),
                          "atlas_entry": safe_entry(maps[model]),
                          "atlas_model": atlas["models"][model]}
    ar, br = (rasters[model] for model in MODELS)
    a, b = ar > 0, br > 0
    common = a & b
    old_mask = historical.valid.repeat(20, axis=0).repeat(20, axis=1)
    assert old_mask.shape == a.shape
    parent = records[MODELS[0]]["uri"].removeprefix("s3://").rsplit("/", 1)[0]
    sidecars = [item.rsplit("/", 1)[-1] for item in fs.ls(parent, detail=False)
                if item.lower().endswith((".json", ".yaml", ".toml", ".txt"))]
    return {"catalogue_sha256": sha(raw), "sample": SAMPLE, "segment": SEGMENT, "volume": VOLUME,
            "maps": records, "ink_directory_sidecars": sidecars,
            "stack": {"uri": stack, "root_attrs": dict(root.attrs),
                      "atlas_entry": safe_entry(stack_entry)},
            "meshes": {"historical": {"uri": historical.source, "meta": historical.meta,
                                      "shape": historical.grid_shape,
                                      "atlas_entry": safe_entry(meshes["historical"])},
                       "t2": {"uri": latest.source, "meta": latest.meta, "shape": latest.grid_shape}},
            "support_checks": {"meaning": "nonzero byte footprint, no ink threshold or registration",
                               "pair_identity": iou(a, b), "pair_flip_v": iou(a, b[::-1]),
                               "pair_flip_u": iou(a, b[:, ::-1]),
                               "pair_rotate_180": iou(a, b[::-1, ::-1]),
                               "historical_tifxyz_validity": [iou(a, old_mask), iou(b, old_mask)]},
            "rank_agreement_nonzero": rank_agreement(ar[common], br[common])}


def write_comparison(folder, report):
    """Carry the verified source chain into the local phase 5 napari manifest."""
    previous = folder / "comparison.json"
    manifest = json.loads(previous.read_bytes())
    mesh = report["meshes"]["historical"]
    manifest["surface_revision"] = mesh["uri"].rsplit("/", 1)[-1]
    for entry, model in zip(manifest["predictions"], MODELS, strict=True):
        source = report["maps"][model]
        if source["sha256_tiff"] != entry["provenance"]["sha256_tiff"]:
            raise ValueError("The napari manifest refers to a different source TIFF")
        entry["provenance"].update({
            "registration": {"input_stack": report["stack"]["uri"], "mesh": mesh["uri"],
                             "uv_orientation": ["+v", "+u"], "anatomical_face": "undetermined"},
            "atlas_creation_info": source["atlas_entry"]["creation_info"],
            "atlas_catalogue_sha256": report["catalogue_sha256"],
        })
    dump(folder / "comparison-phase5.json", manifest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("atlas", type=Path)
    parser.add_argument("phase4", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--comparison", action="store_true")
    args = parser.parse_args()
    result = run(args.atlas, args.phase4)
    dump(args.output, result)
    if args.comparison:
        write_comparison(args.phase4, result)
