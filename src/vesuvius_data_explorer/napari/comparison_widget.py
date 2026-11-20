"""Compare registered UV products without running inference or changing source files."""

from pathlib import Path

import numpy as np
from napari.qt.threading import thread_worker
from napari.utils import Colormap
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QWidget,
)

from ..core.comparison import (
    CONSENSUS_COLOR,
    MAX_CANDIDATES,
    PREDICTION_COLORS,
    UNCERTAIN_COLORS,
    Z_SENSITIVITY_COLOR,
    Candidate,
    ComparisonView,
    comparable_probabilities,
    comparison_values,
    export_comparison_png,
    load_comparison,
    load_comparison_session,
    orientation_pair,
    roi_coordinates,
    save_comparison_session,
)
from ..core.ink_disagreement import inspect_pair
from ..core.ink_exam import export_examination, propose_candidates
from ..core.ink_factorial import CONDITIONS, registered_conditions
from .factorial_view import factorial_dialog, prepare_factorial
from .ink_review import agreement_dialog, candidate_gallery, edit_candidate
from .multimodal import open_validation

MODES = ("overlay", "difference", "consensus", "uncertainty", "z_sensitivity")


def _prepare_comparison(loader, path):
    loaded = loader(path)
    comparison, view = loaded if isinstance(loaded, tuple) else (loaded, None)
    display = tuple(np.nan_to_num(item.image.pixels, nan=0.0)
                    for item in comparison.predictions)
    return comparison, view, display


def _analysis_pixels(a, b, threshold, mode):
    values = comparison_values(a, b, threshold, mode)
    return np.nan_to_num(values, nan=0, copy=False) if mode in ("difference", "z_sensitivity") else values


class ComparisonWidget(QWidget):
    def __init__(self, napari_viewer):
        super().__init__()
        self.viewer = napari_viewer
        self._worker = None
        self._planes = []
        self._predictions = []
        self._comparison = None
        self._disagreement = None
        self._comparison_revision = 0
        self._analysis_worker = None
        self._requested_analysis = None
        self._displayed_analysis = None
        self._regions = None
        self._candidates = []
        self._updating = False
        form = QFormLayout(self)
        self.open_button = QPushButton("Ouvrir un manifeste de comparaison")
        self.open_session = QPushButton("Reprendre une session")
        self.multimodal_button = QPushButton("Ouvrir une validation CT–optique")
        self.save_session = QPushButton("Enregistrer la session")
        self.export_button = QPushButton("Exporter la région en PNG")
        self.export_exam = QPushButton("Exporter le dossier d’examen")
        self.reference = QComboBox()
        self.reference.addItems(["CT projeté", "Surface déroulée"])
        self.prediction = QComboBox()
        self.prediction_b = QComboBox()
        self.disagreement = QCheckBox("Désaccord au seuil")
        self.analysis = QComboBox()
        self.analysis.addItems(["Superposition", "Différence A − B", "Consensus positif au seuil",
                                "Proches du seuil / données manquantes", "Sensibilité à l’ordre Z"])
        self.threshold = QSpinBox()
        self.threshold.setRange(1, 99)
        self.threshold.setValue(50)
        self.threshold.setSuffix(" %")
        self.opacity = QSpinBox()
        self.opacity.setRange(0, 100)
        self.opacity.setValue(100)
        self.opacity.setSuffix(" %")
        self.roi = [QSpinBox() for _ in range(4)]
        roi_row = QHBoxLayout()
        for field, label in zip(self.roi, ("v", "u", "h", "l")):
            field.setPrefix(f"{label} ")
            field.setAccessibleName({"v": "Ligne V", "u": "Colonne U", "h": "Hauteur",
                                     "l": "Largeur"}[label])
            field.valueChanged.connect(self._update_regions)
            roi_row.addWidget(field)
        self.coordinates = QLabel()
        self.candidates = QComboBox()
        self.add_candidate = QPushButton("Ajouter un candidat à la région")
        self.propose_button = QPushButton("Proposer des régions par rang")
        self.review_candidate = QPushButton("Documenter l’observation")
        self.gallery_button = QPushButton("Galerie des observations")
        self.remove_candidate = QPushButton("Retirer le candidat sélectionné")
        self.agreement_button = QPushButton("Accord par seuil et distributions")
        self.factorial_button = QPushButton("Comparer les conditions Z en 2 × 2")
        self.z_button = QPushButton("Superposer la sensibilité Z sur le CT")
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setAccessibleName("Chargement de la comparaison")
        form.addRow(self.open_button)
        form.addRow(self.open_session)
        form.addRow(self.multimodal_button)
        form.addRow("Fond", self.reference)
        form.addRow("Carte A (orange)", self.prediction)
        form.addRow("Carte B (bleu)", self.prediction_b)
        form.addRow("Analyse", self.analysis)
        form.addRow(self.disagreement)
        form.addRow(self.agreement_button)
        form.addRow(self.factorial_button)
        form.addRow(self.z_button)
        form.addRow("Seuil d’affichage", self.threshold)
        form.addRow("Opacité", self.opacity)
        form.addRow("Région (pixels locaux)", roi_row)
        form.addRow(self.coordinates)
        form.addRow("Candidats à valider", self.candidates)
        form.addRow(self.add_candidate)
        form.addRow(self.propose_button)
        form.addRow(self.review_candidate)
        form.addRow(self.gallery_button)
        form.addRow(self.remove_candidate)
        form.addRow(self.save_session)
        form.addRow(self.export_button)
        form.addRow(self.export_exam)
        form.addRow(self.status)
        form.addRow(self.progress)
        self._view_controls = (self.reference, self.prediction, self.prediction_b,
                               self.disagreement, self.analysis, self.threshold, self.opacity, *self.roi,
                               self.add_candidate, self.save_session, self.export_button, self.export_exam)
        self.open_button.clicked.connect(self._choose)
        self.open_session.clicked.connect(self._choose_session)
        self.multimodal_button.clicked.connect(lambda: open_validation(self))
        self.save_session.clicked.connect(self._save)
        self.export_button.clicked.connect(self._export)
        self.export_exam.clicked.connect(self._export_examination)
        self.reference.currentIndexChanged.connect(self._update_visibility)
        self.prediction.currentIndexChanged.connect(lambda: self._choose_model(self.prediction_b))
        self.prediction_b.currentIndexChanged.connect(lambda: self._choose_model(self.prediction))
        self.disagreement.toggled.connect(self._update_visibility)
        self.analysis.currentIndexChanged.connect(self._update_visibility)
        self.threshold.valueChanged.connect(self._update_threshold)
        self.opacity.valueChanged.connect(self._update_opacity)
        self.add_candidate.clicked.connect(self._annotate)
        self.propose_button.clicked.connect(self._propose)
        self.review_candidate.clicked.connect(self._review_candidate)
        self.gallery_button.clicked.connect(self._gallery)
        self.remove_candidate.clicked.connect(self._remove_annotation)
        self.agreement_button.clicked.connect(self._agreement)
        self.factorial_button.clicked.connect(self._factorial)
        self.z_button.clicked.connect(self._select_z_pair)
        self.candidates.activated.connect(self._select_candidate)
        self._set_enabled()

    def _choose(self):
        path, _ = QFileDialog.getOpenFileName(self, "Comparer des prédictions",
                                              filter="Manifeste JSON (*.json)")
        if path:
            self.load(path)

    def load(self, path):
        self._load(path, load_comparison)

    def _choose_session(self):
        path, _ = QFileDialog.getOpenFileName(self, "Reprendre une session",
                                              filter="Session JSON (*.json)")
        if path:
            self._load(path, load_comparison_session)

    def _set_enabled(self):
        idle = self._worker is None
        self.open_button.setEnabled(idle)
        self.open_session.setEnabled(idle)
        for control in self._view_controls:
            control.setEnabled(idle and self._comparison is not None)
        self.remove_candidate.setEnabled(idle and bool(self._candidates))
        self.review_candidate.setEnabled(idle and bool(self._candidates))
        self.gallery_button.setEnabled(idle and bool(self._candidates))
        has_pair = (idle and self._comparison is not None and self.prediction.currentIndex() > 0
                    and self.prediction_b.currentIndex() > 0)
        self.agreement_button.setEnabled(has_pair)
        self.factorial_button.setEnabled(idle and self._comparison is not None and any(
            (model.provenance or {}).get("factorial_condition") in CONDITIONS
            for model in self._comparison.predictions))
        self.z_button.setEnabled(idle and self._z_pair() is not None)
        self.propose_button.setEnabled(has_pair and len(self._candidates) < MAX_CANDIDATES)
        self.disagreement.setEnabled(idle and self._comparison is not None
                                     and self.analysis.currentIndex() == 0)
        self.progress.setVisible(not idle or self._analysis_worker is not None)

    def _load(self, path, loader):
        if self._worker is not None:
            return
        self.status.setText("Chargement des plans UV…")
        self._worker = thread_worker(_prepare_comparison, ignore_errors=True)(loader, path)
        self._worker.returned.connect(lambda result: self._show(*result))
        self._worker.errored.connect(self._error)
        self._worker.finished.connect(self._finished)
        self._set_enabled()
        self._worker.start()

    def _finished(self):
        self._worker = None
        self._set_enabled()

    def _error(self, error):
        self.status.setText(f"Comparaison indisponible. {error}")

    def _colormap(self, slot=0):
        return Colormap([(0, 0, 0, 0), (*PREDICTION_COLORS[slot], 0.8)],
                        controls=[0, self.threshold.value() / 100, 1], interpolation="zero")

    def _show(self, comparison, view, display):
        self._updating = True
        for layer in (*self._planes, *self._predictions, self._disagreement, self._regions):
            if layer is not None and layer in self.viewer.layers:
                self.viewer.layers.remove(layer)
        self._planes.clear()
        self._predictions.clear()
        self._disagreement = self._regions = None
        self._comparison_revision += 1
        self._displayed_analysis = None
        self._comparison = comparison
        metadata = {"volume_id": comparison.volume_id, "segment_id": comparison.segment_id,
                    "surface_revision": comparison.surface_revision, "axes": ["v", "u"],
                    "origin_vu": comparison.origin_vu}
        scale = comparison.pixel_size_um_vu
        translate = tuple(i * step for i, step in zip(comparison.origin_vu, scale))
        for label, plane in (("CT projeté", comparison.ct), ("Surface déroulée", comparison.surface)):
            layer = self.viewer.add_image(plane.pixels, name=label, rgb=False, scale=scale,
                                          translate=translate, visible=False,
                                          metadata={**metadata, "source": str(plane.path)})
            self._planes.append(layer)
        for selector in (self.prediction, self.prediction_b):
            selector.clear()
            selector.addItems(["Aucune", *(item.name + (" · calibration déclarée"
                                if item.calibration else " · score non calibré")
                                for item in comparison.predictions)])
        for prediction, pixels in zip(comparison.predictions, display):
            layer = self.viewer.add_image(
                pixels, name=prediction.name, rgb=False, scale=scale, translate=translate,
                visible=False, colormap=self._colormap(), contrast_limits=(0, prediction.score_scale),
                blending="translucent_no_depth",
                metadata={**metadata, "source": str(prediction.image.path),
                          "model": prediction.model, "score_scale": prediction.score_scale,
                          "provenance": prediction.provenance, "calibration": prediction.calibration,
                          "registration": prediction.registration},
            )
            self._predictions.append(layer)
        rows, cols = comparison.ct.pixels.shape
        if view is None:
            view = ComparisonView(0, (1, 0), self.threshold.value(), self.opacity.value(),
                                  False, (0, 0, rows, cols))
        self.reference.setCurrentIndex(view.reference)
        self.prediction.setCurrentIndex(view.models[0])
        self.prediction_b.setCurrentIndex(view.models[1])
        self.disagreement.setChecked(view.disagreement)
        self.analysis.setCurrentIndex(MODES.index(view.mode))
        self.threshold.setValue(view.threshold)
        self.opacity.setValue(view.opacity)
        for field, low, high, value in zip(self.roi, (0, 0, 1, 1),
                                           (rows - 1, cols - 1, rows, cols), view.roi):
            field.setRange(low, high)
            field.setValue(value)
        self._candidates = list(view.candidates)
        self._updating = False
        self._update_visibility()
        self._refresh_candidates()
        self._set_enabled()

    def _choose_model(self, other):
        if self._updating:
            return
        a, b = self.prediction.currentIndex(), self.prediction_b.currentIndex()
        if a == b != 0:
            other.setCurrentIndex(0)
        self._update_visibility()

    def _z_pair(self):
        if self._comparison is None:
            return None
        try:
            positions = registered_conditions(self._comparison)
        except ValueError:
            return None
        for first, second in (("A+", "A-"), ("B+", "B-")):
            if first in positions and second in positions:
                indexes = positions[first], positions[second]
                if orientation_pair(*(self._comparison.predictions[i-1] for i in indexes)):
                    return indexes
        return None

    def _select_z_pair(self):
        pair = self._z_pair()
        if pair is None:
            return
        self._updating = True
        self.prediction.setCurrentIndex(pair[0])
        self.prediction_b.setCurrentIndex(pair[1])
        self.reference.setCurrentIndex(0)
        self.analysis.setCurrentIndex(MODES.index("z_sensitivity"))
        self._updating = False
        self._update_visibility()

    def _update_visibility(self):
        if self._updating or self._comparison is None:
            return
        a, b = self.prediction.currentIndex(), self.prediction_b.currentIndex()
        mode = MODES[self.analysis.currentIndex()]
        if mode == "overlay" and self.disagreement.isChecked():
            mode = "disagreement"
        show_diff = mode != "overlay"
        self.disagreement.setEnabled(self._worker is None and self.analysis.currentIndex() == 0)
        for index, layer in enumerate(self._planes):
            layer.visible = index == self.reference.currentIndex()
        display_maps = {index: slot for slot, index in enumerate((a, b))
                        if index and not show_diff}
        for index, layer in enumerate(self._predictions, start=1):
            if index in display_maps:
                layer.colormap = self._colormap(display_maps[index])
            layer.visible = index in display_maps
        if self._disagreement is not None:
            self._disagreement.visible = False
        self._requested_analysis = None
        if not show_diff:
            # Keep B above A regardless of the order in the input manifest.
            if a and b and all(self._predictions[i - 1] in self.viewer.layers for i in (a, b)):
                first, second = (self.viewer.layers.index(self._predictions[i - 1])
                                 for i in (a, b))
                if second < first:
                    self.viewer.layers.move(second, first + 1)
        elif a and b and (mode != "z_sensitivity" or orientation_pair(
                self._comparison.predictions[a-1], self._comparison.predictions[b-1])):
            threshold = 0 if mode in ("difference", "z_sensitivity") else self.threshold.value()
            key = (self._comparison_revision, a, b, threshold, mode)
            self._requested_analysis = key
            if (key == self._displayed_analysis and self._disagreement is not None
                    and self._disagreement in self.viewer.layers):
                self._disagreement.visible = True
            elif self._analysis_worker is None:
                self._start_analysis(key)
        self._update_opacity()
        comparison = self._comparison
        if show_diff and not (a and b):
            self.status.setText("Choisir deux cartes pour cette analyse.")
        elif mode == "z_sensitivity" and self._requested_analysis is None:
            self.status.setText("Choisir les deux ordres du même checkpoint et de la même expérience.")
        elif self._requested_analysis and self._requested_analysis != self._displayed_analysis:
            self.status.setText("Calcul de la comparaison…")
        else:
            self.status.setText(f"{comparison.segment_id} · {comparison.surface_revision}")
        self._set_enabled()

    def _update_threshold(self):
        self._update_visibility()

    def _update_opacity(self):
        if self._updating:
            return
        for layer in self._predictions:
            layer.opacity = self.opacity.value() / 100
        if self._disagreement is not None:
            self._disagreement.opacity = self.opacity.value() / 100

    def _start_analysis(self, key):
        _, a, b, threshold, mode = key
        maps = self._comparison.predictions
        self._analysis_worker = thread_worker(_analysis_pixels, ignore_errors=True)(
            maps[a - 1], maps[b - 1], threshold, mode)
        self._analysis_worker.returned.connect(lambda result: self._show_analysis(key, result))
        self._analysis_worker.errored.connect(
            lambda error: self._error(error) if self._requested_analysis == key else None)
        self._analysis_worker.finished.connect(lambda: self._analysis_finished(key))
        self._set_enabled()
        self._analysis_worker.start()

    def _analysis_finished(self, key):
        self._analysis_worker = None
        if self._requested_analysis is not None and self._requested_analysis != key:
            self._start_analysis(self._requested_analysis)
        self._set_enabled()

    def _show_analysis(self, key, values):
        if key != self._requested_analysis:
            return
        _, a, b, threshold, mode = key
        maps = self._comparison.predictions
        models = (maps[a - 1], maps[b - 1])
        transparent = (0, 0, 0, 0)
        if mode == "difference":
            label = ("Différence de probabilités déclarées A − B" if comparable_probabilities(*models)
                     else "Différence de scores normalisés A − B")
            limits = (-1, 1)
            colormap = Colormap([(*PREDICTION_COLORS[1], 1), transparent,
                                 (*PREDICTION_COLORS[0], 1)])
        elif mode == "z_sensitivity":
            label, limits = "Sensibilité Z · écart absolu de score", (0, 1)
            colormap = Colormap([transparent, (*Z_SENSITIVITY_COLOR, 1)])
        elif mode == "consensus":
            label, limits = "Consensus positif au seuil", (0, 1)
            colormap = Colormap([transparent, (*CONSENSUS_COLOR, 1)])
        elif mode == "uncertainty":
            label, limits = "Jaune · ±5 points du seuil   Violet · données manquantes", (0, 2)
            colors = [transparent, *((*color, 1) for color in UNCERTAIN_COLORS)]
            colormap = Colormap(colors, controls=[0, 0.25, 0.75, 1], interpolation="zero")
        else:
            label, limits = "Désaccord au seuil", (0, 2)
            colors = [transparent, *((*color, 1) for color in PREDICTION_COLORS)]
            colormap = Colormap(colors, controls=[0, 0.25, 0.75, 1], interpolation="zero")
        metadata = {"mode": mode, "models": [item.model for item in models],
                    "manifest_sha256": self._comparison.manifest_sha256,
                    "threshold": threshold if mode not in ("difference", "z_sensitivity") else None,
                    "calibrated_pair": comparable_probabilities(*models)}
        if self._disagreement is None or self._disagreement not in self.viewer.layers:
            base = self._planes[0]
            self._disagreement = self.viewer.add_image(
                values, name=label, rgb=False, scale=base.scale, translate=base.translate,
                contrast_limits=limits, colormap=colormap, blending="translucent_no_depth",
                metadata=metadata,
            )
        else:
            self._disagreement.data = values
            self._disagreement.contrast_limits_range = limits
            self._disagreement.contrast_limits = limits
            self._disagreement.colormap = colormap
            self._disagreement.name = label
            self._disagreement.metadata = metadata
            self._disagreement.visible = True
        self._displayed_analysis = key
        self._update_opacity()
        self.status.setText(label)

    def _region(self):
        return tuple(field.value() for field in self.roi)

    def _update_regions(self):
        if self._updating or self._comparison is None:
            return
        self._updating = True
        rows, cols = self._comparison.ct.pixels.shape
        self.roi[2].setMaximum(rows - self.roi[0].value())
        self.roi[3].setMaximum(cols - self.roi[1].value())
        self._updating = False
        region = self._region()
        coords = roi_coordinates(self._comparison, region)
        v0, u0 = coords["start_vu"]
        v1, u1 = coords["stop_vu"]
        self.coordinates.setText(f"V [{v0}, {v1}) · U [{u0}, {u1})")
        regions = [item.roi for item in self._candidates]
        if region != (0, 0, rows, cols):
            regions.insert(0, region)
        if not regions:
            if self._regions is not None:
                self._regions.visible = False
            return
        rectangles = []
        for v, u, h, w in regions:
            rectangles.append(np.array([[v, u], [v, u + w], [v + h, u + w], [v + h, u]]) - 0.5)
        if self._regions is None or self._regions not in self.viewer.layers:
            base = self._planes[0]
            self._regions = self.viewer.add_shapes(
                rectangles, shape_type="rectangle", name="Régions UV et candidats à valider",
                scale=base.scale, translate=base.translate, edge_width=1,
                edge_color="yellow", face_color="transparent",
            )
            self._regions.editable = False
        else:
            self._regions.data = rectangles
            self._regions.visible = True
        position = self.viewer.layers.index(self._regions)
        if position < len(self.viewer.layers) - 1:
            self.viewer.layers.move(position, len(self.viewer.layers))

    def _refresh_candidates(self):
        self.candidates.clear()
        for item in self._candidates:
            v, u = roi_coordinates(self._comparison, item.roi)["start_vu"]
            self.candidates.addItem(f"{item.label} · V {v}, U {u}")
        self._update_regions()

    def _select_candidate(self, index):
        v, u, height, width = self._candidates[index].roi
        rows, cols = self._comparison.ct.pixels.shape
        self._updating = True
        self.roi[2].setMaximum(rows - v)
        self.roi[3].setMaximum(cols - u)
        for field, value in zip(self.roi, (v, u, height, width)):
            field.setValue(value)
        self._updating = False
        self._update_regions()

    def _annotate(self):
        label, accepted = QInputDialog.getText(self, "Caractère candidat à valider",
                                               "Nom de la région")
        if not accepted or not label.strip():
            return
        if len(label.strip()) > 80 or len(self._candidates) >= MAX_CANDIDATES:
            self.status.setText("Limite de 80 caractères par libellé et de 256 candidats.")
            return
        models = tuple(i for i in (self.prediction.currentIndex(), self.prediction_b.currentIndex()) if i)
        self._candidates.append(Candidate(label.strip(), self._region(), models=models))
        self._refresh_candidates()
        self.candidates.setCurrentIndex(len(self._candidates) - 1)
        self._set_enabled()

    def _remove_annotation(self):
        index = self.candidates.currentIndex()
        if index >= 0:
            self._candidates.pop(index)
            self._refresh_candidates()
            self._set_enabled()

    def _review_candidate(self):
        index = self.candidates.currentIndex()
        if index >= 0:
            revised = edit_candidate(self, self._candidates[index])
            if revised is not None:
                self._candidates[index] = revised

    def _gallery(self):
        index = candidate_gallery(self, self._comparison, self._candidates,
                                  self.candidates.currentIndex())
        if index is not None:
            candidate = self._candidates[index]
            self.candidates.setCurrentIndex(index)
            self._select_candidate(index)
            if candidate.models:
                self._updating = True
                self.prediction.setCurrentIndex(candidate.models[0])
                self.prediction_b.setCurrentIndex(candidate.models[1] if len(candidate.models) == 2 else 0)
                self._updating = False
                self._update_visibility()
            bounds = roi_coordinates(self._comparison, candidate.roi)
            centre = tuple((a+b)/2-s/2 for a, b, s in zip(
                bounds["start_um_vu"], bounds["stop_um_vu"], self._comparison.pixel_size_um_vu))
            self.viewer.camera.center = centre

    def _agreement(self):
        if self._worker is not None:
            return
        view = self._view()
        thresholds = sorted({20, 35, 50, 65, 80, view.threshold})
        self._worker = thread_worker(inspect_pair, ignore_errors=True)(
            self._comparison, view.models, view.roi, thresholds)
        self._worker.returned.connect(lambda report: agreement_dialog(self, report))
        self._worker.errored.connect(self._error)
        self._worker.finished.connect(self._finished)
        self._set_enabled()
        self._worker.start()

    def _propose(self):
        view = self._view()
        self._worker = thread_worker(propose_candidates, ignore_errors=True)(
            self._comparison, view.models, view.roi, min(128, *view.roi[2:]))
        self._worker.returned.connect(self._add_proposals)
        self._worker.errored.connect(self._error)
        self._worker.finished.connect(self._finished)
        self._set_enabled()
        self._worker.start()

    def _factorial(self):
        self._worker = thread_worker(prepare_factorial, ignore_errors=True)(self._comparison, self._region())
        self._worker.returned.connect(lambda previews: factorial_dialog(self, previews))
        self._worker.errored.connect(self._error)
        self._worker.finished.connect(self._finished)
        self._set_enabled()
        self._worker.start()

    def _add_proposals(self, proposals):
        existing = {(candidate.roi, candidate.models) for candidate in self._candidates}
        selected = [candidate for candidate in proposals if (candidate.roi, candidate.models) not in existing]
        count = min(len(selected), MAX_CANDIDATES-len(self._candidates))
        self._candidates.extend(selected[:count])
        self._refresh_candidates()
        self.status.setText(f"Régions ajoutées par le protocole de rang · {count}")

    def _view(self):
        return ComparisonView(self.reference.currentIndex(),
                              (self.prediction.currentIndex(), self.prediction_b.currentIndex()),
                              self.threshold.value(), self.opacity.value(),
                              self.disagreement.isChecked(), self._region(),
                              tuple(self._candidates), MODES[self.analysis.currentIndex()])

    def _save(self):
        self._write("Enregistrer la session", "Session JSON (*.json)", ".json",
                    save_comparison_session)

    def _export(self):
        self._write("Exporter la région", "Image PNG (*.png)", ".png", export_comparison_png)

    def _export_examination(self):
        self._write("Exporter le dossier d’examen", "Archive ZIP (*.zip)", ".zip", export_examination)

    def _write(self, title, file_filter, suffix, writer):
        name, _ = QFileDialog.getSaveFileName(self, title, filter=file_filter)
        if not name:
            return
        path = Path(name)
        if path.suffix.lower() != suffix:
            path = path.with_name(path.name + suffix)
        self._worker = thread_worker(writer, ignore_errors=True)(path, self._comparison, self._view())
        self._worker.returned.connect(lambda _: self.status.setText(f"Fichier enregistré · {path.name}"))
        self._worker.errored.connect(self._error)
        self._worker.finished.connect(self._finished)
        self._set_enabled()
        self._worker.start()
