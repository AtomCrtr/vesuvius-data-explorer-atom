"""Measure descriptive consensus and optional native napari rendering on local crops."""

import argparse
import json
import os
import platform
import subprocess
from pathlib import Path
from time import perf_counter, sleep

import numpy as np
import psutil
from phase3_profile import gpu_bytes
from phase4_ink import dump, sha

from vesuvius_data_explorer.core.comparison import load_comparison
from vesuvius_data_explorer.core.consensus import analyze_pair

THRESHOLDS = tuple(range(5, 100, 5))


def summary(values):
    return dict(zip(("p50", "p95", "max"), np.percentile(values, [50, 95, 100]).tolist()))


def renderer_info():
    command = ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"]
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=10,
                              check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def measure_napari(manifest):
    import napari
    import qtpy
    from napari.qt import get_qapp
    from qtpy.QtCore import Qt, QTimer
    from vispy.gloo import gl

    from vesuvius_data_explorer.napari.comparison_widget import ComparisonWidget

    app = get_qapp()
    viewer = napari.Viewer(show=False)
    viewer.window._qt_window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    viewer.window.resize(900, 640)
    viewer.show()
    widget = ComparisonWidget(viewer)
    viewer.window.add_dock_widget(widget, area="right")
    ticks = []
    timer = QTimer()
    timer.setTimerType(Qt.TimerType.PreciseTimer)
    timer.setInterval(8)
    timer.timeout.connect(lambda: ticks.append(perf_counter()))

    def ready(condition):
        deadline = perf_counter() + 20
        while not condition():
            app.processEvents()
            if perf_counter() > deadline:
                raise TimeoutError(widget.status.text())
            sleep(0.001)
        app.processEvents()

    def pause():
        end = perf_counter() + 0.070
        ready(lambda: perf_counter() >= end)

    try:
        timer.start()
        app.processEvents()
        start = perf_counter()
        widget.load(str(manifest))
        ready(widget.open_button.isEnabled)
        assert len(viewer.layers) == 4
        open_ms = (perf_counter()-start)*1000
        widget.prediction_b.setCurrentIndex(2)
        samples = []
        pause()
        startup_ticks = len(ticks)
        startup_gaps = summary(np.diff(ticks)*1000)
        ticks.clear()
        pause()
        for _ in range(3):
            for index in (2, 3, 0):
                start = perf_counter()
                widget.analysis.setCurrentIndex(index)
                widget.disagreement.setChecked(index == 0)
                ready(lambda: widget._analysis_worker is None)
                layer = widget._disagreement
                layer_ready = perf_counter()
                frame = viewer.screenshot(canvas_only=True, flash=False)
                assert layer.visible and np.ptp(frame[..., :3]) > 0
                samples.append({"mode": layer.metadata["mode"],
                                "ms_to_layer": (layer_ready-start)*1000,
                                "ms_to_frame": (perf_counter()-start)*1000,
                                "sha256": sha(layer.data.tobytes())})
                pause()
        canvas = viewer.window._qt_viewer.canvas
        canvas.native.makeCurrent()
        gpu = gl.glGetParameter(gl.GL_RENDERER)
        if isinstance(gpu, bytes):
            gpu = gpu.decode()
        timer.stop()
        dedicated = gpu_bytes()
        return {"qt": qtpy.QT_VERSION, "napari": napari.__version__, "open_ms": open_ms,
                "opengl_renderer": gpu, "process_dedicated_gpu_bytes": dedicated,
                "timer_interval_ms": timer.interval(),
                "startup_timer_gaps_ms": startup_gaps, "startup_timer_ticks": startup_ticks,
                "analysis_timer_gaps_ms": summary(np.diff(ticks)*1000),
                "analysis_timer_ticks": len(ticks),
                "frames": samples}
    finally:
        timer.stop()
        viewer.close()
        app.processEvents()


def plot(path, report):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (left, right) = plt.subplots(1, 2, figsize=(10.5, 3.8), layout="constrained")
    rows = report["thresholds"]
    thresholds = [r["thresholds_percent"][0] for r in rows]
    for key, label in (("jaccard", "Jaccard"), ("dice", "Dice"),
                       ("disagreement_rate", "Désaccord")):
        left.plot(thresholds, [r[key] for r in rows], "o-", markersize=2, label=label)
    left.set(xlabel="Seuil du score normalisé (%)", ylabel="Proportion", ylim=(0, 1))
    left.legend()
    for diagram, model in zip(report["score_distributions"], report["models"]):
        right.stairs(np.array(diagram["counts"])/diagram["finite_pixels"],
                     diagram["normalized_bin_edges"], label=model["name"].split()[0])
    right.set(xlabel="Score normalisé", ylabel="Fraction par classe")
    right.legend()
    fig.suptitle("PHerc0500P2 · Accord descriptif dans la fenêtre CT 384 × 384")
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--napari", action="store_true")
    parser.add_argument("--plot", type=Path)
    args = parser.parse_args()
    process = psutil.Process()
    comparison = load_comparison(args.manifest)
    roi = (0, 0, *comparison.ct.pixels.shape)
    rss_before = process.memory_info().rss
    elapsed, digests = [], []
    for _ in range(7):
        start = perf_counter()
        report = analyze_pair(comparison, (1, 2), roi, THRESHOLDS)
        elapsed.append((perf_counter()-start)*1000)
        digests.append(sha(json.dumps(report, sort_keys=True).encode()))
    assert len(set(digests)) == 1
    for row in report["thresholds"]:
        union = row["both_positive"] + row["a_only"] + row["b_only"]
        row["selected_by_strategy"] = {"A": row["both_positive"] + row["a_only"],
                                       "B": row["both_positive"] + row["b_only"],
                                       "intersection": row["both_positive"], "union": union}
    result = {"python": platform.python_version(), "system": platform.platform(),
              "nvidia_smi": renderer_info(), "cpu_pair_analysis_ms": elapsed,
              "cpu_summary_ms": summary(elapsed), "rss_before_cpu_bytes": rss_before,
              "rss_after_cpu_bytes": process.memory_info().rss,
              "repeated_report_sha256": digests[0], "agreement": report}
    if args.napari:
        os.environ.setdefault("NAPARI_CONFIG", str(args.manifest.parent.resolve() / "napari.yaml"))
        result["napari"] = measure_napari(args.manifest)
    dump(args.output, result)
    if args.plot:
        plot(args.plot, report)


if __name__ == "__main__":
    main()
