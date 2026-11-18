"""Surfaces panel: catalogue segments, overlay in the image frame, holes, navigation, errors."""

import json
import threading

import numpy as np
import pytest

pytest.importorskip("napari")
pytest.importorskip("qtpy")
import tifffile  # noqa: E402
import zarr  # noqa: E402
from qtpy.QtCore import Qt  # noqa: E402

from vesuvius_data_explorer.core.catalog import Catalog, CatalogSegment  # noqa: E402
from vesuvius_data_explorer.napari import surface_widget as surface_module  # noqa: E402
from vesuvius_data_explorer.napari.qc_widget import camera  # noqa: E402
from vesuvius_data_explorer.napari.reader import read_volume  # noqa: E402
from vesuvius_data_explorer.napari.surface_widget import SurfaceWidget  # noqa: E402


def write_segment(folder, hole=False):
    """12 x 20 grid on the plane z = 8 of the (16, 32, 48) test pyramid; the last 4 columns
    (x >= 48) lie outside the volume, the first row is VC3D's (-1, -1, -1) outline."""
    row, col = np.mgrid[:12, :20].astype(np.float32)
    x, y, z = 3 * col, 2 * row + 4, np.full_like(row, 8)
    for grid in (x, y, z):
        grid[0, :] = -1
        if hole:
            grid[5:7, 5:7] = -1
    folder.mkdir()
    for name, grid in zip("xyz", (x, y, z)):
        tifffile.imwrite(folder / f"{name}.tif", grid)
    # scale 0.5: one grid point every 2 voxels, so the slice trace keeps points within 1 voxel.
    (folder / "meta.json").write_text(json.dumps({"scale": [0.5, 0.5]}))
    return folder


@pytest.fixture
def viewer_with_volume(napari_pyramid, make_napari_viewer, qtbot):
    viewer = make_napari_viewer()
    [(arrays, options, _)] = read_volume(str(napari_pyramid))
    options["metadata"]["catalog"] = {"volume_id": "V1"}
    layer = viewer.add_image(arrays, **options)
    widget = SurfaceWidget(viewer)
    qtbot.addWidget(widget)
    return viewer, layer, widget


def _overlay(widget, qtbot, path):
    widget.path_input.setText(str(path))
    qtbot.mouseClick(widget.overlay_button, Qt.LeftButton)
    qtbot.waitUntil(lambda: widget.overlay_button.isEnabled(), timeout=20000)


def test_overlay_is_read_off_the_gui_thread_in_the_image_frame(
    viewer_with_volume, tmp_path, qtbot, monkeypatch
):
    viewer, layer, widget = viewer_with_volume
    threads = []
    real = surface_module.prepare_overlay

    def tracked(*args):
        threads.append(threading.get_ident())
        return real(*args)

    monkeypatch.setattr(surface_module, "prepare_overlay", tracked)
    viewer.dims.set_point(0, 8 * 0.5)  # world z of level-0 slice 8
    _overlay(widget, qtbot, write_segment(tmp_path / "seg"))
    assert threads and threads[0] != threading.get_ident()
    points = viewer.layers["Surface — seg"]
    # 11 valid rows x 16 columns inside the volume; same scale as the image (0.5, 1, 2).
    assert len(points.data) == 11 * 16
    assert tuple(points.scale) == tuple(layer.scale) == (0.5, 1, 2)
    assert points.data[:, 0].tolist() == [8] * len(points.data)  # z in level-0 voxels
    assert "Trous — seg" not in [lyr.name for lyr in viewer.layers]
    info = widget.info_label.text()
    assert "Grille 12 × 20" in info and "44 hors du volume, masqué(s)" in info
    assert "Kio lus" in info
    assert "surface.holes : pass" in info
    assert "surface.bounds : pass" in info  # no catalogue coverage: informational
    assert viewer.layers.selection.active is layer
    assert widget.goto_button.isEnabled()


def test_interior_hole_is_marked_and_navigation_frames_the_surface(
    viewer_with_volume, tmp_path, qtbot
):
    viewer, layer, widget = viewer_with_volume
    viewer.dims.set_point(0, 8 * 0.5)
    _overlay(widget, qtbot, write_segment(tmp_path / "seg", hole=True))
    holes = viewer.layers["Trous — seg"]
    assert len(holes.data) == 1
    assert holes.data[0].tolist() == pytest.approx([8, 15, 16.5])
    assert "surface.holes : warn" in widget.info_label.text()  # 4 / 220 = 1.8 %, between 1 and 5
    viewer.dims.ndisplay = 3
    widget.go_to_surface()
    assert viewer.dims.ndisplay == 2
    assert viewer.dims.point[0] == pytest.approx(8 * 0.5)
    # Displayed points: y from 6 to 26, x from 0 to 45 (world x doubles).
    assert tuple(camera(viewer).center[-2:]) == pytest.approx((16, 45))


def test_displayed_points_are_capped(viewer_with_volume, tmp_path, qtbot, monkeypatch):
    viewer, _, widget = viewer_with_volume
    monkeypatch.setattr(surface_module, "MAX_DISPLAYED_POINTS", 50)
    _overlay(widget, qtbot, write_segment(tmp_path / "seg"))
    assert len(viewer.layers["Surface — seg"].data) == 44  # 176 points, one out of 4
    assert "un point sur 4 au-delà de 50" in widget.info_label.text()


def test_catalogue_segments_fill_the_path_and_bring_the_coverage(
    viewer_with_volume, tmp_path, qtbot, monkeypatch
):
    viewer, _, widget = viewer_with_volume
    folder = write_segment(tmp_path / "seg")
    segment = CatalogSegment("P", "20251029010146", "20251029010146-auto", "V1", str(folder),
                             0.9, None, False)
    other = CatalogSegment("P", "2", "2", "V2", "s3://b/other", None, None, False)
    monkeypatch.setattr(surface_module, "load_catalog",
                        lambda: Catalog((), "test", segments=(segment, other)))
    assert widget.catalog_button.isEnabled()
    qtbot.mouseClick(widget.catalog_button, Qt.LeftButton)
    qtbot.waitUntil(lambda: widget.catalog_button.isEnabled(), timeout=20000)
    assert widget.segment_combo.count() == 1
    assert widget.segment_combo.currentText() == "20251029010146 (auto) — couverture 90 %"
    assert widget.path_input.text() == str(folder)
    assert "1 segment(s)" in widget.status_label.text()
    _overlay(widget, qtbot, folder)
    # 176 of 220 valid points inside (80 %) vs 90 % announced: inconsistent catalogue.
    assert "surface.bounds : warn" in widget.info_label.text()
    assert widget.path_input.text() == str(folder)


def test_catalogue_button_needs_a_catalogued_volume(napari_pyramid, make_napari_viewer, qtbot):
    viewer = make_napari_viewer()
    widget = SurfaceWidget(viewer)
    qtbot.addWidget(widget)
    assert not widget.overlay_button.isEnabled()
    assert "Aucun volume" in widget.status_label.text()
    [(arrays, options, _)] = read_volume(str(napari_pyramid))
    viewer.add_image(arrays, **options)  # typed path: no catalogue metadata
    assert widget.overlay_button.isEnabled()
    assert not widget.catalog_button.isEnabled()


@pytest.mark.parametrize("source, expected", [
    ("missing", "Grille introuvable"),
    ("https://example.org/seg", "pas prise en charge"),
])
def test_errors_are_french(viewer_with_volume, tmp_path, qtbot, source, expected):
    viewer, _, widget = viewer_with_volume
    if source == "missing":
        source = tmp_path / "absent"
    _overlay(widget, qtbot, source)
    assert expected in widget.status_label.text()
    assert "Traceback" not in widget.status_label.text()
    assert len(viewer.layers) == 1


def test_unexpected_errors_are_not_shown_verbatim(viewer_with_volume, qtbot, monkeypatch):
    viewer, _, widget = viewer_with_volume

    def broken(*args):
        raise RuntimeError("botocore internals")

    monkeypatch.setattr(surface_module, "prepare_overlay", broken)
    _overlay(widget, qtbot, "s3://bucket/seg")
    assert "Lecture du segment impossible" in widget.status_label.text()


def test_manifest_instantiates_surface_widget(make_napari_viewer):
    viewer = make_napari_viewer()
    _, widget = viewer.window.add_plugin_dock_widget("vesuvius-data-explorer", "Vesuvius — Surfaces")
    assert isinstance(widget, SurfaceWidget)


def test_trace_follows_the_slice_and_shows_everything_in_3d(viewer_with_volume, tmp_path, qtbot):
    viewer, _, widget = viewer_with_volume
    viewer.dims.set_point(0, 8 * 0.5)
    _overlay(widget, qtbot, write_segment(tmp_path / "seg"))
    points = viewer.layers["Surface — seg"]
    viewer.dims.set_point(0, 9 * 0.5)  # 1 voxel away: still within half a grid step
    assert len(points.data) == 176 and set(points.data[:, 0]) == {9}
    viewer.dims.set_point(0, 12 * 0.5)  # 4 voxels away: nothing on this slice
    assert len(points.data) == 0
    viewer.dims.ndisplay = 3
    assert len(points.data) == 176 and set(points.data[:, 0]) == {8}
    viewer.dims.ndisplay = 2
    viewer.dims.order = (2, 0, 1)  # slicing along x now: points with x within 1 voxel
    viewer.dims.set_point(2, 9 * 2)
    assert len(points.data) == 11 and set(points.data[:, 2]) == {9}


def test_removing_the_layer_stops_the_trace(viewer_with_volume, tmp_path, qtbot):
    viewer, _, widget = viewer_with_volume
    _overlay(widget, qtbot, write_segment(tmp_path / "seg"))
    viewer.layers.remove("Surface — seg")
    assert widget._traces == {}
    viewer.dims.set_point(0, 2)  # no error from a dangling trace


def test_overlay_keeps_the_chosen_segment(viewer_with_volume, tmp_path, qtbot, monkeypatch):
    viewer, _, widget = viewer_with_volume
    first, second = write_segment(tmp_path / "a"), write_segment(tmp_path / "b")
    segments = tuple(CatalogSegment("P", name, name, "V1", str(path), None, None, False)
                     for name, path in (("1", first), ("2", second)))
    monkeypatch.setattr(surface_module, "load_catalog",
                        lambda: Catalog((), "test", segments=segments))
    qtbot.mouseClick(widget.catalog_button, Qt.LeftButton)
    qtbot.waitUntil(lambda: widget.catalog_button.isEnabled(), timeout=20000)
    widget.segment_combo.setCurrentIndex(1)
    qtbot.mouseClick(widget.overlay_button, Qt.LeftButton)
    qtbot.waitUntil(lambda: widget.overlay_button.isEnabled(), timeout=20000)
    assert "Surface — b" in [lyr.name for lyr in viewer.layers]
    assert widget.segment_combo.currentIndex() == 1 and widget.path_input.text() == str(second)


def test_alignment_is_measured_off_the_gui_thread_and_plotted(
    make_napari_viewer, tmp_path, qtbot, monkeypatch
):
    """Synthetic sheets every 24 voxels; the segment lies on the sheet at z = 48."""
    from vesuvius_data_explorer.napari.reader import read_volume as read

    z = np.arange(96)[:, None, None]
    volume = (50 + 100 * np.exp(-(((z + 12) % 24 - 12) ** 2) / 8.0)
              + np.zeros((96, 64, 64))).astype(np.float32)
    path = tmp_path / "sheets.zarr"
    root = zarr.open_group(str(path), mode="w", zarr_format=2)
    root.create_array("0", shape=volume.shape, dtype="float32", chunks=(32, 32, 32))
    root["0"][:] = volume
    root.attrs["multiscales"] = [{"axes": ["z", "y", "x"], "datasets": [
        {"path": "0", "coordinateTransformations": [{"type": "scale", "scale": [1, 1, 1]}]}]}]
    viewer = make_napari_viewer()
    [(arrays, options, _)] = read(str(path))
    options["metadata"]["pixel_size_um"] = 8.0
    layer = viewer.add_image(arrays, **options)
    widget = SurfaceWidget(viewer)
    qtbot.addWidget(widget)
    folder = tmp_path / "seg"
    folder.mkdir()
    row, col = np.mgrid[:30, :30].astype(np.float32)
    for name, grid in zip("xyz", (2 * col + 2, 2 * row + 2, np.full_like(row, 43))):
        tifffile.imwrite(folder / f"{name}.tif", grid)  # 5 voxels above the sheet at z = 48
    (folder / "meta.json").write_text(json.dumps({"scale": [0.5, 0.5]}))
    assert not widget.align_button.isEnabled()
    _overlay(widget, qtbot, folder)
    assert widget.align_button.isEnabled()
    threads = []
    real = surface_module.measure_alignment

    def tracked(*args):
        threads.append(threading.get_ident())
        return real(*args)

    monkeypatch.setattr(surface_module, "measure_alignment", tracked)
    qtbot.mouseClick(widget.align_button, Qt.LeftButton)
    qtbot.waitUntil(lambda: widget.align_button.isEnabled(), timeout=20000)
    assert threads and threads[0] != threading.get_ident()
    # Grid normal points to -z: the sheet at z = 48 is 5 voxels "behind" -> offset -5.
    assert "Feuille la plus proche à -5 voxel(s) (-40 µm)" in widget.align_label.text()
    assert "exploratoire" in widget.align_label.text()
    plot = widget.profile_plot
    assert not plot.isHidden() and plot.peak == -5 and len(plot.values) == len(plot.offsets)
    assert not plot.grab().isNull()
    patches = viewer.layers["Alignement — patchs seg"]
    assert tuple(patches.scale) == tuple(layer.scale)
    viewer.dims.ndisplay = 3
    assert len(patches.data) == 25  # 30 x 30 grid: every usable 6 x 6 patch (36 asked)
    assert widget.patches_spin.value() == 36


@pytest.mark.parametrize("error, expected", [
    (ValueError("Aucun patch de 6 × 6 points valides dans le volume : profil impossible."),
     "Aucun patch"),
    (RuntimeError("dask internals"), "Lecture du segment impossible"),
])
def test_alignment_errors_are_french(viewer_with_volume, tmp_path, qtbot, monkeypatch,
                                     error, expected):
    viewer, _, widget = viewer_with_volume
    _overlay(widget, qtbot, write_segment(tmp_path / "seg"))

    def failing(*args):
        raise error

    monkeypatch.setattr(surface_module, "measure_alignment", failing)
    qtbot.mouseClick(widget.align_button, Qt.LeftButton)
    qtbot.waitUntil(lambda: widget.align_button.isEnabled(), timeout=20000)
    assert expected in widget.status_label.text()
    assert "internals" not in widget.status_label.text()
    assert widget.profile_plot.isHidden()


def test_undetermined_alignment_is_described_as_such():
    from vesuvius_data_explorer.core.alignment import AlignmentProfile

    profile = AlignmentProfile(np.arange(-3.0, 4.0), np.full(7, 5.0), np.full((2, 7), 5.0),
                               np.zeros((2, 3)), 0, 6.0, 72, 100)
    text = surface_module.describe_alignment({
        "profile": profile, "pixel_size_um": 8.0,
        "metrics": {"peak_offset": None, "patches": 2, "level": 0}})
    assert text.startswith("Alignement indéterminé")
    plot = surface_module.ProfilePlot()
    plot.set_profile(profile.offsets, profile.mean, None)
    assert not plot.grab().isNull()
