"""Time the real napari plugin and OpenGL drawing on bounded public-data crops."""

import argparse
import json
import os
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from time import perf_counter, process_time

import numpy as np
import zarr
from rust_bench import peak_rss
from rust_real_bench import distribution, dump

from vesuvius_data_explorer.core.tifxyz import load_tifxyz, write_tifxyz


def local_pyramid(root, case, destination):
    source = root / case["name"]
    data = np.load(source / "ct.npy", mmap_mode="r")
    volume = destination / "viewer.zarr"
    group = zarr.open_group(str(volume), mode="w", zarr_format=2)
    datasets = []
    for level, pixels in enumerate((data, data[::3, ::3, ::3])):
        key = str(level)
        group.create_array(key, data=pixels, chunks=(128, 128, 128), compressor=None)
        scale = [3**level] * 3
        datasets.append({"path": key, "coordinateTransformations": [{"type": "scale", "scale": scale}]})
    group.attrs["multiscales"] = [{"version": "0.4", "axes": ["z", "y", "x"], "datasets": datasets}]
    surface = load_tifxyz(str(source / "segment"))
    points = (surface.points + 0.5) / np.asarray(case["factor_zyx"]) - 0.5 - case["lo_zyx"]
    write_tifxyz(destination / "surface", points, {**surface.meta, "scale": [
        float(np.mean(case["factor_zyx"])) / surface.step_voxels] * 2})
    dump(destination / "fixture.json", {"pixel_size_um":
         case["pixel_size_um"] * float(np.mean(case["factor_zyx"]))})


class TimedArray:
    def __init__(self, array, events):
        self.array, self.events = array, events
        self.shape, self.chunks, self.dtype = array.shape, array.chunks, array.dtype

    def __getitem__(self, key):
        started = perf_counter()
        data = np.asarray(self.array[key])
        self.events.append((started, perf_counter(), data.nbytes))
        return data


def active_ms(events):
    duration, end = 0.0, 0.0
    for a, b, _ in sorted(events):
        duration += max(0, b - max(a, end))
        end = max(end, b)
    return duration * 1e3


def worker(folder, backend, repeats):
    os.environ["NAPARI_CONFIG"] = str((folder / f"{backend}-settings.yaml").resolve())
    os.environ["XDG_CACHE_HOME"] = str((folder / f"{backend}-cache").resolve())
    os.environ["VESUVIUS_RUST_SAMPLER"] = "1" if backend == "rust" else "0"
    import napari
    import qtpy
    from napari.settings import get_settings
    from qtpy.QtCore import Qt
    from qtpy.QtWidgets import QApplication
    from vispy.gloo import gl

    from vesuvius_data_explorer.core import chunkcache
    from vesuvius_data_explorer.napari import surface_widget
    from vesuvius_data_explorer.napari.qc_widget import camera
    from vesuvius_data_explorer.napari.widget import OpenVolumeWidget

    if backend == "rust" and chunkcache._rust_sampler() is None:
        raise RuntimeError("The Rust wheel is required")
    measurements = []
    original_measure = surface_widget.measure_drift

    def measure(overlay, arrays, shapes, pixel_size_um):
        events = []
        started = perf_counter()
        result = original_measure(overlay, [TimedArray(array, events) for array in arrays],
                                  shapes, pixel_size_um)
        measurements.append({"worker_ms": (perf_counter() - started) * 1e3,
                             "array_union_ms": active_ms(events), "array_reads": len(events),
                             "decoded_bytes": sum(row[2] for row in events)})
        return result

    surface_widget.measure_drift = measure
    get_settings().experimental.async_ = True
    viewer = napari.Viewer(show=False)
    app = QApplication.instance()
    viewer.window._qt_window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    viewer.window.resize(840, 620)
    viewer.show()
    app.processEvents()

    def wait(condition, context):
        end = perf_counter() + 30
        while not condition():
            app.processEvents()
            if perf_counter() > end:
                raise RuntimeError(context)
            time.sleep(0.001)

    def draw():
        frame = viewer.screenshot(canvas_only=True, flash=False)
        if frame.ndim != 3 or min(frame.shape[:2]) < 32 or not frame[:, :, -1].any():
            raise RuntimeError("No OpenGL frame")
        return frame

    def operation(action, done, label):
        started = perf_counter()
        action()
        app.processEvents()
        wait(done, label)
        ready = perf_counter()
        draw()
        end = perf_counter()
        return {"ready_ms": (ready - started) * 1e3, "draw_ms": (end - ready) * 1e3,
                "through_frame_ms": (end - started) * 1e3}

    try:
        start_cpu = process_time()
        opener = OpenVolumeWidget(viewer)
        viewer.window.add_dock_widget(opener, area="right")
        opener.path_input.setText(str((folder / "viewer.zarr").resolve()))
        started = perf_counter()
        opener.open_button.click()
        wait(lambda: len(viewer.layers) == 1 and opener.open_button.isEnabled(), "open volume")
        image = viewer.layers[0]
        image.metadata["pixel_size_um"] = json.loads((folder / "fixture.json").read_text(
            encoding="utf-8"))["pixel_size_um"]
        opening_ms = (perf_counter() - started) * 1e3
        wait(lambda: image.loaded, "initial volume view")
        surface = load_tifxyz(str(folder / "surface"))
        z, y, x = np.nanmedian(surface.points, axis=(0, 1))
        camera(viewer).center = (float(y), float(x))
        camera(viewer).zoom = 1.0
        app.processEvents()
        wait(lambda: image.loaded, "centered volume view")
        frame = draw()
        origin = int(z)
        levels = []

        def read_index(index):
            if viewer.dims.point[0] == index:
                raise RuntimeError("Slice trajectory contains a no-op")
            return operation(lambda: viewer.dims.set_point(0, index), lambda: image.loaded,
                             f"slice {index}")

        first = read_index(origin - 4)
        slices = []
        for index in (origin - 3, origin - 2, origin - 1, origin, origin + 1, origin + 2,
                      origin + 3, origin + 4, origin, origin - 1, origin + 1, origin + 2):
            row = read_index(index)
            levels.append(int(image.data_level))
            slices.append(row)
        widget = surface_widget.SurfaceWidget(viewer)
        viewer.window.add_dock_widget(widget, area="right")
        widget.path_input.setText(str((folder / "surface").resolve()))
        overlay = operation(widget.overlay_button.click, lambda: widget._overlay is not None and
                            widget._worker is None, "load original tifxyz overlay")
        drift_ms = []
        for _ in range(repeats):
            previous = widget._drift_layer
            drift_ms.append(operation(widget.drift_button.click, lambda: widget._worker is None and
                            widget._drift_layer is not None and widget._drift_layer is not previous,
                            "render drift layer"))
            drift_ms[-1].update(measurements[-1])
        canvas = viewer.window._qt_viewer.canvas._scene_canvas
        canvas.set_current()
        return {"backend": backend, "napari": napari.__version__, "qt": qtpy.QT_VERSION,
                "qpa": app.platformName(), "opengl_renderer": gl.glGetParameter(gl.GL_RENDERER),
                "frame_shape": frame.shape, "initial_rgb_max": int(frame[:, :, :3].max()),
                "opening_ms": opening_ms, "first_requested_slice": first, "selected_levels": levels,
                "steps": slices, "navigation": distribution([r["through_frame_ms"] for r in slices]),
                "overlay": overlay, "drifts": drift_ms, "drift": distribution(
                    [r["through_frame_ms"] for r in drift_ms]), "drift_label": widget.drift_label.text(),
                "rss_peak_bytes": peak_rss(), "cpu_ms": (process_time() - start_cpu) * 1e3}
    finally:
        surface_widget.measure_drift = original_measure
        viewer.close()
        app.processEvents()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--worker", choices=("python", "rust"))
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(args.root, args.worker, args.repeats), ensure_ascii=True))
        return
    if not args.output:
        parser.error("--output required")
    cases = json.loads((args.root / "corpus.json").read_text(encoding="utf-8"))
    if args.case:
        cases = [case for case in cases if case["name"] in args.case]
        if not cases:
            parser.error("No selected case in the corpus")
    rows = []
    rng = random.Random(2026)
    for case in cases:
        with tempfile.TemporaryDirectory(prefix="napari-bench-", dir=args.root) as tmp:
            folder = Path(tmp)
            local_pyramid(args.root, case, folder)
            names = rng.sample(["python", "rust"], 2)
            records = {}
            for name in names:
                process = subprocess.run([sys.executable, __file__, str(folder), "--worker", name,
                                         "--repeats", str(args.repeats)], capture_output=True,
                                         encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
                if process.returncode:
                    raise RuntimeError(f"{case['name']}/{name}\n{process.stderr}")
                records[name] = json.loads(process.stdout)
            assert records["rust"]["drift_label"] == records["python"]["drift_label"]
            rows.append({"case": case["name"], **records})
            dump(args.output, rows)
            print(f"Measured napari/{case['name']}", flush=True)


if __name__ == "__main__":
    main()
