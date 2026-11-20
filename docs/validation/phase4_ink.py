"""Exercise two public model exports in their published UV raster, with a CT control."""

import argparse
import gzip
import hashlib
import io
import json
import os
import time
from pathlib import Path

import fsspec
import numpy as np
import tifffile
from scipy.ndimage import map_coordinates

from vesuvius_data_explorer.core.comparison import (
    Candidate,
    ComparisonView,
    comparison_values,
    export_comparison_png,
    load_comparison,
    load_comparison_session,
    save_comparison_session,
)
from vesuvius_data_explorer.core.tifxyz import load_tifxyz
from vesuvius_data_explorer.core.volume import open_levels

S3 = "s3://vesuvius-challenge-open-data/"
SAMPLE = "PHerc0500P2"
SEGMENT = "20250919184428"
VOLUME = "20250526151718"
MODELS = ("20260417190342", "20260709123958")
SCALE_UM = 2.215
ORIGIN = (388, 508)
SIDE = 384


def sha(data):
    return hashlib.sha256(data).hexdigest()


def dump(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def artifact(entry):
    return S3 + entry["origins"][0]["path"].rstrip("/")


def get_tiff(fs, uri):
    key = uri.removeprefix("s3://")
    info = fs.info(key)
    if info["size"] > 16 * 2**20:
        raise ValueError("Prediction exceeds the bounded download")
    data = fs.cat_file(key)
    if len(data) != info["size"]:
        raise ValueError("Prediction changed during download")
    with tifffile.TiffFile(io.BytesIO(data)) as tif:
        page = tif.pages[0]
        assert len(tif.pages) == 1 and page.shape == (1160, 1400) and page.dtype == "uint8"
        assert page.tags.valueof("Orientation", 1) == 1
        description = page.description
        array = page.asarray()
    return array, {"uri": uri, "sha256_tiff": sha(data), "etag": info.get("ETag"),
                   "dtype": str(array.dtype), "shape": array.shape, "description": description}


def ct_control(ct, stack, original, current, origins):
    """Check correspondence at grid knots without moving either score raster."""
    knots = [(24, 30), (26, 32), (30, 37), (32, 40)]
    rows = []
    depth_start = 47
    for v, u in knots:
        r, c = v*20, u*20
        r0, c0 = r - origins[0], c - origins[1]
        radius = 9
        texture = stack[:, r0-radius:r0+radius+1, c0-radius:c0+radius+1]
        witnesses = {}
        for label, surface in (("historical", original), ("t2", current)):
            step = surface.step_voxels
            uv = np.meshgrid((r+np.arange(-radius, radius+1))/step,
                             (c+np.arange(-radius, radius+1))/step, indexing="ij")
            points = np.stack([map_coordinates(surface.points[..., i], uv, order=1,
                                               prefilter=False) for i in range(3)], axis=-1)
            if not np.isfinite(points).all():
                witnesses[label] = {"valid_geometry": False}
                continue
            lo = np.floor(points.min(axis=(0, 1))).astype(int) - 1
            hi = np.ceil(points.max(axis=(0, 1))).astype(int) + 2
            voxels = ct[tuple(slice(a, b) for a, b in zip(lo, hi))]
            oracle = map_coordinates(voxels.astype(float), (points-lo).reshape(-1, 3).T,
                                     order=1, mode="nearest").reshape(texture.shape[1:])
            scores = []
            for d, plane in enumerate(texture, depth_start):
                if np.ptp(plane) and np.ptp(oracle):
                    value = float(np.corrcoef(oracle.ravel(), plane.ravel())[0, 1])
                    mae = float(np.abs(oracle - plane).mean())
                    scores.append({"depth": d, "r": value, "mae_ct": mae})
            witnesses[label] = {
                "valid_geometry": True, "oracle_range": [float(oracle.min()), float(oracle.max())],
                "at_59": next((s for s in scores if s["depth"] == 59), None),
                "best": max(scores, key=lambda s: s["r"]) if scores else None,
                "oracle_sha256": sha(oracle.tobytes()),
            }
        rows.append({"pixel_vu": [r, c], "grid_vu": [v, u], "by_mesh": witnesses})
    return rows


def run(atlas, work):
    raw = atlas.read_bytes()
    catalogue = json.loads(gzip.decompress(raw) if raw.startswith(b"\x1f\x8b") else raw)
    sample = catalogue["samples"][SAMPLE]
    segment = sample["segments"][SEGMENT]
    target = [item for item in segment["data"]
              if (item.get("parameters") or {}).get("target_volume") == VOLUME]
    maps = {item["parameters"]["model_id"]: item for item in target
            if item["type"] == "ink-detection"}
    stack_uri = artifact(next(item for item in target if item["type"] == "layers-zarr"))
    meshes = {item["parameters"].get("transform_revision", "historical"): item for item in target
              if item["type"] == "tifxyz-transformed"}
    original, current = (load_tifxyz(artifact(meshes[key])) for key in ("historical", "2"))
    render, levels = open_levels(stack_uri, cache=True)
    assert levels[0].shape == (118, 1160, 1400) and levels[0].scale == (SCALE_UM,) * 3
    assert tuple(20*n for n in original.grid_shape) == levels[0].shape[1:]
    v, u = ORIGIN
    roi = np.s_[v:v+SIDE, u:u+SIDE]
    stack = render[0][(slice(47, 72), *roi)]
    assert stack.shape == (25, SIDE, SIDE) and np.ptp(stack) > 0
    ct_entry = next(item for item in sample["volumes"][VOLUME]["data"] if item["type"] == "ome-zarr")
    ct_uri = artifact(ct_entry)
    ct, _ = open_levels(ct_uri, cache=True)
    control = ct_control(ct[0], stack, original, current, ORIGIN)
    fs = fsspec.filesystem("s3", anon=True, max_concurrency=1)
    predictions = []
    for model_id in MODELS:
        scores, source = get_tiff(fs, artifact(maps[model_id]))
        cropped = scores[roi]
        image = model_id + ".tif"
        tifffile.imwrite(work / image, cropped, photometric="minisblack")
        model = catalogue["models"][model_id]
        predictions.append({"name": model["suffix"], "model": model["long_id"], "path": image,
                            "score_scale": 255, "provenance": {
                                **source, "catalogue_target": VOLUME,
                                "catalogue_model": model_id, "model_properties": model["properties"],
                                "cropped_sha256": sha(cropped.tobytes()),
                                "calibration": "undocumented",
                                "registration": "published UV raster; model render revision unknown"}})
    tifffile.imwrite(work / "ct.tif", stack[59-47], photometric="minisblack")
    tifffile.imwrite(work / "surface.tif", stack[57-47:62-47].mean(axis=0).astype("float32"),
                     photometric="minisblack")
    manifest = work / "comparison.json"
    metadata = {"version": 1, "axes": ["v", "u"], "volume_id": VOLUME, "segment_id": SEGMENT,
                "surface_revision": "published UV stack; score export revisions undocumented",
                "origin_vu": ORIGIN, "pixel_size_um_vu": [SCALE_UM]*2, "ct": "ct.tif",
                "surface": "surface.tif", "predictions": predictions}
    dump(manifest, metadata)
    comparison = load_comparison(manifest)
    a, b = comparison.predictions
    delta = comparison_values(a, b, 50, "difference")
    bands = []
    for threshold in (35, 50, 65):
        disagreement = comparison_values(a, b, threshold, "disagreement")
        consensus = comparison_values(a, b, threshold, "consensus")
        only_a, only_b = int((disagreement == 1).sum()), int((disagreement == 2).sum())
        both = int(consensus.sum())
        union = only_a + only_b + both
        bands.append({"threshold": threshold, "a_only": only_a, "b_only": only_b,
                      "both_positive": both, "both_below": int(delta.size-union),
                      "positive_jaccard": both/union if union else None})
    region = (96, 100, 160, 160)
    view = ComparisonView(0, (1, 2), 50, 80, False, region,
                          (Candidate("Zone témoin à relire", region),), "difference")
    session = work / "session.json"
    save_comparison_session(session, comparison, view)
    export_comparison_png(work / "difference.png", comparison, view)
    assert load_comparison_session(session)[1] == view
    return manifest, {"sample": SAMPLE, "segment": SEGMENT, "licence": "CC BY-NC 4.0",
                      "atlas_sha256": sha(raw), "stack": stack_uri, "volume": ct_uri,
                      "stack_shape": levels[0].shape, "stack_sha256": sha(stack.tobytes()),
                      "origin_vu": ORIGIN, "roi_shape_vu": [SIDE, SIDE],
                      "reference_depth": 59, "references": {
                          "historical": artifact(meshes["historical"]), "t2": artifact(meshes["2"])},
                      "ct_controls": control, "thresholds": bands, "models": predictions,
                      "mean_signed_score_difference": float(delta.mean()),
                      "mean_absolute_score_difference": float(np.abs(delta).mean()),
                      "source_score_ranges": [[int(plane.image.pixels.min()),
                                               int(plane.image.pixels.max())] for plane in (a, b)],
                      "manifest_sha256": comparison.manifest_sha256,
                      "session_sha256": sha(session.read_bytes())}


def napari_check(manifest):
    import napari
    import qtpy
    from napari.qt import get_qapp
    from qtpy.QtCore import Qt

    from vesuvius_data_explorer.napari.comparison_widget import ComparisonWidget

    app = get_qapp()
    viewer = napari.Viewer(show=False)
    viewer.window._qt_window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    viewer.window.resize(840, 620)
    viewer.show()
    widget = ComparisonWidget(viewer)
    viewer.window.add_dock_widget(widget, area="right")
    app.processEvents()

    def ready(condition):
        deadline = time.perf_counter() + 20
        while not condition():
            app.processEvents()
            if time.perf_counter() > deadline:
                raise TimeoutError(widget.status.text())
            time.sleep(0.001)

    try:
        start = time.perf_counter()
        widget.load(str(manifest))
        ready(widget.open_button.isEnabled)
        assert len(viewer.layers) == 4
        open_ms = (time.perf_counter()-start)*1000
        widget.prediction_b.setCurrentIndex(2)
        modes = []
        for index in (1, 2, 0):
            start = time.perf_counter()
            widget.analysis.setCurrentIndex(index)
            if not index:
                widget.disagreement.setChecked(True)
            ready(lambda: widget._analysis_worker is None)
            frame = viewer.screenshot(canvas_only=True, flash=False)[..., :3]
            assert np.ptp(frame) > 0
            layer = widget._disagreement
            modes.append({"name": layer.name, "ms_to_frame": (time.perf_counter()-start)*1000,
                          "sha256": sha(layer.data.tobytes())})
        return {"napari": napari.__version__, "qt": qtpy.QT_VERSION, "open_ms": open_ms,
                "modes": modes}
    finally:
        viewer.close()
        app.processEvents()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("atlas", type=Path)
    parser.add_argument("work", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--napari", action="store_true")
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    manifest, report = run(args.atlas, args.work)
    if args.napari:
        os.environ["NAPARI_CONFIG"] = str((args.work / "napari.yaml").resolve())
        report["napari"] = napari_check(manifest)
    dump(args.output, report)


if __name__ == "__main__":
    main()
