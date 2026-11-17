"""Offscreen integration: real viewer, async open, errors and npe2 registration."""

import threading

import pytest

pytest.importorskip("napari")
pytest.importorskip("qtpy")
from qtpy.QtCore import Qt  # noqa: E402

from vesuvius_data_explorer.napari.widget import OpenVolumeWidget  # noqa: E402


def test_async_widget_adds_one_multiscale_layer(
    napari_pyramid, make_napari_viewer, qtbot, monkeypatch
):
    from vesuvius_data_explorer.napari import widget as widget_module

    real_read = widget_module.read_volume
    entered = threading.Event()
    release = threading.Event()
    worker_threads = []

    def slow_read(path):
        worker_threads.append(threading.get_ident())
        entered.set()
        assert release.wait(10)
        return real_read(path)

    monkeypatch.setattr(widget_module, "read_volume", slow_read)
    viewer = make_napari_viewer()
    widget = OpenVolumeWidget(viewer)
    qtbot.addWidget(widget)
    widget.path_input.setText(str(napari_pyramid))
    qtbot.mouseClick(widget.open_button, Qt.LeftButton)
    try:
        qtbot.waitUntil(entered.is_set)
        assert not widget.open_button.isEnabled()
        assert worker_threads[0] != threading.get_ident()
    finally:
        release.set()
    qtbot.waitUntil(lambda: widget.open_button.isEnabled(), timeout=20000)
    assert len(viewer.layers) == 1
    layer = viewer.layers[0]
    assert layer.multiscale and len(layer.data) == 3
    assert tuple(layer.scale) == (0.5, 1, 2)
    assert layer.contrast_limits == pytest.approx((192.95, 286.05))
    assert layer.metadata["volume_summary"]["level_count"] == 3
    assert widget.summary_table.rowCount() == 3
    assert widget.summary_table.item(0, 0).text() == "fine"
    assert "ouvert" in widget.status_label.text().lower()


@pytest.mark.parametrize(
    "source, message",
    [
        ("", "chemin"),
        ("missing", "introuvable"),
        ("https://example.org/scan.zarr", "HTTPS"),
        ("empty", "3D"),
    ],
)
def test_widget_errors_are_french_and_leave_viewer_empty(
    source, message, tmp_path, make_napari_viewer, qtbot
):
    import zarr

    if source == "missing":
        source = str(tmp_path / "absent.zarr")
    if source == "empty":
        source = str(tmp_path / "empty.zarr")
        zarr.open_group(source, mode="w")
    viewer = make_napari_viewer()
    widget = OpenVolumeWidget(viewer)
    qtbot.addWidget(widget)
    widget.path_input.setText(source)
    qtbot.mouseClick(widget.open_button, Qt.LeftButton)
    qtbot.waitUntil(lambda: widget.open_button.isEnabled(), timeout=20000)
    assert message in widget.status_label.text()
    assert "Traceback" not in widget.status_label.text()
    assert len(viewer.layers) == 0


def test_manifest_instantiates_widget(make_napari_viewer):
    viewer = make_napari_viewer()
    _, widget = viewer.window.add_plugin_dock_widget("vesuvius-data-explorer")
    assert isinstance(widget, OpenVolumeWidget)


def test_open_and_navigation_never_compute_dask_on_gui_thread(
    napari_pyramid, make_napari_viewer, qtbot, monkeypatch
):
    import dask.array as da

    compute_threads = []
    original = da.Array.compute

    def tracked_compute(array, *args, **kwargs):
        compute_threads.append(threading.get_ident())
        return original(array, *args, **kwargs)

    monkeypatch.setattr(da.Array, "compute", tracked_compute)
    viewer = make_napari_viewer()
    widget = OpenVolumeWidget(viewer)
    qtbot.addWidget(widget)
    widget.path_input.setText(str(napari_pyramid))
    qtbot.mouseClick(widget.open_button, Qt.LeftButton)
    qtbot.waitUntil(lambda: widget.open_button.isEnabled(), timeout=20000)
    assert len(viewer.layers) == 1
    viewer.dims.set_point(0, 2)
    # Complete pending slices while continuing to process main-thread Qt events.
    qtbot.waitUntil(lambda: viewer.layers[0].loaded, timeout=20000)
    assert compute_threads
    assert threading.get_ident() not in compute_threads


def test_registered_reader_adds_one_image_layer(napari_pyramid, make_napari_viewer, qtbot):
    viewer = make_napari_viewer()
    layers = viewer.open(str(napari_pyramid), plugin="vesuvius-data-explorer")
    assert len(layers) == 1 and len(viewer.layers) == 1
    assert layers[0].multiscale and len(layers[0].data) == 3
    assert tuple(layers[0].scale) == (0.5, 1, 2)
    assert layers[0].contrast_limits == pytest.approx((192.95, 286.05))
    qtbot.waitUntil(lambda: layers[0].loaded, timeout=20000)


@pytest.mark.parametrize("x_size", [3, 4])
def test_short_x_axis_is_not_interpreted_as_rgb(x_size, tmp_path, make_napari_viewer, qtbot):
    import numpy as np
    import zarr

    path = str(tmp_path / "small.zarr")
    root = zarr.open_array(
        path, mode="w", shape=(40, 60, x_size), chunks=(1, 10, x_size), dtype="u2"
    )
    root[:] = np.arange(40 * 60 * x_size, dtype=np.uint16).reshape(40, 60, x_size)
    viewer = make_napari_viewer()
    widget = OpenVolumeWidget(viewer)
    qtbot.addWidget(widget)
    widget.path_input.setText(path)
    qtbot.mouseClick(widget.open_button, Qt.LeftButton)
    qtbot.waitUntil(lambda: widget.open_button.isEnabled(), timeout=20000)
    assert len(viewer.layers) == 1
    assert viewer.layers[0].ndim == 3
    assert not viewer.layers[0].rgb
    qtbot.waitUntil(lambda: viewer.layers[0].loaded, timeout=20000)
