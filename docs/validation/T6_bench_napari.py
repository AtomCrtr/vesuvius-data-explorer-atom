"""T6 validation: scripted napari timings on a real volume.

Opens PHerc0800 20250521135224, shows a level-0 2D view, steps through slices, overlays a VC3D
segment and measures its alignment twice. Prints one JSON line. Usage, under a display (Xvfb):

    python T6_bench_napari.py LABEL

Run it with ``XDG_CACHE_HOME`` pointing to an empty folder for a cold cache, then again for a
warm cache. To time another version of the plugin, put its ``src`` first on ``PYTHONPATH``.
"""

import json
import os
import sys
import tempfile
import time

# napari reads NAPARI_CONFIG on first use: keep the user's preferences untouched.
os.environ["NAPARI_CONFIG"] = os.path.join(tempfile.mkdtemp(), "settings.yaml")

import napari  # noqa: E402
from napari.settings import get_settings  # noqa: E402
from qtpy.QtWidgets import QApplication  # noqa: E402

from vesuvius_data_explorer.napari.qc_widget import camera  # noqa: E402
from vesuvius_data_explorer.napari.surface_widget import SurfaceWidget  # noqa: E402
from vesuvius_data_explorer.napari.widget import OpenVolumeWidget  # noqa: E402

VOLUME = ("s3://vesuvius-challenge-open-data/PHerc0800/volumes/"
          "20250521135224-8.640um-1.2m-116keV-masked.zarr")
SEGMENT = ("s3://vesuvius-challenge-open-data/PHerc0800/segments/20251029010146-auto_grown_"
           "20251029010146642/mesh/20251029010146-on-20250521135224-8.64um.tifxyz")


def main(label: str) -> dict:
    get_settings().experimental.async_ = True
    viewer = napari.Viewer(show=True)
    viewer.window.resize(1500, 950)
    app = QApplication.instance()

    def wait(condition, timeout=300):
        end = time.time() + timeout
        while not condition() and time.time() < end:
            app.processEvents()
            time.sleep(0.01)
        assert condition(), "timeout"

    results = {"version": label}
    opener = OpenVolumeWidget(viewer)
    viewer.window.add_dock_widget(opener, area="right")
    opener.path_input.setText(VOLUME)
    started = time.time()
    opener._open()
    wait(lambda: opener.open_button.isEnabled())
    results["open_s"] = round(time.time() - started, 2)
    image = viewer.layers[0]
    results["contrast"] = [float(v) for v in image.contrast_limits]
    for _ in range(20):
        app.processEvents()
        time.sleep(0.02)
    cam = camera(viewer)
    cam.center = (6260.0, 3396.0)  # around the segment
    cam.zoom = 1.0  # one screen pixel per level-0 voxel: napari shows level 0

    def step(z):
        started = time.time()
        viewer.dims.set_point(0, z)
        for _ in range(3):
            app.processEvents()
        wait(lambda: image.loaded)
        return time.time() - started

    results["first_view_s"] = round(step(12058.0), 2)
    results["level_shown"] = int(image.data_level)
    results["next_slice_s"] = round(step(12059.0), 2)
    results["ten_next_slices_s"] = round(sum(step(12060.0 + i) for i in range(10)), 2)
    surfaces = SurfaceWidget(viewer)
    viewer.window.add_dock_widget(surfaces, area="right")
    surfaces.path_input.setText(SEGMENT)
    surfaces._overlay_clicked()
    wait(lambda: surfaces._worker is None and surfaces._overlay is not None)
    for key in ("alignment_cold_s", "alignment_again_s"):
        started = time.time()
        surfaces._align_clicked()
        wait(lambda: surfaces._worker is None and surfaces.align_label.text() != "")
        results[key] = round(time.time() - started, 2)
        surfaces.align_label.setText("")
    return results


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1] if len(sys.argv) > 1 else "run")), flush=True)
    os._exit(0)  # skip the slow teardown of Qt and of open network sessions
