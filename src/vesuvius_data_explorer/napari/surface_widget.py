"""Overlay VC3D tifxyz segments on an opened volume, with their quality indicators.

Reading, indicators and decimation live in ``core/`` and ``qc/``; this module wires Qt and
napari. Every read (catalogue, grids) runs in a worker thread.
"""

from __future__ import annotations

from pathlib import PureWindowsPath

import numpy as np
from napari.layers import Image
from napari.qt.threading import thread_worker
from napari.viewer import Viewer
from qtpy.QtCore import QPointF, Qt
from qtpy.QtGui import QColor, QPainter, QPen
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

from vesuvius_data_explorer.core.alignment import (
    DEFAULT_MAX_VOXELS,
    DEFAULT_PATCHES,
    alignment_metrics,
    normal_profiles,
)
from vesuvius_data_explorer.core.alignment_map import (
    DEFAULT_MAX_DRIFT_UM,
    alignment_map,
    reliable_tiles,
    review_zones,
)
from vesuvius_data_explorer.core.catalog import load_catalog
from vesuvius_data_explorer.core.geometry import sampling_details
from vesuvius_data_explorer.core.tifxyz import in_volume, load_tifxyz
from vesuvius_data_explorer.qc import run_surface
from vesuvius_data_explorer.qc.carte import drift_rgb
from vesuvius_data_explorer.qc.checks import grade_alignment
from vesuvius_data_explorer.qc.thresholds import load_thresholds

from .qc_widget import camera, canvas_size

MAX_DISPLAYED_POINTS = 200_000
SURFACE_PREFIX = "Surface — "
HOLES_PREFIX = "Trous — "
PATCHES_PREFIX = "Alignement — patchs "
DRIFT_PREFIX = "Carte de dérive — "
ZONE_LABELS = {"saut_de_feuille": "indice de saut de feuille", "derive": "forte dérive",
               "sans_feuille": "signal peu fiable"}
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
    shown = np.flatnonzero(inside)
    thinning = 1
    if len(shown) > MAX_DISPLAYED_POINTS:
        thinning = int(np.ceil(len(shown) / MAX_DISPLAYED_POINTS))
        shown = shown[::thinning]
    holes = next(r for r in report["results"] if r["check_id"] == "surface.holes")
    centers = np.array([loc["center"] for loc in holes["locations"] if "center" in loc],
                       dtype=float).reshape(-1, 3)
    return {
        "name": PureWindowsPath(surface.source).name,
        "points": flat[shown],
        "point_indices": shown,
        "holes": centers,
        "step": surface.step_voxels,
        "grid_shape": surface.grid_shape,
        "stride": surface.stride,
        "bytes_read": surface.bytes_read,
        "valid": int(valid.sum()),
        "hidden_outside": int(valid.sum() - inside.sum()),
        "thinning": thinning,
        "report": report,
        "surface": surface,  # kept for the alignment measure (T5.1)
    }


def measure_alignment(surface, arrays, shapes, pixel_size_um, max_voxels,
                      patches=DEFAULT_PATCHES, sampling=None):
    """Worker body (no Qt): alignment profile, its metrics and its grade (same rule as QC)."""
    profile = normal_profiles(surface, arrays, shapes, pixel_size_um=pixel_size_um,
                              max_voxels=max_voxels, patches=patches, sampling=sampling)
    metrics = alignment_metrics(profile)
    status, note = grade_alignment(metrics, pixel_size_um,
                                   load_thresholds()["surface.alignment"])
    return {"profile": profile, "metrics": metrics, "pixel_size_um": pixel_size_um,
            "status": status, "note": note,
            "sampling": sampling_details(shapes, profile.level, sampling)}


def measure_drift(overlay, arrays, shapes, pixel_size_um, sampling=None):
    """Worker body: compute T10 and colour each displayed point by its tile."""
    surface = overlay["surface"]
    amap = alignment_map(surface, arrays, shapes, pixel_size_um=pixel_size_um, sampling=sampling)
    rows, cols = np.unravel_index(overlay["point_indices"], surface.points.shape[:2])
    rgb = drift_rgb(amap, pixel_size_um)
    colors = rgb[rows // amap.tile, cols // amap.tile].astype(np.float32) / 255
    return colors, review_zones(amap, pixel_size_um=pixel_size_um), int(reliable_tiles(amap).sum())


def describe_alignment(result) -> str:
    """French summary: grade (T5.3), offset (µm when known), bootstrap interval, prominence."""
    metrics, pixel = result["metrics"], result["pixel_size_um"]
    offset = metrics["peak_offset"]
    if offset is None:
        text = ("Alignement indéterminé : aucune feuille identifiable (profil plat ou maximum au "
                f"bord de la fenêtre) ; {metrics['patches']} patch(s), niveau {metrics['level']}.")
        for warning in result["profile"].warnings:
            text += f" {warning}"
        return text
    iqr = metrics["bootstrap_iqr"]
    prominence = metrics["peak_prominence"]
    text = f"Feuille la plus proche à {offset:+.3g} voxel(s)"
    if pixel:
        text += f" ({offset * pixel:+.3g} µm)".replace(".", ",")
    interval = "indéterminé" if iqr is None else f"[{iqr[0]:.3g}, {iqr[1]:.3g}]"
    prefix = {"warn": "Alerte — ", "pass": ""}.get(result.get("status"), "")
    text = prefix + text
    text += (f", intervalle {interval}, proéminence "
             + ("non définie" if prominence is None else "très élevée" if prominence == float("inf")
                else f"{prominence:.2g}".replace(".", ","))
             + f" ; {metrics['patches']} patch(s), niveau {metrics['level']}.")
    if result.get("note"):
        text += f" Notation : {result['note']}."
    text += " Un décalage d'une feuille entière n'est pas détectable."
    for warning in result["profile"].warnings:
        text += f" {warning}"
    return text


class ProfilePlot(QWidget):
    """Mean intensity along the normal (offsets in level-0 voxels), drawn with QPainter."""

    def __init__(self):
        super().__init__()
        self.offsets = self.values = None
        self.peak = None
        self.setMinimumHeight(120)

    def set_profile(self, offsets, values, peak):
        self.offsets, self.values, self.peak = np.asarray(offsets), np.asarray(values), peak
        self.update()

    def to_pixels(self, offset, value):
        margin = 8
        width, height = self.width() - 2 * margin, self.height() - 2 * margin
        low, high = float(self.values.min()), float(self.values.max())
        span_x = float(self.offsets[-1] - self.offsets[0]) or 1.0
        span_y = (high - low) or 1.0
        return QPointF(margin + (offset - self.offsets[0]) / span_x * width,
                       margin + (high - value) / span_y * height)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1e2329"))
        if self.values is None or len(self.values) < 2:
            painter.end()
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        top, bottom = 0.0, float(self.height())
        for offset, color in ((0.0, "#9aa5b1"), (self.peak, "#ff6b6b")):
            if offset is not None:
                x = self.to_pixels(offset, self.values[0]).x()
                painter.setPen(QPen(QColor(color), 1, Qt.PenStyle.DashLine))
                painter.drawLine(QPointF(x, top), QPointF(x, bottom))
        painter.setPen(QPen(QColor("cyan"), 2))
        line = [self.to_pixels(o, v) for o, v in zip(self.offsets, self.values)]
        for a, b in zip(line, line[1:]):
            painter.drawLine(a, b)
        painter.end()


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

    def __init__(self, viewer, layer, points, half, colors=None):
        self.viewer, self.layer, self.points, self.half = viewer, layer, points, half
        self.colors = colors
        viewer.dims.events.point.connect(self.update)
        viewer.dims.events.ndisplay.connect(self.update)
        viewer.dims.events.order.connect(self.update)
        self.update()

    def disconnect(self):
        for event in (self.viewer.dims.events.point, self.viewer.dims.events.ndisplay,
                      self.viewer.dims.events.order):
            event.disconnect(self.update)

    def _slice(self):
        dims = self.viewer.dims
        if dims.ndisplay == 3 or not len(self.points):
            return self.points, slice(None)
        axis = dims.not_displayed[0]
        plane = dims.point[axis] / self.layer.scale[axis]
        inside = np.abs(self.points[:, axis] - plane) <= self.half
        slab = self.points[inside].copy()
        slab[:, axis] = plane
        return slab, inside

    def update(self, event=None):
        if self.layer not in self.viewer.layers:
            self.disconnect()
            return
        points, indices = self._slice()
        self.layer.data = points
        if self.colors is not None and len(points):
            self.layer.face_color = self.colors[indices]


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
        self._drift_layer = None

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
        self.align_button = QPushButton("Mesurer l'alignement")
        self.align_button.setEnabled(False)
        self.drift_button = QPushButton("Cartographier la dérive")
        self.zone_combo = QComboBox()
        self.zone_combo.setPlaceholderText("Choisir une zone à revoir")
        self.zone_combo.setEnabled(False)
        self.drift_label = QLabel()
        self.drift_label.setWordWrap(True)
        self.patches_spin = QSpinBox()
        self.patches_spin.setRange(4, 100)
        self.patches_spin.setValue(DEFAULT_PATCHES)
        self.patches_spin.setToolTip("36 par défaut : avec 12, la mesure retrouve moins bien un "
                                     "décalage connu (calibration T5.1).")
        self.profile_plot = ProfilePlot()
        self.profile_plot.setVisible(False)
        self.align_label = QLabel()
        self.align_label.setWordWrap(True)
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
        form.addRow("Patchs (alignement)", self.patches_spin)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        for control in (self.overlay_button, self.goto_button, self.info_label,
                        self.align_button, self.profile_plot, self.align_label,
                        self.drift_button, self.drift_label, self.zone_combo,
                        self.status_label):
            layout.addWidget(control)

        self.layer_combo.currentIndexChanged.connect(self._layer_changed)
        self.catalog_button.clicked.connect(self._load_catalog)
        self.segment_combo.currentIndexChanged.connect(self._segment_changed)
        self.overlay_button.clicked.connect(self._overlay_clicked)
        self.goto_button.clicked.connect(self.go_to_surface)
        self.align_button.clicked.connect(self._align_clicked)
        self.drift_button.clicked.connect(self._drift_clicked)
        self.zone_combo.activated.connect(self.go_to_zone)
        self._viewer.layers.events.inserted.connect(self._refresh_layers)
        self._viewer.layers.events.removed.connect(self._refresh_layers)
        self._refresh_layers()

    # --- target volume ------------------------------------------------------------------

    def _refresh_layers(self, event=None):
        for name, trace in list(self._traces.items()):
            if trace.layer not in self._viewer.layers:
                trace.disconnect()
                del self._traces[name]
        if self._drift_layer is not None and self._drift_layer not in self._viewer.layers:
            self._clear_drift()
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
        if self._layer() is not self._target:
            self._clear_drift()
        self._update_buttons()
        self._fill_segments()

    def _update_buttons(self):
        layer = self._layer()
        busy = self._worker is not None
        self.overlay_button.setEnabled(layer is not None and not busy)
        self.catalog_button.setEnabled(self._volume_id(layer) is not None and not busy)
        on_target = self._overlay is not None and layer is not None and layer is self._target
        self.align_button.setEnabled(on_target and not busy)
        has_points = on_target and len(self._overlay["points"]) > 0
        self.goto_button.setEnabled(has_points)
        self.drift_button.setEnabled(has_points and not busy)
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
        self._start(prepare_overlay,
                    (source, self.budget_spin.value() * 2**20, volume_shape, overlap),
                    lambda overlay: self._show_overlay(overlay, layer), "Lecture du segment…")

    def _show_overlay(self, overlay, layer):
        if layer is not self._layer():
            return
        self._clear_drift()
        self._target = layer
        name = overlay["name"]
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
        self.profile_plot.setVisible(False)
        self.align_label.setText("")
        self.info_label.setText(describe(overlay))
        self.status_label.setText("Segment superposé.")

    def go_to_surface(self):
        """2D view on the slice through the centre of the displayed points, framing them."""
        if self._overlay is None or not len(self._overlay["points"]) or self._target is None:
            return
        scale = np.asarray(self._target.scale, dtype=float)
        points = self._overlay["points"] * scale
        low, high = points.min(axis=0), points.max(axis=0)
        self._focus_slice((low + high) / 2)
        extent = np.maximum(high[1:] - low[1:], scale[1:])
        size = canvas_size(self._viewer)
        if size:
            camera(self._viewer).zoom = 0.8 * min(size[0] / extent[0], size[1] / extent[1])

    def _focus_slice(self, center):
        viewer = self._viewer
        if viewer.dims.ndisplay != 2:
            viewer.dims.ndisplay = 2
        viewer.dims.order = (0, 1, 2)
        viewer.dims.set_point(0, float(center[0]))
        camera(viewer).center = (float(center[1]), float(center[2]))

    # --- alignment (T5.1) -------------------------------------------------------------------

    def _align_clicked(self):
        layer = self._target
        if self._overlay is None or layer is None or layer not in self._viewer.layers:
            return
        shapes = [tuple(level["shape"]) for level in layer.metadata["volume_summary"]["levels"]]
        self._start(measure_alignment,
                    (self._overlay["surface"], list(layer.data), shapes,
                     layer.metadata.get("pixel_size_um"), DEFAULT_MAX_VOXELS,
                     self.patches_spin.value(), layer.metadata.get("verified_sampling")),
                    self._show_alignment, "Mesure de l'alignement…")

    def _show_alignment(self, result):
        metrics, profile = result["metrics"], result["profile"]
        self.profile_plot.set_profile(profile.offsets, profile.mean, metrics["peak_offset"])
        self.profile_plot.setVisible(True)
        self.align_label.setText(describe_alignment(result))
        name = PATCHES_PREFIX + self._overlay["name"]
        for old in [lyr for lyr in self._viewer.layers if lyr.name == name]:
            self._viewer.layers.remove(old)
        patch_extent = 6 * self._overlay["step"]  # 6 x 6 grid points per patch (step has stride)
        points_layer = self._viewer.add_points(
            np.empty((0, 3)), name=name, size=patch_extent / 2, face_color="transparent",
            border_color="yellow", border_width=0.1, scale=tuple(self._target.scale),
            metadata={"sampling": result["sampling"]})
        self._traces[name] = SliceTrace(self._viewer, points_layer, profile.patch_centers,
                                        patch_extent / 2)
        self._viewer.layers.selection.active = self._target
        self.status_label.setText("Alignement mesuré.")

    # --- drift map (T10) -----------------------------------------------------------------------

    def _drift_clicked(self):
        layer = self._target
        if layer is None or layer is not self._layer():
            return
        shapes = [tuple(level["shape"]) for level in layer.metadata["volume_summary"]["levels"]]
        pixel_size_um = layer.metadata.get("pixel_size_um")
        sampling = layer.metadata.get("verified_sampling")
        args = (self._overlay, list(layer.data), shapes, pixel_size_um)
        if sampling is not None:
            args += (sampling,)
        self._start(measure_drift, args,
                    self._show_drift, "Calcul de la carte de dérive…")

    def _show_drift(self, result):
        target = self._target
        if target is not self._layer():
            return
        colors, zones, reliable = result
        self._clear_drift()
        overlay = self._overlay
        name = DRIFT_PREFIX + overlay["name"]
        half = overlay["step"] / 2
        layer = self._viewer.add_points(
            np.empty((0, 3)), name=name, size=half, border_width=0,
            scale=tuple(target.scale))
        self._drift_layer = layer
        self._traces[layer.name] = SliceTrace(self._viewer, layer, overlay["points"], half, colors)
        for zone in zones:
            if zone["centre_zyx"] is not None:
                self.zone_combo.addItem(
                    f"{zone['rang']}. {ZONE_LABELS[zone['type']]} — {zone['tuiles']} tuile(s)",
                    zone["centre_zyx"])
        self.zone_combo.setCurrentIndex(-1)
        self.zone_combo.setEnabled(self.zone_combo.count() > 0)
        unit = "µm" if target.metadata.get("pixel_size_um") else "voxels"
        self.drift_label.setText(
            f"{reliable} tuile(s) fiable(s), {len(zones)} zone(s) à revoir. "
            f"Bleu −{DEFAULT_MAX_DRIFT_UM:g}, blanc 0, rouge +{DEFAULT_MAX_DRIFT_UM:g} {unit}. "
            "Gris pour les tuiles peu fiables ou non mesurées.")
        self._viewer.layers.selection.active = target
        self.status_label.setText("Carte de dérive calculée.")

    def _clear_drift(self):
        layer, self._drift_layer = self._drift_layer, None
        self.zone_combo.clear()
        self.zone_combo.setEnabled(False)
        self.drift_label.clear()
        if layer is not None and layer in self._viewer.layers:
            self._viewer.layers.remove(layer)

    def go_to_zone(self, index):
        center = self.zone_combo.itemData(index)
        if center is not None and self._target is self._layer():
            self._focus_slice(np.asarray(center) * self._target.scale)

    # --- workers -------------------------------------------------------------------------------

    def _start(self, function, args, on_result, message):
        self._worker = thread_worker(function, ignore_errors=True)(*args)
        self._update_buttons()
        self.status_label.setText(message)
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
