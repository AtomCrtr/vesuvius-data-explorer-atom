"""Attribute Windows Qt timer gaps to napari, Vispy and plugin call sites."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
from functools import wraps
from pathlib import Path
from time import thread_time
from unittest.mock import patch

import numpy as np
import phase3_profile


def worker(folder):
    import dask.array as da
    import zarr
    from napari._qt.qt_viewer import QtViewer
    from napari._vispy.layers.scalar_field import VispyScalarFieldBaseLayer
    from napari.layers.image.image import Image, _ImageSlicingState
    from napari.viewer import Viewer
    from vispy.gloo.glir import GlirProgram, GlirShader, GlirTexture2D
    from vispy.scene.canvas import SceneCanvas

    from vesuvius_data_explorer.napari.widget import OpenVolumeWidget

    scopes = []
    gui = threading.get_ident()
    original_probe = phase3_profile.Probe.install
    targets = (
        (OpenVolumeWidget, "_loaded"), (OpenVolumeWidget, "_show_cache_size"),
        (Viewer, "add_image"), (Viewer, "add_layer"), (Image, "__init__"), (QtViewer, "_add_layer"),
        (Image, "_raw_to_displayed"), (_ImageSlicingState, "_update_slice_response"),
        (VispyScalarFieldBaseLayer, "_on_data_change"), (SceneCanvas, "_draw_scene"),
        (GlirShader, "set_data"), (GlirProgram, "draw"), (GlirTexture2D, "set_data"),
        (QtViewer, "_screenshot"), (zarr.Array, "__getitem__"), (da.Array, "compute"),
    )

    def trace(probe, owner, name):
        original = getattr(owner, name)
        label = f"{owner.__name__}.{name}"

        @wraps(original)
        def call(*args, **kwargs):
            start, cpu = probe.now(), thread_time()
            stage = probe.stage
            try:
                return original(*args, **kwargs)
            finally:
                scopes.append({"call": label, "stage": stage, "start_ms": start,
                               "ms": probe.now() - start, "cpu_ms": (thread_time() - cpu)*1000,
                               "gui": threading.get_ident() == gui})

        return call

    def install(probe, stack, reader):
        result = original_probe(probe, stack, reader)
        for owner, name in targets:
            stack.enter_context(patch.object(owner, name, trace(probe, owner, name)))
        return result

    with patch.object(phase3_profile.Probe, "install", install):
        report = phase3_profile.run(folder, delay=0, interrupt=False, reverse=False,
                                    include_gpu=False)
    report["ui_scopes"] = scopes
    spans = sorted([s for s in report["spans"] if s["name"] == "widget_open_until_layer"],
                   key=lambda s: s["start_ms"])
    report["ui_gaps"] = {}
    for phase, span in zip(("cold", "warm"), spans):
        lo = span["start_ms"]
        hi = lo + report[phase]["first_frame_ms"]
        times = [t for t in report["qt_tick_ms"] if lo <= t <= hi]
        gaps = sorted(zip(times, times[1:]), key=lambda pair: pair[1]-pair[0], reverse=True)
        longest = []
        for start, stop in gaps[:5]:
            matching = [{**row, "overlap_ms": min(stop, row["start_ms"]+row["ms"])
                         - max(start, row["start_ms"])}
                        for row in scopes if row["gui"] and
                        start < row["start_ms"]+row["ms"] and row["start_ms"] < stop]
            longest.append({"start_ms": start, "gap_ms": stop-start,
                            "overlapping": sorted(matching, key=lambda r: -r["overlap_ms"])[:12]})
        report["ui_gaps"][phase] = {"p50": float(np.median(np.diff(times))),
                                   "p95": float(np.percentile(np.diff(times), 95)),
                                   "max": longest[0]["gap_ms"], "longest": longest}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(args.work)))
        return
    args.work.mkdir(parents=True, exist_ok=True)
    rows = []
    for _ in range(args.repeats):
        with tempfile.TemporaryDirectory(prefix="phase4-ui-", dir=args.work) as path:
            folder = Path(path).resolve()
            env = {**os.environ, "NAPARI_CONFIG": str(folder/"napari.yaml"),
                   "XDG_CACHE_HOME": str(folder/"cache"), "VESUVIUS_CACHE": "1"}
            result = subprocess.run(
                [sys.executable, __file__, str(folder), str(args.output), "--worker"],
                env=env, check=False, capture_output=True, encoding="utf-8", timeout=240,
            )
            if result.returncode:
                raise RuntimeError(result.stderr)
            rows.append(json.loads(result.stdout))
            args.output.write_text(json.dumps(rows, indent=2)+"\n", encoding="utf-8")
            print(f"{len(rows)}/{args.repeats}", flush=True)


if __name__ == "__main__":
    main()
