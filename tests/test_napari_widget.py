"""Offscreen integration: real viewer, async open, errors and npe2 registration."""

import threading

import pytest

pytest.importorskip("napari")
pytest.importorskip("qtpy")
from qtpy.QtCore import Qt  # noqa: E402

from vesuvius_data_explorer.napari.widget import OpenVolumeWidget  # noqa: E402


def test_async_widget_adds_one_multiscale_layer(
    async_loading,
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
    async_loading,
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
    async_loading,
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
def test_short_x_axis_is_not_interpreted_as_rgb(
    async_loading, x_size, tmp_path, make_napari_viewer, qtbot
):
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


def test_open_without_async_reads_nothing_and_keeps_preference(
    napari_pyramid, make_napari_viewer, qtbot, monkeypatch
):
    from napari.settings import get_settings

    from vesuvius_data_explorer.napari import widget as widget_module

    calls = []
    monkeypatch.setattr(widget_module, "read_volume", lambda path: calls.append(path))
    viewer = make_napari_viewer()
    assert get_settings().experimental.async_ is False
    widget = OpenVolumeWidget(viewer)
    qtbot.addWidget(widget)
    assert not widget.async_button.isHidden()
    widget.path_input.setText(str(napari_pyramid))
    qtbot.mouseClick(widget.open_button, Qt.LeftButton)
    assert calls == []
    assert len(viewer.layers) == 0
    assert "asynchrone" in widget.status_label.text()
    assert get_settings().experimental.async_ is False


def test_async_button_enables_preference_only_on_click(make_napari_viewer, qtbot):
    from napari.settings import get_settings

    viewer = make_napari_viewer()
    widget = OpenVolumeWidget(viewer)
    qtbot.addWidget(widget)
    assert get_settings().experimental.async_ is False
    qtbot.mouseClick(widget.async_button, Qt.LeftButton)
    assert get_settings().experimental.async_ is True
    assert widget.async_button.isHidden()
    assert "activé" in widget.status_label.text()


def test_registered_reader_does_not_change_async_preference(
    napari_pyramid, make_napari_viewer, qtbot
):
    from napari.settings import get_settings

    viewer = make_napari_viewer()
    layers = viewer.open(str(napari_pyramid), plugin="vesuvius-data-explorer")
    qtbot.waitUntil(lambda: layers[0].loaded, timeout=20000)
    assert get_settings().experimental.async_ is False


def _catalog_for(path, **overrides):
    from vesuvius_data_explorer.core.catalog import Catalog, CatalogVolume

    fields = dict(
        sample_id="PHerc0332",
        sample_type="scroll",
        volume_id="20251211183505",
        name="scan.zarr",
        uri=str(path),
        codec="standard",
        pixel_size_um=2.399,
        energy_kev=78.0,
        shape=(16, 32, 48),
        dtype="uint16",
        license="CC BY-NC 4.0",
        superseded_by=None,
        superseded_reason=None,
    )
    fields.update(overrides)
    other = CatalogVolume(**{**fields, "sample_id": "PHercParis4", "volume_id": "1", "uri": "s3://b/c.zarr",
                             "codec": "vc-delta3d", "superseded_by": "2"})
    return Catalog((CatalogVolume(**fields), other), source="test")


def _load_catalog(widget, qtbot):
    qtbot.mouseClick(widget.catalog_button, Qt.LeftButton)
    qtbot.waitUntil(lambda: widget.catalog_button.isEnabled(), timeout=20000)


def test_catalogue_picker_fills_path_and_open_reports_voxel_size(
    async_loading, napari_pyramid, make_napari_viewer, qtbot, monkeypatch
):
    from vesuvius_data_explorer.napari import widget as widget_module

    threads = []

    def fake_load(refresh=False):
        threads.append((threading.get_ident(), refresh))
        return _catalog_for(napari_pyramid)

    monkeypatch.setattr(widget_module, "load_catalog", fake_load)
    viewer = make_napari_viewer()
    widget = OpenVolumeWidget(viewer)
    qtbot.addWidget(widget)
    assert not widget.sample_combo.isEnabled()
    _load_catalog(widget, qtbot)
    assert threads[0][0] != threading.get_ident()
    assert threads[0][1] is False
    assert [widget.sample_combo.itemText(i) for i in range(2)] == ["PHerc0332", "PHercParis4"]
    assert widget.volume_combo.currentText() == "20251211183505 — 2,399 µm — 78 keV"
    assert widget.path_input.text() == str(napari_pyramid)
    assert "Taille de voxel : 2,399 µm" in widget.volume_info.text()
    assert "CC BY-NC 4.0" in widget.volume_info.text()

    qtbot.mouseClick(widget.open_button, Qt.LeftButton)
    qtbot.waitUntil(lambda: widget.open_button.isEnabled(), timeout=20000)
    layer = viewer.layers[0]
    assert layer.metadata["pixel_size_um"] == 2.399
    assert layer.metadata["catalog"]["volume_id"] == "20251211183505"
    # World coordinates stay in level-0 voxels (catalogue and VC3D convention).
    assert tuple(layer.scale) == (0.5, 1, 2)
    status = widget.status_label.text()
    assert "taille de voxel 2,399 µm (catalogue officiel)" in status
    assert "Attention" not in status

    widget.sample_combo.setCurrentIndex(1)
    assert widget.path_input.text() == "s3://b/c.zarr"
    info = widget.volume_info.text()
    assert "[vcdelta3d]" in info and "Python 3.12" in info and "Remplacé par le volume 2" in info

    # A second click refreshes the catalogue instead of reading the cache.
    assert widget.catalog_button.text() == "Actualiser le catalogue"
    _load_catalog(widget, qtbot)
    assert threads[1][1] is True
    qtbot.waitUntil(lambda: layer.loaded, timeout=20000)


def test_open_warns_when_level0_shape_differs_from_catalogue(
    async_loading, napari_pyramid, make_napari_viewer, qtbot, monkeypatch
):
    from vesuvius_data_explorer.napari import widget as widget_module

    monkeypatch.setattr(
        widget_module, "load_catalog",
        lambda refresh=False: _catalog_for(napari_pyramid, shape=(17, 32, 48)),
    )
    viewer = make_napari_viewer()
    widget = OpenVolumeWidget(viewer)
    qtbot.addWidget(widget)
    _load_catalog(widget, qtbot)
    qtbot.mouseClick(widget.open_button, Qt.LeftButton)
    qtbot.waitUntil(lambda: widget.open_button.isEnabled(), timeout=20000)
    assert "Attention : forme du niveau 0 (16, 32, 48) différente" in widget.status_label.text()
    qtbot.waitUntil(lambda: viewer.layers[0].loaded, timeout=20000)


def test_path_typed_by_hand_opens_without_catalogue_metadata(
    async_loading, napari_pyramid, make_napari_viewer, qtbot
):
    viewer = make_napari_viewer()
    widget = OpenVolumeWidget(viewer)
    qtbot.addWidget(widget)
    widget.path_input.setText(str(napari_pyramid))
    qtbot.mouseClick(widget.open_button, Qt.LeftButton)
    qtbot.waitUntil(lambda: widget.open_button.isEnabled(), timeout=20000)
    assert "pixel_size_um" not in viewer.layers[0].metadata
    assert widget.status_label.text() == "Volume ouvert."
    qtbot.waitUntil(lambda: viewer.layers[0].loaded, timeout=20000)


@pytest.mark.parametrize(
    "error, expected",
    [
        (ConnectionError("Catalogue officiel inaccessible : vérifier le réseau."), "vérifier le réseau"),
        (RuntimeError("botocore internals"), "Catalogue officiel inaccessible ou illisible."),
    ],
)
def test_catalogue_errors_are_french_and_keep_manual_path(
    error, expected, make_napari_viewer, qtbot, monkeypatch
):
    from vesuvius_data_explorer.napari import widget as widget_module

    def failing(refresh=False):
        raise error

    monkeypatch.setattr(widget_module, "load_catalog", failing)
    viewer = make_napari_viewer()
    widget = OpenVolumeWidget(viewer)
    qtbot.addWidget(widget)
    widget.path_input.setText("s3://bucket/scan.zarr")
    _load_catalog(widget, qtbot)
    assert expected in widget.volume_info.text()
    assert "botocore" not in widget.volume_info.text()
    assert not widget.sample_combo.isEnabled()
    assert widget.path_input.text() == "s3://bucket/scan.zarr"


def test_stale_catalogue_is_announced(napari_pyramid, make_napari_viewer, qtbot, monkeypatch):
    from dataclasses import replace

    from vesuvius_data_explorer.napari import widget as widget_module

    monkeypatch.setattr(
        widget_module, "load_catalog",
        lambda refresh=False: replace(_catalog_for(napari_pyramid), stale=True),
    )
    viewer = make_napari_viewer()
    widget = OpenVolumeWidget(viewer)
    qtbot.addWidget(widget)
    _load_catalog(widget, qtbot)
    assert widget.volume_info.text().startswith("Réseau indisponible")
