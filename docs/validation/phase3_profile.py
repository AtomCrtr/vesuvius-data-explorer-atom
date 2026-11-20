"""Profile the production napari opener and bounded S3/Dask reads on Windows."""

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from collections import Counter
from contextlib import ExitStack, contextmanager
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch
from urllib.parse import urlsplit

import dask
import dask.array as da
import numpy as np
import s3fs
import zarr
from aiobotocore.endpoint import AioEndpoint
from rust_bench import peak_rss
from rust_real_bench import dump
from zarr.core.codec_pipeline import BatchedCodecPipeline
from zarr.storage import FsspecStore
from zarr.storage._common import StorePath
from zarr_navigation_bench import URI

from vesuvius_data_explorer.core import volume


class Probe:
    def __init__(self, delay, interrupt):
        self.delay, self.interrupt = delay, interrupt
        self.start = perf_counter()
        self.spans, self.requests, self.stores, self.codecs = [], [], [], []
        self.stage = ""

    def now(self):
        return (perf_counter() - self.start) * 1000

    @contextmanager
    def measure(self, name):
        start, cpu = self.now(), process_time()
        try:
            yield
        finally:
            self.spans.append({"name": name, "start_ms": start, "ms": self.now() - start,
                               "process_cpu_ms": (process_time() - cpu) * 1000})

    def install(self, stack, reader):
        def wrap(module, attribute):
            original = getattr(module, attribute)

            def measured(*args, **kwargs):
                with self.measure(attribute):
                    return original(*args, **kwargs)

            stack.enter_context(patch.object(module, attribute, measured))

        for module, names in (
            (reader, ("open_levels", "estimate_contrast", "volume_summary")),
            (volume, ("open_volume_store", "list_levels", "_level_arrays", "_metadata_levels",
                      "get_array")),
            (zarr, ("open",)),
            (FsspecStore, ("from_url",)),
            (da, ("from_zarr",)),
        ):
            for name in names:
                if hasattr(module, name):
                    wrap(module, name)
        get, send = FsspecStore.get, AioEndpoint._send
        decode = BatchedCodecPipeline.decode_batch
        ensure_open = StorePath.open
        budget = 192  # Maximum data GETs per paired run on this uncompressed fixture.
        filesystem_ids = {}

        async def traced_get(store, key, prototype, byte_range=None):
            start = self.now()
            row = {"key": key, "start_ms": start, "stage": self.stage,
                   "fs": filesystem_ids.setdefault(id(store.fs), len(filesystem_ids)),
                   "range": repr(byte_range) if byte_range else None}
            try:
                if self.delay:
                    await asyncio.sleep(self.delay)
                if self.interrupt and self.stage == "interrupted" and key == ".zattrs":
                    raise ConnectionError("simulated interruption")
                result = await get(store, key, prototype, byte_range)
                row.update(bytes=len(result) if result is not None else 0, present=result is not None)
                return result
            except Exception as error:
                row["error"] = type(error).__name__
                raise
            finally:
                self.stores.append({**row, "ms": self.now() - start})

        async def traced_send(endpoint, request):
            nonlocal budget
            key = urlsplit(request.url).path
            if request.method == "GET" and key.rsplit("/", 1)[-1].isdigit():
                budget -= 1
                if budget < 0:
                    raise RuntimeError("S3 data request budget exceeded")
            _, index = endpoint_ids.setdefault(id(endpoint), (endpoint, len(endpoint_ids)))
            row = {"method": request.method, "path": key, "stage": self.stage,
                   "start_ms": self.now(), "client": index}
            try:
                response = await send(endpoint, request)
                row.update(status=response.status_code,
                           content_length=int(response.headers.get("content-length", 0)),
                           range=request.headers.get("Range", b"").decode("ascii"))
                return response
            except Exception as error:
                row["error"] = type(error).__name__
                raise
            finally:
                self.requests.append({**row, "headers_ms": self.now() - row["start_ms"]})

        async def traced_decode(pipeline, *args, **kwargs):
            started = self.now()
            try:
                return await decode(pipeline, *args, **kwargs)
            finally:
                self.codecs.append({"stage": self.stage, "start_ms": started,
                                    "ms": self.now() - started})

        async def traced_open(*args, **kwargs):
            with self.measure("store_path_open"):
                return await ensure_open(*args, **kwargs)

        endpoint_ids = {}
        stack.enter_context(patch.object(FsspecStore, "get", traced_get))
        stack.enter_context(patch.object(AioEndpoint, "_send", traced_send))
        stack.enter_context(patch.object(BatchedCodecPipeline, "decode_batch", traced_decode))
        stack.enter_context(patch.object(StorePath, "open", traced_open))
        return endpoint_ids


def gpu_bytes():
    """Dedicated allocations summed across the process's WDDM adapter instances."""
    if os.name != "nt":
        return None
    command = (r"(Get-Counter '\GPU Process Memory(*)\Dedicated Usage').CounterSamples "
               f"| Where-Object InstanceName -like 'pid_{os.getpid()}_*' "
               "| Measure-Object -Property CookedValue -Sum | Select-Object -ExpandProperty Sum")
    try:
        result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command],
                                capture_output=True, text=True, timeout=10, check=False)
    except subprocess.TimeoutExpired:
        return None
    value = result.stdout.strip()
    return int(float(value)) if result.returncode == 0 and value else None


def digest(array):
    return hashlib.sha256(np.ascontiguousarray(array).view("u1")).hexdigest()


def dask_reads(probe, arrays, reverse):
    results = []
    for level_index in (0, 2, 5):
        source = arrays[level_index]
        with probe.measure("dask_graph_construction"):
            graph = da.from_zarr(source)
        z, y, x = (min((dim // 2 // chunk + 1) * chunk, dim - 2)
                   for dim, chunk in zip(source.shape, source.chunks))
        selections = ((z - 1, slice(y - 24, y + 24), slice(x - 24, x + 24)),
                      (slice(z - 24, z + 24), y, slice(x - 24, x + 24)))
        for selection in selections:
            pair = {}
            for engine in (("dask", "zarr") if reverse else ("zarr", "dask")):
                probe.stage = f"roi_l{level_index}_{len(results)}_{engine}"
                tasks = []
                if engine == "dask":
                    with probe.measure("dask_graph_selection"):
                        roi = graph[selection]
                    with dask.callbacks.Callback(pretask=lambda key, *_: tasks.append(str(key))):
                        with probe.measure("dask_compute"):
                            pixels = roi.compute(scheduler="threads")
                else:
                    with probe.measure("zarr_selection"):
                        pixels = source[selection]
                pair[engine] = {"sha256": digest(pixels), "tasks": tasks,
                                "decoded_result_bytes": pixels.nbytes}
            assert pair["zarr"]["sha256"] == pair["dask"]["sha256"]
            results.append({"level": level_index, "selection": repr(selection), **pair})
    return results


def metadata_run(folder):
    from aiohttp import TCPConnector

    from vesuvius_data_explorer.napari import reader

    probe = Probe(delay=0, interrupt=False)
    os.environ["XDG_CACHE_HOME"] = str(folder)
    socket_connect = TCPConnector._create_connection
    sockets = []

    async def traced_connect(*args, **kwargs):
        start = probe.now()
        stage = probe.stage
        try:
            return await socket_connect(*args, **kwargs)
        finally:
            sockets.append({"stage": stage, "start_ms": start, "ms": probe.now() - start})

    with ExitStack() as stack:
        stack.enter_context(patch.object(TCPConnector, "_create_connection", traced_connect))
        connections = probe.install(stack, reader)
        for state in ("cold", "warm"):
            probe.stage = state
            with probe.measure(f"{state}_open_metadata"):
                _, levels = reader.open_levels(URI)
                summary = volume.volume_summary(levels)
    return {"spans": probe.spans, "http": probe.requests, "source_reads": probe.stores,
            "s3_clients": len(connections), "tcp_tls": sockets, "levels": summary}


def run(folder, delay, interrupt, reverse, include_gpu):
    import napari
    from napari.settings import get_settings
    from qtpy.QtCore import Qt, QTimer
    from qtpy.QtWidgets import QApplication

    from vesuvius_data_explorer.napari import reader
    from vesuvius_data_explorer.napari.widget import OpenVolumeWidget

    probe = Probe(delay, interrupt)
    get_settings().experimental.async_ = True
    viewer = None
    app = QApplication.instance()
    if app is None:
        from napari.qt import get_qapp

        app = get_qapp()
    ticks = []
    timer = QTimer()
    timer.setTimerType(Qt.TimerType.PreciseTimer)
    timer.timeout.connect(lambda: ticks.append(probe.now()))
    timer.start(10)

    def wait(condition, label):
        deadline = perf_counter() + 90
        while not condition():
            app.processEvents()
            if perf_counter() >= deadline:
                raise TimeoutError(f"{label}: {opener.status_label.text()}")
            time.sleep(0.001)

    def frame(layer):
        native = np.asarray(layer._slice.image.raw)
        rgb = viewer.screenshot(canvas_only=True, flash=False)[..., :3]
        if not np.ptp(rgb) or native.ndim != 2 or not np.ptp(native):
            raise RuntimeError("No nonuniform native data and OpenGL frame")
        return {"selected_level": int(layer.data_level), "sha256": digest(native),
                "slice_shape": native.shape, "slice_dtype": str(native.dtype),
                "rgb_max": int(rgb.max()), "point": viewer.dims.point,
                "data_point": layer._slice.slice_input.world_slice.point}

    def open_image(label, navigate=False):
        nonlocal viewer, opener
        if viewer is not None:
            viewer.close()
            app.processEvents()
        viewer = napari.Viewer(show=False)
        viewer.window._qt_window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        viewer.window.resize(840, 620)
        viewer.show()
        opener = OpenVolumeWidget(viewer)
        viewer.window.add_dock_widget(opener, area="right")
        opener.path_input.setText(URI)
        app.processEvents()
        probe.stage = label
        start = probe.now()
        with probe.measure("widget_open_until_layer"):
            opener.open_button.click()
            wait(opener.open_button.isEnabled, label)
        if not viewer.layers:
            return {"error": opener.status_label.text(), "elapsed_ms": probe.now() - start}
        image = viewer.layers[0]
        with probe.measure("wait_for_initial_slice"):
            wait(lambda: image.loaded and not image._slice.empty, label)
        with probe.measure("opengl_frame"):
            first = frame(image)
        elapsed = probe.now() - start
        navigation = []
        for index in (11800, 12260, 11800, 12040) if navigate else ():
            probe.stage = f"{label}_navigate_{len(navigation)}"
            with probe.measure("navigate_until_frame"):
                previous = image._slice.request_id
                viewer.dims.set_point(0, index)
                app.processEvents()
                wait(lambda: image.loaded and image._slice.request_id != previous, str(index))
                navigation.append(frame(image))
        return {"first_frame_ms": elapsed, "first": first, "navigation": navigation}

    opener = None
    try:
        os.environ["XDG_CACHE_HOME"] = str(folder)
        with ExitStack() as stack:
            connections = probe.install(stack, reader)
            failure = open_image("interrupted") if interrupt else None
            if failure and "error" not in failure:
                raise AssertionError("Fault did not reach the widget")
            cold = open_image("cold", navigate=True)
            if "error" in cold:
                raise RuntimeError(cold["error"])
            warm = open_image("warm")
            if "error" in warm:
                raise RuntimeError(warm["error"])
            a, b = (cold["navigation"][i] for i in (0, 2))
            assert a["sha256"] == b["sha256"], (a, b)
            arrays = list(viewer.layers[0].data)
            dedicated = gpu_bytes() if include_gpu else None
            rois = [] if interrupt else dask_reads(probe, arrays, reverse)
        return {"cold": cold, "warm": warm, "failure": failure, "rois": rois,
                "spans": probe.spans, "http": probe.requests, "source_reads": probe.stores,
                "codec_decode": probe.codecs, "qt_tick_ms": ticks, "s3_clients": len(connections),
                "requests_by_stage": dict(Counter(row["stage"] for row in probe.requests)),
                "rss_peak_bytes": peak_rss(), "frame_dedicated_gpu_bytes": dedicated,
                "napari": napari.__version__, "qpa": app.platformName()}
    finally:
        timer.stop()
        if viewer is not None:
            viewer.close()
        app.processEvents()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--delay", type=float, default=0, help="Seconds per remote get")
    parser.add_argument("--interrupt", action="store_true", help="Fail one metadata stage")
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--worker", type=int)
    args = parser.parse_args()
    if args.worker is not None:
        result = (metadata_run(args.work) if args.metadata_only
                  else run(args.work, args.delay, args.interrupt, bool(args.worker % 2), True))
        print(json.dumps(result))
        return
    args.work.mkdir(parents=True, exist_ok=True)
    report = {"uri": URI, "zarr": zarr.__version__, "dask": dask.__version__,
              "s3fs": s3fs.__version__, "delay_s": args.delay, "rows": []}
    for repeat in range(args.repeats):
        with tempfile.TemporaryDirectory(prefix="profile-", dir=args.work) as tmp:
            folder = Path(tmp).resolve()
            env = {**os.environ, "NAPARI_CONFIG": str(folder / "napari.yaml"),
                   "XDG_CACHE_HOME": str(folder / "cache"), "VESUVIUS_CACHE": "1"}
            command = [sys.executable, __file__, str(folder), str(args.output),
                       "--worker", str(repeat), "--delay", str(args.delay)]
            if args.interrupt:
                command.append("--interrupt")
            if args.metadata_only:
                command.append("--metadata-only")
            result = subprocess.run(command, env=env, capture_output=True, encoding="utf-8",
                                    timeout=240, check=False)
            if result.returncode:
                raise RuntimeError(result.stderr)
            report["rows"].append(json.loads(result.stdout))
            dump(args.output, report)
            print(f"Pair {repeat + 1}/{args.repeats}", flush=True)


if __name__ == "__main__":
    main()
