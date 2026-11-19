"""Compare registered UV products without running inference or changing source files."""

import numpy as np
from napari.qt.threading import create_worker
from napari.utils import Colormap
from qtpy.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QWidget,
)

from ..core.comparison import load_comparison


class ComparisonWidget(QWidget):
    def __init__(self, napari_viewer):
        super().__init__()
        self.viewer = napari_viewer
        self._worker = None
        self._planes = []
        self._predictions = []
        self.open_button = QPushButton("Ouvrir un manifeste de comparaison")
        self.reference = QComboBox()
        self.reference.addItems(["CT projeté", "Surface déroulée"])
        self.prediction = QComboBox()
        self.threshold = QSpinBox()
        self.threshold.setRange(1, 99)
        self.threshold.setValue(50)
        self.threshold.setSuffix(" %")
        self.status = QLabel()
        self.status.setWordWrap(True)
        form = QFormLayout(self)
        form.addRow(self.open_button)
        form.addRow("Fond", self.reference)
        form.addRow("Superposition", self.prediction)
        form.addRow("Seuil d’affichage", self.threshold)
        form.addRow(self.status)
        self.open_button.clicked.connect(self._choose)
        self.reference.currentIndexChanged.connect(self._update_visibility)
        self.prediction.currentIndexChanged.connect(self._update_visibility)
        self.threshold.valueChanged.connect(self._update_threshold)

    def _choose(self):
        path, _ = QFileDialog.getOpenFileName(self, "Comparer des prédictions",
                                              filter="Manifeste JSON (*.json)")
        if path:
            self.load(path)

    def load(self, path):
        if self._worker is not None:
            return
        self.open_button.setEnabled(False)
        self.status.setText("Chargement des plans UV…")
        self._worker = create_worker(load_comparison, path)
        self._worker.returned.connect(self._show)
        self._worker.errored.connect(self._error)
        self._worker.finished.connect(self._finished)
        self._worker.start()

    def _finished(self):
        self._worker = None
        self.open_button.setEnabled(True)

    def _error(self, error):
        self.status.setText(f"Comparaison indisponible. {error}")

    def _colormap(self):
        return Colormap([(0, 0, 0, 0), (1, 0.32, 0.12, 0.8)],
                        controls=[0, self.threshold.value() / 100, 1], interpolation="zero")

    def _show(self, comparison):
        for layer in (*self._planes, *self._predictions):
            if layer in self.viewer.layers:
                self.viewer.layers.remove(layer)
        self._planes.clear()
        self._predictions.clear()
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
        self.prediction.blockSignals(True)
        self.prediction.clear()
        self.prediction.addItem("Aucune")
        for prediction in comparison.predictions:
            # Display-only copy. Missing scores display as transparent; source bytes stay intact.
            pixels = np.nan_to_num(prediction.image.pixels, nan=0.0)
            layer = self.viewer.add_image(
                pixels, name=prediction.name, rgb=False, scale=scale, translate=translate,
                visible=False, colormap=self._colormap(), contrast_limits=(0, prediction.score_scale),
                blending="translucent_no_depth",
                metadata={**metadata, "source": str(prediction.image.path), "model": prediction.model,
                          "score_scale": prediction.score_scale},
            )
            self._predictions.append(layer)
            self.prediction.addItem(prediction.name)
        self.prediction.setCurrentIndex(1)
        self.prediction.blockSignals(False)
        self._update_visibility()
        self.status.setText(f"{comparison.segment_id} · {comparison.surface_revision}")

    def _update_visibility(self):
        for index, layer in enumerate(self._planes):
            layer.visible = index == self.reference.currentIndex()
        for index, layer in enumerate(self._predictions, start=1):
            layer.visible = index == self.prediction.currentIndex()

    def _update_threshold(self):
        colormap = self._colormap()
        for layer in self._predictions:
            layer.colormap = colormap
