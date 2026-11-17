"""Overlay VC3D tifxyz segments on an opened volume, with their quality indicators.

Reading, indicators and decimation live in ``core/`` and ``qc/``; this module wires Qt and
napari. Every read (catalogue, grids) runs in a worker thread.
"""

from __future__ import annotations

import numpy as np
from napari.layers import Image
from napari.qt.threading import thread_worker
from napari.viewer import Viewer
from qtpy.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from vesuvius_data_explorer.core.catalog import load_catalog
from vesuvius_data_explorer.core.tifxyz import in_volume, load_tifxyz
from vesuvius_data_explorer.qc import run_surface

from .qc_widget import camera, canvas_size

MAX_DISPLAYED_POINTS = 200_000
SURFACE_PREFIX = "Surface — "
HOLES_PREFIX = "Trous — "
NO_VOLUME = "Aucun volume ouvert par le plugin : utiliser « Vesuvius — Ouvrir un volume »."
CHECK_ORDER = ("surface.holes", "surface.bounds", "surface.stretch", "surface.normal_flips",
               "surface.valid")


def _volume_layers(viewer):
    return [layer for layer in viewer.layers if isinstance(layer, Image)
            and "source" in layer.metadata and "volume_summary" in layer.metadata]


def prepare_overlay(source, max_bytes, volume_shape, overlap_ratio):
    """Worker body (no Qt): read the segment, compute its report and the points to display."""
    surface = load_tifxyz(source, max_bytes=max_bytes)
    report = run_surface(source, surface=surface, max_bytes=max_bytes,
                         volume_shape=volume_shape, overlap_ratio=overlap_ratio)
    flat = surface.points.reshape(-1, 3)
    valid = np.isfinite(flat).all(axis=1)
    inside = in_volume(flat, volume_shape) if volume_shape is not None else valid
    shown = flat[inside]
    thinning = 1
    if len(shown) > MAX_DISPLAYED_POINTS:
        thinning = int(np.ceil(len(shown) / MAX_DISPLAYED_POINTS))
        shown = shown[::thinning]
    holes = next(r for r in report["results"] if r["check_id"] == "surface.holes")
    centers = np.array([loc["center"] for loc in holes["locations"] if "center" in loc],
                       dtype=float).reshape(-1, 3)
    return {
        "source": surface.source,
        "points": shown,
        "holes": centers,
        "step": surface.step_voxels,
        "grid_shape": surface.grid_shape,
        "stride": surface.stride,
        "bytes_read": surface.bytes_read,
        "valid": int(valid.sum()),
        "hidden_outside": int(valid.sum() - inside.sum()),
        "thinning": thinning,
        "report": report,
    }


def format_bytes(count: int) -> str:
    """French byte count: '29 Kio', '1,5 Mio'."""
    if count < 2**20:
        return f"{count / 2**10:.0f} Kio"
    return f"{count / 2**20:.1f} Mio".replace(".", ",")


class SliceTrace:
    """Show the points of a surface that lie in a thin slab around the current 2D slice.

    napari's own out-of-slice display is deprecated (0.9) in favour of thick slicing, which is
    viewer-wide and would also average the image (its default projection is "mean"). The trace
    is therefore computed here: points within ``half`` voxels of the slice, moved onto it. In
    3D every point is shown.
    """

    def __init__(self, viewer, layer, points, half):
        self.viewer, self.layer, self.points, self.half = viewer, layer, points, half
        viewer.dims.events.point.connect(self.update)
        viewer.dims.events.ndisplay.connect(self.update)
        viewer.dims.events.order.connect(self.update)
        self.update()

    def disconnect(self):
        for event in (self.viewer.dims.events.point, self.viewer.dims.events.ndisplay,
                      self.viewer.dims.events.order):
            event.disconnect(self.update)

    def visible(self) -> np.ndarray:
        dims = self.viewer.dims
        if dims.ndisplay == 3 or not len(self.points):
            return self.points
        axis = dims.not_displayed[0]
        plane = dims.point[axis] / self.layer.scale[axis]
        inside = np.abs(self.points[:, axis] - plane) <= self.half
        slab = self.points[inside].copy()
        slab[:, axis] = plane
        return slab

    def update(self, event=None):
        if self.layer not in self.viewer.layers:
            self.disconnect()
            return
        self.layer.data = self.visible()


def describe(overlay) -> str:
    """French summary of a prepared overlay and its indicators."""
    rows, cols = overlay["grid_shape"]
    lines = [f"Grille {rows} × {cols}"
             + (f", lue une ligne et une colonne sur {overlay['stride']}"
                if overlay["stride"] > 1 else "")
             + f" ; {format_bytes(overlay['bytes_read'])} lus.",
             f"{len(overlay['points'])} point(s) affiché(s) sur {overlay['valid']} valide(s)"
             + (f" ; {overlay['hidden_outside']} hors du volume, masqué(s)"
                if overlay["hidden_outside"] else "")
             + (f" ; un point sur {overlay['thinning']} au-delà de {MAX_DISPLAYED_POINTS}"
                if overlay["thinning"] > 1 else "") + "."]
    results = {r["check_id"]: r for r in overlay["report"]["results"]}
    for check_id in CHECK_ORDER:
        result = results.get(check_id)
        if result is not None:
            value = "" if result["value"] is None else f" ({result['value']:.3g})"
            lines.append(f"{check_id} : {result['status']}{value} — {result['message']}")
    return "\n".join(lines)


class SurfaceWidget(QWidget):
    def __init__(self, napari_viewer: Viewer):
        super().__init__()
        self._viewer = napari_viewer
        self._worker = None
        self._catalog = None
        self._overlay = None
        self._target = None
        self._traces = {}
        self._current_name = None

        self.layer_combo = QComboBox()
        self.catalog_button = QPushButton("Lister les segments du catalogue")
        self.segment_combo = QComboBox()
        self.segment_combo.setEnabled(False)
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Dossier ou URI s3:// d'un segment tifxyz")
        self.budget_spin = QSpinBox()
        self.budget_spin.setRange(1, 4096)
        self.budget_spin.setValue(64)
        self.budget_spin.setSuffix(" Mio par grille")
        self.overlay_button = QPushButton("Superposer")
        self.goto_button = QPushButton("Aller à la surface")
        self.goto_button.setEnabled(False)
        self.info_label = QLabel()
        self.info_label.setWordWrap(True)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Volume", self.layer_combo)
        form.addRow(self.catalog_button)
        form.addRow("Segment", self.segment_combo)
        form.addRow("Chemin", self.path_input)
        form.addRow("Budget", self.budget_spin)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        for control in (self.overlay_button, self.goto_button, self.info_label,
                        self.status_label):
            layout.addWidget(control)

        self.layer_combo.currentIndexChanged.connect(self._layer_changed)
        self.catalog_button.clicked.connect(self._load_catalog)
        self.segment_combo.currentIndexChanged.connect(self._segment_changed)
        self.overlay_button.clicked.connect(self._overlay_clicked)
        self.goto_button.clicked.connect(self.go_to_surface)
        self._viewer.layers.events.inserted.connect(self._refresh_layers)
        self._viewer.layers.events.removed.connect(self._refresh_layers)
        self._refresh_layers()

    # --- target volume ------------------------------------------------------------------

    def _refresh_layers(self, event=None):
        for name, trace in list(self._traces.items()):
            if trace.layer not in self._viewer.layers:
                trace.disconnect()
                del self._traces[name]
        current = self.layer_combo.currentText()
        names = [layer.name for layer in _volume_layers(self._viewer)]
        self.layer_combo.blockSignals(True)
        self.layer_combo.clear()
        self.layer_combo.addItems(names)
        if current in names:
            self.layer_combo.setCurrentText(current)
        self.layer_combo.blockSignals(False)
        if self.layer_combo.currentText() != self._current_name:
            self._layer_changed()
        else:  # e.g. our own Points layers: keep the chosen segment and path.
            self._update_buttons()

    def _layer(self):
        name = self.layer_combo.currentText()
        return next((lyr for lyr in _volume_layers(self._viewer) if lyr.name == name), None)

    def _volume_id(self, layer):
        catalog = layer.metadata.get("catalog") if layer is not None else None
        return catalog.get("volume_id") if isinstance(catalog, dict) else None

    def _layer_changed(self, *args):
        self._current_name = self.layer_combo.currentText()
        self._update_buttons()
        self._fill_segments()

    def _update_buttons(self):
        layer = self._layer()
        busy = self._worker is not None
        self.overlay_button.setEnabled(layer is not None and not busy)
        self.catalog_button.setEnabled(self._volume_id(layer) is not None and not busy)
        if layer is None:
            self.status_label.setText(NO_VOLUME)
        elif self.status_label.text() == NO_VOLUME:
            self.status_label.setText("")

    # --- catalogue -------------------------------------------------------------------------

    def _load_catalog(self):
        self._start(load_catalog, (), self._catalog_loaded, "Chargement du catalogue…")

    def _catalog_loaded(self, catalog):
        self._catalog = catalog
        self._fill_segments()
        count = self.segment_combo.count()
        self.status_label.setText(
            f"{count} segment(s) publié(s) dans le repère de ce volume." if count else
            "Aucun segment publié dans le repère de ce volume.")

    def _fill_segments(self):
        self.segment_combo.blockSignals(True)
        self.segment_combo.clear()
        volume_id = self._volume_id(self._layer())
        if self._catalog is not None and volume_id is not None:
            for segment in self._catalog.segments_for(volume_id):
                self.segment_combo.addItem(segment.label, segment)
        self.segment_combo.blockSignals(False)
        self.segment_combo.setEnabled(self.segment_combo.count() > 0)
        self._segment_changed()

    def _segment_changed(self, *args):
        segment = self.segment_combo.currentData()
        if segment is not None:
            self.path_input.setText(segment.uri)
            self.segment_combo.setToolTip(segment.label)

    # --- overlay -----------------------------------------------------------------------------

    def _overlay_clicked(self):
        layer = self._layer()
        if layer is None:
            return
        source = self.path_input.text().strip()
        segment = self.segment_combo.currentData()
        overlap = (segment.overlap_ratio if segment is not None
                   and segment.uri == source.rstrip("/") else None)
        levels = layer.metadata["volume_summary"]["levels"]
        volume_shape = tuple(levels[0]["shape"]) if levels else None
        self._target = layer
        self._start(prepare_overlay,
                    (source, self.budget_spin.value() * 2**20, volume_shape, overlap),
                    self._show_overlay, "Lecture du segment…")

    def _show_overlay(self, overlay):
        layer = self._target
        name = overlay["source"].rsplit("/", 1)[-1]
        for old in [lyr for lyr in self._viewer.layers
                    if lyr.name in (SURFACE_PREFIX + name, HOLES_PREFIX + name)]:
            self._viewer.layers.remove(old)
        # Same frame as the image: (z, y, x) level-0 voxels with the image layer's scale.
        # Slab of half a grid step on each side, so each grid point shows on one slice band;
        # markers half a step wide leave the image visible between them.
        step = overlay["step"]
        layers = [(SURFACE_PREFIX + name, overlay["points"], step / 2, step / 2, "cyan")]
        if len(overlay["holes"]):
            layers.append((HOLES_PREFIX + name, overlay["holes"], 2 * step, step, "red"))
        for layer_name, points, size, half, color in layers:
            points_layer = self._viewer.add_points(
                np.empty((0, 3)), name=layer_name, size=size, face_color=color,
                border_width=0, opacity=0.8, scale=tuple(layer.scale))
            self._traces[layer_name] = SliceTrace(self._viewer, points_layer, points, half)
        self._viewer.layers.selection.active = layer
        self._overlay = overlay
        self.goto_button.setEnabled(len(overlay["points"]) > 0)
        self.info_label.setText(describe(overlay))
        self.status_label.setText("Segment superposé.")

    def go_to_surface(self):
        """2D view on the slice through the centre of the displayed points, framing them."""
        if self._overlay is None or not len(self._overlay["points"]) or self._target is None:
            return
        scale = np.asarray(self._target.scale, dtype=float)
        points = self._overlay["points"] * scale
        low, high = points.min(axis=0), points.max(axis=0)
        center = (low + high) / 2
        viewer = self._viewer
        if viewer.dims.ndisplay != 2:
            viewer.dims.ndisplay = 2
        viewer.dims.order = (0, 1, 2)
        viewer.dims.set_point(0, float(center[0]))
        cam = camera(viewer)
        cam.center = (float(center[1]), float(center[2]))
        extent = np.maximum(high[1:] - low[1:], scale[1:])
        size = canvas_size(viewer)
        if size:
            cam.zoom = 0.8 * min(size[0] / extent[0], size[1] / extent[1])

    # --- workers -------------------------------------------------------------------------------

    def _start(self, function, args, on_result, message):
        for button in (self.overlay_button, self.catalog_button):
            button.setEnabled(False)
        self.status_label.setText(message)
        self._worker = thread_worker(function, ignore_errors=True)(*args)
        self._worker.returned.connect(on_result)
        self._worker.errored.connect(self._error)
        self._worker.finished.connect(self._finished)
        self._worker.start()

    def _finished(self):
        self._worker = None
        self._update_buttons()

    def _error(self, error):
        message = str(error)
        safe = (isinstance(error, (ValueError, FileNotFoundError, ConnectionError))
                and message[:1].isupper() and "Traceback" not in message)
        self.status_label.setText(message if safe else
                                  "Lecture du segment impossible. Vérifier le chemin, le format "
                                  "tifxyz et l'accès au stockage ou au réseau.")
