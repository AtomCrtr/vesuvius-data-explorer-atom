"""QC panel integration: run/load reports, anomaly layer, navigation, view measurement."""

import json
import threading

import numpy as np
import pytest

pytest.importorskip("napari")
pytest.importorskip("qtpy")
import zarr  # noqa: E402
from qtpy.QtCore import Qt  # noqa: E402

from vesuvius_data_explorer.napari import qc_widget as qc_module  # noqa: E402
from vesuvius_data_explorer.napari.qc_widget import (  # noqa: E402
    ANOMALY_LAYER,
    QCWidget,
    camera,
    canvas_size,
    view_box,
)
from vesuvius_data_explorer.napari.reader import read_volume  # noqa: E402
from vesuvius_data_explorer.qc.locate import (  # noqa: E402
    location_to_world,
    view_metrics,
    visible_region,
)


@pytest.fixture
def saturated_pyramid(tmp_path):
    """Three levels, non-uniform scales, a saturated column block visible at every level."""
    path = tmp_path / "scan.zarr"
    root = zarr.open_group(str(path), mode="w", zarr_format=2)
    datasets = []
    for index, shape in enumerate([(64, 128, 128), (32, 64, 64), (16, 32, 32)]):
        data = np.random.default_rng(index).integers(60, 200, shape, dtype="uint8")
        data[:, : shape[1] // 2, : shape[2] // 2] = 255
        array = root.create_array(str(index), shape=shape, dtype="uint8",
                                  chunks=(8, shape[1] // 2, shape[2] // 2))
        array[:] = data
        datasets.append({"path": str(index), "coordinateTransformations": [
            {"type": "scale", "scale": [2.0 * 2**index, 0.5 * 2**index, 0.5 * 2**index]}]})
    root.attrs["multiscales"] = [{"axes": ["z", "y", "x"], "datasets": datasets}]
    return path


@pytest.fixture
def viewer_with_volume(saturated_pyramid, make_napari_viewer, qtbot):
    viewer = make_napari_viewer()
    [(arrays, options, _)] = read_volume(str(saturated_pyramid))
    layer = viewer.add_image(arrays, **options)
    widget = QCWidget(viewer)
    qtbot.addWidget(widget)
    return viewer, layer, widget


def _anomaly_layers(viewer):
    return [layer for layer in viewer.layers if layer.name == ANOMALY_LAYER]


def _expected_boxes(report, layer):
    levels = layer.metadata["volume_summary"]["levels"]
    return [location_to_world(location, levels, layer.scale)
            for result in report["results"]
            if result["status"] in ("warn", "fail") and not result["check_id"].startswith(
                ("volume.levels", "volume.chunks"))
            for location in result["locations"]]


def _run(widget, qtbot):
    widget._report = None
    qtbot.mouseClick(widget.run_button, Qt.LeftButton)
    qtbot.waitUntil(lambda: widget._report is not None and widget._worker is None, timeout=20000)


def test_run_qc_off_gui_thread_draws_one_anomaly_layer(viewer_with_volume, qtbot, monkeypatch):
    viewer, layer, widget = viewer_with_volume
    threads = []
    real = qc_module.run_qc

    def tracked(*args):
        threads.append(threading.get_ident())
        return real(*args)

    monkeypatch.setattr(qc_module, "run_qc", tracked)
    widget.samples_spin.setValue(4)
    _run(widget, qtbot)
    assert threads and threads[0] != threading.get_ident()
    report = widget._report
    assert report["summary"]["fail"] >= 1
    assert widget.results_table.item(0, 1).text() == "fail"
    # Readable in napari's dark theme: dark text on light status colours.
    assert widget.results_table.item(0, 0).foreground().color().name() == "#18232b"
    boxes = _expected_boxes(report, layer)
    [anomalies] = _anomaly_layers(viewer)
    assert len(anomalies.data) == len(boxes) > 0
    for vertices, box in zip(anomalies.data, boxes):
        np.testing.assert_allclose(vertices, box.rectangle())
    assert "anomalie" in widget.status_label.text()
    _run(widget, qtbot)
    assert len(_anomaly_layers(viewer)) == 1


def test_load_report_valid_mismatched_invalid_and_surface(viewer_with_volume, tmp_path, qtbot):
    viewer, layer, widget = viewer_with_volume
    report = qc_module.run_qc(layer.metadata["source"], None, 4, 0, 16_777_216, "")
    good = tmp_path / "good.json"
    good.write_text(json.dumps(report))
    widget.load_report_file(str(good))
    [anomalies] = _anomaly_layers(viewer)
    assert len(anomalies.data) == len(_expected_boxes(report, layer))
    assert "Attention" not in widget.status_label.text()

    report["target"]["uri"] = "/ailleurs/scan.zarr"
    moved = tmp_path / "moved.json"
    moved.write_text(json.dumps(report))
    widget.load_report_file(str(moved))
    assert "Attention" in widget.status_label.text()
    assert "ni dessinées" in widget.status_label.text()
    # A report for another volume must not mark (or navigate to) voxels of this one.
    assert _anomaly_layers(viewer) == []
    assert widget.results_table.rowCount() == len(report["results"])
    row = next(i for i, r in enumerate(widget._rows) if r["locations"])
    widget.results_table.selectRow(row)
    assert widget.locations_list.count() == 0

    bad = tmp_path / "bad.json"
    bad.write_text('{"schema_version": "1.0"}')
    widget.load_report_file(str(bad))
    assert "non conforme" in widget.status_label.text()
    report["target"]["kind"] = "surface"
    surface = tmp_path / "surface.json"
    surface.write_text(json.dumps(report))
    widget.load_report_file(str(surface))
    assert "surface" in widget.status_label.text()
    assert _anomaly_layers(viewer) == []


def test_selecting_a_location_navigates_to_it(viewer_with_volume, qtbot):
    viewer, layer, widget = viewer_with_volume
    widget.samples_spin.setValue(4)
    _run(widget, qtbot)
    row = next(i for i, r in enumerate(widget._rows) if r["check_id"] == "volume.saturation")
    widget.results_table.selectRow(row)
    assert widget.locations_list.count() == len(widget._rows[row]["locations"])
    location = widget._rows[row]["locations"][-1]
    widget.locations_list.setCurrentRow(widget.locations_list.count() - 1)
    box = location_to_world(location, layer.metadata["volume_summary"]["levels"], layer.scale)
    assert viewer.dims.point[0] == pytest.approx(box.plane, abs=layer.scale[0] / 2)
    cy, cx = camera(viewer).center[-2:]
    assert box.low[0] <= cy <= box.high[0] and box.low[1] <= cx <= box.high[1]
    height, width = canvas_size(viewer)
    expected = 0.5 * min(height / (box.high[0] - box.low[0]), width / (box.high[1] - box.low[1]))
    assert camera(viewer).zoom == pytest.approx(expected)


def test_measure_view_is_bounded_off_gui_thread_and_exact(viewer_with_volume, qtbot, monkeypatch):
    viewer, layer, widget = viewer_with_volume
    calls = []
    real = qc_module.read_slice

    def tracked(array, *args, **kwargs):
        data = real(array, *args, **kwargs)
        calls.append((threading.get_ident(), data))
        return data

    monkeypatch.setattr(qc_module, "read_slice", tracked)
    viewer.dims.set_point(0, 40.0)
    camera(viewer).center = (16.0, 16.0)
    camera(viewer).zoom = 8.0
    qtbot.mouseClick(widget.measure_button, Qt.LeftButton)
    qtbot.waitUntil(lambda: widget.measure_label.text().startswith("Niveau"), timeout=20000)
    [(thread, data)] = calls
    assert thread != threading.get_ident()
    assert data.size <= 512 * 512
    # The read matches the real canvas: visible world extent = canvas pixels / zoom.
    plane_axis, plane, low, high = view_box(viewer)
    height, width = canvas_size(viewer)
    assert high[0] - low[0] == pytest.approx(height / 8.0)
    assert high[1] - low[1] == pytest.approx(width / 8.0)
    region = visible_region(layer.metadata["volume_summary"]["levels"], layer.scale,
                            plane_axis, plane, low, high)
    assert region["level"] == "0"
    assert data.shape == (min(region["width_a"], 128 - region["start_a"]),
                          min(region["width_b"], 128 - region["start_b"]))
    metrics = view_metrics(data)
    assert f"p99 {metrics['p99']:.4g}" in widget.measure_label.text()
    assert f"fond {metrics['background_pct']:.4g} %" in widget.measure_label.text()


def test_measure_refuses_3d_view(viewer_with_volume, qtbot):
    viewer, _, widget = viewer_with_volume
    viewer.dims.ndisplay = 3
    qtbot.mouseClick(widget.measure_button, Qt.LeftButton)
    assert "2D" in widget.measure_label.text()


def test_without_plugin_volume_buttons_are_disabled(make_napari_viewer, qtbot):
    viewer = make_napari_viewer()
    viewer.add_image(np.zeros((4, 4, 4)))
    widget = QCWidget(viewer)
    qtbot.addWidget(widget)
    assert not widget.run_button.isEnabled()
    assert "Ouvrir un volume" in widget.status_label.text()


def test_manifest_instantiates_qc_widget(make_napari_viewer):
    from napari.settings import get_settings

    viewer = make_napari_viewer()
    _, widget = viewer.window.add_plugin_dock_widget(
        "vesuvius-data-explorer", "Vesuvius — Contrôle qualité"
    )
    assert isinstance(widget, QCWidget)
    assert get_settings().experimental.async_ is False
