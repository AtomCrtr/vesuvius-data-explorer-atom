"""QC panel: run or load a report, show anomalies on the image, navigate, measure the view.

All computation lives in ``qc/`` and ``core/``; this module only wires Qt and napari.
Reads (QC sampling, view measurement) always run in a worker thread.
"""

import json
from pathlib import Path

from napari.layers import Image
from napari.qt.threading import thread_worker
from napari.viewer import Viewer
from qtpy.QtCore import Qt
from qtpy.QtGui import QColor
from qtpy.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vesuvius_data_explorer.core.volume import open_volume_store, read_slice
from vesuvius_data_explorer.qc import run_volume
from vesuvius_data_explorer.qc.locate import location_to_world, view_metrics, visible_region
from vesuvius_data_explorer.qc.report import validate_report
from vesuvius_data_explorer.qc.thresholds import load_thresholds

ANOMALY_LAYER = "QC — anomalies"
NO_VOLUME = "Aucun volume ouvert par le plugin : utiliser « Vesuvius — Ouvrir un volume »."
COARSEST = "Le plus grossier"
STATUS_ORDER = {"fail": 0, "error": 1, "warn": 2, "pass": 3, "skipped": 4}
STATUS_COLORS = {"fail": "#ffd0cc", "error": "#ffd0cc", "warn": "#fff0ba", "pass": "#ccebd6",
                 "skipped": "#dddddd"}
TEXT_COLOR = "#18232b"
EDGE_COLORS = {"fail": "red", "warn": "orange"}
AXES = ("z", "y", "x")


def camera(viewer):
    """napari >= 0.9 exposes the camera on ``viewer.scene``; older versions on the viewer."""
    scene = getattr(viewer, "scene", None)
    return scene.camera if scene is not None else viewer.camera


def canvas_size(viewer):
    """Canvas (height, width) in screen pixels: ``viewer.canvas`` (>= 0.9) or older field."""
    canvas = getattr(viewer, "canvas", None)
    size = getattr(canvas, "size", None) if canvas is not None else None
    if size is None:
        size = getattr(viewer, "_canvas_size", None)
    return tuple(int(n) for n in size) if size is not None else None


def view_box(viewer):
    """(plane axis, plane world coordinate, low, high) of the current 2D view.

    ``low`` / ``high`` are world corners on the two displayed axes, in (z, y, x) order.
    """
    a, b = viewer.dims.displayed
    plane = next(i for i in range(3) if i not in (a, b))
    size = canvas_size(viewer) or (512, 512)
    cam = camera(viewer)
    center = tuple(cam.center[-2:])
    half = (size[0] / cam.zoom / 2, size[1] / cam.zoom / 2)
    if a > b:
        center, half = center[::-1], half[::-1]
    low = tuple(c - h for c, h in zip(center, half))
    high = tuple(c + h for c, h in zip(center, half))
    return AXES[plane], viewer.dims.point[plane], low, high


def _qc_layers(viewer):
    return [layer for layer in viewer.layers if isinstance(layer, Image)
            and "source" in layer.metadata and "volume_summary" in layer.metadata]


def run_qc(source, level, samples, seed, max_voxels, config):
    """Worker body: open the store and run the bounded QC (no Qt here)."""
    thresholds = load_thresholds(config or None)
    root = open_volume_store(source)
    return run_volume(root, uri=source, level=level, samples=samples, seed=seed,
                      max_voxels=max_voxels, thresholds=thresholds)


def measure(array, region, background):
    """Worker body: one bounded read of the visible region, then its metrics."""
    data = read_slice(array, region["axis"], region["index"], region["start_a"],
                      region["start_b"], width=region["width_a"], width_b=region["width_b"])
    return region, data.shape, view_metrics(data, background["value"],
                                            bool(background["enabled"]))


class QCWidget(QWidget):
    def __init__(self, napari_viewer: Viewer):
        super().__init__()
        self._viewer = napari_viewer
        self._worker = None
        self._report = None
        self._target = None
        self._rows = []
        self._report_matches = True

        self.layer_combo = QComboBox()
        self.level_combo = QComboBox()
        self.samples_spin = QSpinBox()
        self.samples_spin.setRange(0, 10_000)
        self.samples_spin.setValue(16)
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 2**31 - 1)
        self.budget_spin = QSpinBox()
        self.budget_spin.setRange(0, 2**31 - 1)
        self.budget_spin.setValue(16_777_216)
        self.config_input = QLineEdit()
        self.config_input.setPlaceholderText("Fichier de seuils TOML (optionnel)")

        self.run_button = QPushButton("Lancer le QC")
        self.load_button = QPushButton("Charger un rapport JSON…")
        self.measure_button = QPushButton("Mesurer la vue")
        self.summary_label = QLabel()
        self.results_table = QTableWidget(0, 4)
        self.results_table.setHorizontalHeaderLabels(["Contrôle", "Statut", "Valeur", "Message"])
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.locations_list = QListWidget()
        self.measure_label = QLabel()
        self.measure_label.setWordWrap(True)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Volume", self.layer_combo)
        form.addRow("Niveau", self.level_combo)
        form.addRow("ROI", self.samples_spin)
        form.addRow("Graine", self.seed_spin)
        form.addRow("Budget (voxels)", self.budget_spin)
        form.addRow("Seuils", self.config_input)
        buttons = QHBoxLayout()
        buttons.addWidget(self.run_button)
        buttons.addWidget(self.load_button)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(buttons)
        for control in (self.summary_label, self.results_table, QLabel("Localisations"),
                        self.locations_list, self.measure_button, self.measure_label,
                        self.status_label):
            layout.addWidget(control)

        self.layer_combo.currentIndexChanged.connect(self._layer_changed)
        self.run_button.clicked.connect(self._run)
        self.load_button.clicked.connect(self._choose_report)
        self.measure_button.clicked.connect(self._measure)
        self.results_table.itemSelectionChanged.connect(self._result_selected)
        self.locations_list.currentRowChanged.connect(self._location_selected)
        self._viewer.layers.events.inserted.connect(self._refresh_layers)
        self._viewer.layers.events.removed.connect(self._refresh_layers)
        self._refresh_layers()

    # --- target layer -------------------------------------------------------------------

    def _refresh_layers(self, event=None):
        current = self.layer_combo.currentText()
        names = [layer.name for layer in _qc_layers(self._viewer)]
        self.layer_combo.blockSignals(True)
        self.layer_combo.clear()
        self.layer_combo.addItems(names)
        if current in names:
            self.layer_combo.setCurrentText(current)
        self.layer_combo.blockSignals(False)
        self._layer_changed()

    def _layer(self):
        name = self.layer_combo.currentText()
        for layer in _qc_layers(self._viewer):
            if layer.name == name:
                return layer
        return None

    def _layer_changed(self, *args):
        layer = self._layer()
        level = self.level_combo.currentText()
        self.level_combo.clear()
        enabled = layer is not None
        for button in (self.run_button, self.load_button, self.measure_button):
            button.setEnabled(enabled and self._worker is None)
        if not enabled:
            self.status_label.setText(NO_VOLUME)
            return
        self.level_combo.addItem(COARSEST)
        self.level_combo.addItems([lv["key"] for lv in layer.metadata["volume_summary"]["levels"]])
        if self.level_combo.findText(level) >= 0:
            self.level_combo.setCurrentText(level)
        if self.status_label.text() == NO_VOLUME:
            self.status_label.setText("")

    # --- workers --------------------------------------------------------------------------

    def _start(self, function, args, on_result, message):
        for button in (self.run_button, self.load_button, self.measure_button):
            button.setEnabled(False)
        self.status_label.setText(message)
        self._worker = thread_worker(function, ignore_errors=True)(*args)
        self._worker.returned.connect(on_result)
        self._worker.errored.connect(self._error)
        self._worker.finished.connect(self._finished)
        self._worker.start()

    def _finished(self):
        self._worker = None
        self._layer_changed()
        if self.status_label.text().endswith("…"):
            self.status_label.setText("")

    def _error(self, error):
        message = str(error)
        safe = isinstance(error, (ValueError, FileNotFoundError, KeyError)) and message[:1].isupper()
        self.status_label.setText(message if safe else
                                  "Opération impossible. Vérifier le volume, le fichier de seuils "
                                  "et l'accès au stockage ou au réseau.")

    # --- run / load a report -------------------------------------------------------------

    def _run(self):
        layer = self._layer()
        if layer is None:
            return
        level = self.level_combo.currentText()
        args = (layer.metadata["source"], None if level == COARSEST else level,
                self.samples_spin.value(), self.seed_spin.value(), self.budget_spin.value(),
                self.config_input.text().strip())
        self._target = layer
        self._start(run_qc, args, self._show_report, "Contrôle qualité en cours…")

    def _choose_report(self):
        path, _ = QFileDialog.getOpenFileName(self, "Charger un rapport QC", "",
                                              "Rapport JSON (*.json)")
        if path:
            self.load_report_file(path)

    def load_report_file(self, path):
        layer = self._layer()
        if layer is None:
            return
        try:
            report = json.loads(Path(path).read_text(encoding="utf-8"))
            validate_report(report)
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            self._show_error("Rapport illisible ou non conforme au schéma QC.")
            return
        self._target = layer
        self._show_report(report)

    def _show_error(self, message):
        self.status_label.setText(message)

    def _show_report(self, report):
        layer = self._target
        if report["target"]["kind"] != "volume":
            self._show_error("Rapport de surface : utiliser « Vesuvius — Surfaces » pour superposer "
                             "le segment et calculer ses indicateurs.")
            return
        notes = []
        # Locations only make sense on the volume the report was produced for: drawing them on
        # another one would point at the wrong voxels.
        self._report_matches = (str(report["target"]["uri"]).rstrip("/")
                                == str(layer.metadata["source"]).rstrip("/"))
        if not self._report_matches:
            notes.append(f"Attention : rapport produit pour {report['target']['uri']}, pas pour "
                         f"{layer.metadata['source']} : résultats affichés, anomalies ni dessinées "
                         "ni navigables.")
        self._report = report
        summary = report["summary"]
        self.summary_label.setText(" · ".join(f"{status} : {summary[status]}"
                                              for status in STATUS_ORDER))
        self._rows = sorted(report["results"], key=lambda r: STATUS_ORDER[r["status"]])
        self.results_table.setRowCount(len(self._rows))
        for row, result in enumerate(self._rows):
            value = "" if result["value"] is None else f"{result['value']:.4g}"
            cells = (result["check_id"], result["status"], value, result["message"])
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setBackground(QColor(STATUS_COLORS[result["status"]]))
                # Light status colours need dark text, whatever napari's theme is.
                item.setForeground(QColor(TEXT_COLOR))
                self.results_table.setItem(row, column, item)
        self.results_table.resizeColumnsToContents()
        self.locations_list.clear()
        if not self._report_matches:
            for old in [lyr for lyr in self._viewer.layers if lyr.name == ANOMALY_LAYER]:
                self._viewer.layers.remove(old)
            self.status_label.setText(" ".join(notes))
            return
        drawn, skipped = self._draw_anomalies(layer, report)
        if skipped:
            notes.append(f"{skipped} localisation(s) sur un niveau absent de ce volume, ignorée(s).")
        notes.insert(0, f"Rapport affiché : {drawn} anomalie(s) localisée(s) sur l'image.")
        self.status_label.setText(" ".join(notes))

    def _draw_anomalies(self, layer, report):
        levels = layer.metadata["volume_summary"]["levels"]
        rectangles, edges, check_ids, skipped = [], [], [], 0
        for result in report["results"]:
            if result["status"] not in EDGE_COLORS or result["check_id"].startswith(
                    "volume.levels") or result["check_id"] == "volume.chunks.size":
                continue
            for location in result["locations"]:
                try:
                    box = location_to_world(location, levels, layer.scale)
                except KeyError:
                    skipped += 1
                    continue
                rectangles.append(box.rectangle())
                edges.append(EDGE_COLORS[result["status"]])
                check_ids.append(result["check_id"])
        for old in [lyr for lyr in self._viewer.layers if lyr.name == ANOMALY_LAYER]:
            self._viewer.layers.remove(old)
        if rectangles:
            self._viewer.add_shapes(
                rectangles, shape_type="rectangle", name=ANOMALY_LAYER, edge_color=edges,
                face_color="transparent", edge_width=2 * float(min(layer.scale)),
                features={"check_id": check_ids},
                text={"string": "{check_id}", "color": "white", "size": 9, "anchor": "upper_left"},
            )
            self._viewer.layers.selection.active = layer
        return len(rectangles), skipped

    # --- navigation ------------------------------------------------------------------------

    def _result_selected(self):
        self.locations_list.clear()
        rows = {index.row() for index in self.results_table.selectedIndexes()}
        if not rows:
            return
        result = self._rows[rows.pop()]
        if not self._report_matches:
            return
        for location in result["locations"]:
            text = (f"niveau {location['level']} · {location['axis']}={location['index']} · "
                    f"origine {tuple(location['origin'])} · taille {tuple(location['size'])}")
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, location)
            self.locations_list.addItem(item)

    def _location_selected(self, row):
        if row < 0:
            return
        location = self.locations_list.item(row).data(Qt.ItemDataRole.UserRole)
        layer = self._layer()
        try:
            box = location_to_world(location, layer.metadata["volume_summary"]["levels"],
                                    layer.scale)
        except KeyError as error:
            self._error(error)
            return
        self.go_to(box)

    def go_to(self, box):
        viewer = self._viewer
        plane = AXES.index(box.axis)
        a, b = box.in_plane_axes
        if viewer.dims.ndisplay != 2:
            viewer.dims.ndisplay = 2
        if tuple(viewer.dims.order[-2:]) != (a, b):
            viewer.dims.order = (plane, a, b)
        viewer.dims.set_point(plane, box.plane)
        cam = camera(viewer)
        cam.center = box.center
        height, width = (high - low for low, high in zip(box.low, box.high))
        size = canvas_size(viewer)
        if size and height > 0 and width > 0:
            # The rectangle fills about half of the view.
            cam.zoom = 0.5 * min(size[0] / height, size[1] / width)

    # --- measure the view ------------------------------------------------------------------

    def _measure(self):
        layer = self._layer()
        viewer = self._viewer
        if layer is None:
            return
        if viewer.dims.ndisplay != 2:
            self.measure_label.setText("La mesure de la vue est 2D : repasser en vue 2D.")
            return
        levels = layer.metadata["volume_summary"]["levels"]
        region = visible_region(levels, layer.scale, *view_box(viewer))
        array = layer.data[[lv["key"] for lv in levels].index(region["level"])]
        try:
            background = load_thresholds(self.config_input.text().strip() or None)[
                "volume.background"]
        except (OSError, ValueError) as error:
            self._error(error)
            return
        self._start(measure, (array, region, dict(background)), self._show_measure,
                    "Mesure de la vue en cours…")

    def _show_measure(self, outcome):
        region, shape, metrics = outcome
        background = metrics["background_pct"]
        self.measure_label.setText(
            f"Niveau {region['level']}, coupe {region['axis']}={region['index']}, "
            f"fenêtre {shape[0]} × {shape[1]} : finis {metrics['finite_pct']:.4g} %, "
            f"p1 {metrics['p1']:.4g}, p99 {metrics['p99']:.4g}, écart-type {metrics['std']:.4g}, "
            + ("fond non exclu." if background is None else f"fond {background:.4g} %.")
        )
