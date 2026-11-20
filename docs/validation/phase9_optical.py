"""Verify the published ν2 field using its original calibrated numeric export."""

import argparse
import csv
import json
from hashlib import file_digest
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image
from scipy.ndimage import gaussian_filter

REVISION = "a806bead2f3b9100c20e19de37814fb285cfeefd"
CASE = "500P2_230925_N2"


def sha(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def read_height(path, shape):
    with path.open("rb") as stream:
        x = np.fromstring(stream.readline().strip().strip(b";").decode("ascii"), sep=";")
        height, y = np.empty(shape, "f4"), []
        for index, line in enumerate(stream):
            row = np.fromstring(line.strip().strip(b";").decode("ascii"), sep=";")
            if len(row) != len(x)+1 or index >= shape[0]:
                raise ValueError("Published raw grid does not have the expected dimensions")
            y.append(row[0])
            height[index] = row[1:]
    if height.shape != (len(y), len(x)):
        raise ValueError("Incomplete numeric export")
    return x, np.array(y), height


def scale_axis(centers):
    indices = np.arange(len(centers))
    pitch, origin = np.polyfit(indices, centers, 1)
    if not np.isfinite(centers).all() or np.any(np.diff(centers) <= 0):
        raise ValueError("Physical centers must be finite and strictly ascending")
    return {"pitch_um": float(pitch), "extent_center_to_center_um": float(np.ptp(centers)),
            "origin_um": float(origin),
            "max_residual_um": float(abs(centers-(indices*pitch+origin)).max()),
            "error_vs_article_0_34_um_at_far_end": float(np.ptp(centers)-.34*indices[-1])}


def read_brightfield(path):
    """Decode the release's contiguous RGB strips, whose TIFF type tag is inconsistent."""
    with tifffile.TiffFile(path) as document:
        page = document.pages[0]
        if page.dtype is not None:
            return page.asarray(), False
        counts = np.asarray(page.databytecounts)
        offsets = np.asarray(page.dataoffsets)
        expected = (page.imagelength, page.imagewidth, 3)
        if (page.compression != 1 or page.photometric != 2 or page.planarconfig != 1
                or page.bitspersample != 8 or page.samplesperpixel != 3
                or page.sampleformat != 3 or page.tags["Orientation"].value != 1
                or counts.sum() != np.prod(expected) or not np.all(offsets[1:] == offsets[:-1]+counts[:-1])
                or offsets[-1]+counts[-1] > path.stat().st_size):
            raise ValueError("Malformed TIFF outside the known contiguous RGB layout")
    return np.memmap(path, "u1", mode="r", offset=int(offsets[0]), shape=expected), True


def audit(root):
    sources = {item["path"]: item for item in json.loads((root/"tree.json").read_bytes())}
    cases = json.loads((root/"configs/case_manifest.json").read_bytes())["samples"]
    case = next(c for c in cases if c["case_id"] == CASE)
    names = {k: case[k] for k in ("raw_height_txt", "normalized_height_tif", "brightfield_tif", "label_png")}
    verified = {}
    for key, relative in names.items():
        path = root/relative
        h = sha(path)
        if h != sources[relative]["lfs"]["oid"] or path.stat().st_size != sources[relative]["size"]:
            raise ValueError(f"LFS integrity mismatch for {path}")
        verified[key] = {"path": relative, "sha256": h, "bytes": path.stat().st_size}
    paths = {k:root/v for k,v in names.items()}
    norm = tifffile.imread(paths["normalized_height_tif"])
    bright, repaired_rgb = read_brightfield(paths["brightfield_tif"])
    with Image.open(paths["label_png"]) as source:
        label = np.array(source)
        dpi = source.info.get("dpi")
    if norm.dtype != "uint16" or norm.shape != label.shape or bright.shape != (*norm.shape, 3):
        raise ValueError("Unexpected optical raster shapes or data types")
    x, y, height = read_height(paths["raw_height_txt"], norm.shape)
    valid = np.isfinite(height)
    low, high = float(height[valid].min()), float(height[valid].max())
    # Test internal pixel indexing against adjacent shifted controls, using only heights.
    center = np.s_[1:-1:4, 1:-1:4]
    sample = height[center]
    pairs = valid[center]
    values = sample[pairs]
    codes = norm[center][pairs].astype(float)
    slope, intercept = np.polyfit(values, codes, 1)
    alignment = {}
    for offset_y, offset_x in ((0,0), (1,0), (-1,0), (0,1), (0,-1)):
        displaced = norm[1+offset_y:norm.shape[0]-1+offset_y:4,
                         1+offset_x:norm.shape[1]-1+offset_x:4][pairs]
        alignment[f"{offset_y},{offset_x}"] = float(
            np.sqrt(np.mean((displaced-(values*slope+intercept))**2)) / slope)
    green = bright[::4, ::4, 1].astype(float)
    relief = norm[::4, ::4].astype(float)
    def structure(plane):
        gy, gx = np.gradient(gaussian_filter(plane, 1.))
        g = np.hypot(gy, gx)
        return np.minimum(g, np.quantile(g, .99))
    bri, rel = structure(green), structure(relief)
    # A cross-modality diagnostic across shifts of four native pixels.
    shifts = {}
    interior = valid[8:-8:4, 8:-8:4]
    for dv in (-1, 0, 1):
        for du in (-1, 0, 1):
            b = bri[2+dv:bri.shape[0]-2+dv, 2+du:bri.shape[1]-2+du]
            shifts[f"{4*dv},{4*du}"] = float(np.corrcoef(rel[2:-2, 2:-2][interior], b[interior])[0,1])
    with (root/"manifest.csv").open(encoding="utf-8", newline="") as stream:
        manifest = [c for c in csv.DictReader(stream) if c["papyrus_dir"] == "pherc0500p2"]
    meta = ("README.md", "manifest.csv", "configs/sampling.json",
            "configs/experiment.json", "configs/case_manifest.json", "folds/splits_final.json", "tree.json")
    splits = json.loads((root/"folds/splits_final.json").read_bytes())
    result = {"repository_revision": REVISION, "dataset_version": "1.0.0", "license": "CC BY-NC 4.0",
              "publication": "https://doi.org/10.1038/s41598-026-58467-1",
              "metadata_files": {k: {"sha256": sha(root/k), "bytes": (root/k).stat().st_size} for k in meta},
              "cases": manifest, "pilot": case, "files": verified, "shape_yx": list(norm.shape),
              "axis_x": scale_axis(x), "axis_y": scale_axis(y), "label_print_dpi": dpi,
              "calibration_status": "export pitch measured, absolute instrument calibration unverified",
              "height_range_um": [low, high], "valid_fraction": float(valid.mean()),
              "brightfield_read_from_validated_uint8_strips": repaired_rgb,
              "ink_annotation_nonzero": int(np.count_nonzero(label)),
              "raw_to_normalized_residual_um": alignment,
              "height_brightfield_gradient_correlations_dy_dx_px": shifts,
              "optical_folds": [{"index": i, "train": sorted(s["train"]), "val": sorted(s["val"])}
                                for i,s in enumerate(splits)]}
    return result, height, bright, label


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("preview", type=Path)
    args = p.parse_args()
    report, height, bright, label = audit(args.root)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf8")
    np.savez_compressed(args.preview, height=height[::4,::4], bright=bright[::4,::4],
                        label=label[::4,::4] != 0)
