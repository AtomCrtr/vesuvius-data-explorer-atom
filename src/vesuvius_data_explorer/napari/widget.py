"""Minimal asynchronous volume opener; all data work lives in core/reader."""

from napari.qt.threading import thread_worker
from napari.settings import get_settings
from napari.viewer import Viewer
from qtpy.QtWidgets import (
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .reader import read_volume


class OpenVolumeWidget(QWidget):
    def __init__(self, napari_viewer: Viewer):
        super().__init__()
        self._viewer = napari_viewer
        self._worker = None
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Chemin local ou s3://…/volume.zarr")
        self.open_button = QPushButton("Ouvrir")
        self.summary_table = QTableWidget(0, 6)
        self.summary_table.setHorizontalHeaderLabels(
            ["Niveau", "Forme (z, y, x)", "dtype", "Chunks", "Échelle", "Taille estimée (octets)"]
        )
        self.status_label = QLabel("Indiquer le chemin d'un volume .zarr.")
        self.status_label.setWordWrap(True)
        layout = QVBoxLayout(self)
        for control in (self.path_input, self.open_button, self.summary_table, self.status_label):
            layout.addWidget(control)
        self.open_button.clicked.connect(self._open)

    def _open(self):
        # Napari otherwise performs viewport Dask computations on the GUI thread.
        # This public preference also updates already-open viewers.
        get_settings().experimental.async_ = True
        self.open_button.setEnabled(False)
        self.status_label.setText("Ouverture en cours…")
        # Both metadata I/O and the bounded contrast sample run off the GUI thread.
        self._worker = thread_worker(read_volume, ignore_errors=True)(self.path_input.text())
        self._worker.returned.connect(self._loaded)
        self._worker.errored.connect(self._error)
        self._worker.finished.connect(lambda: self.open_button.setEnabled(True))
        self._worker.start()

    def _loaded(self, layer_data):
        try:
            [(arrays, options, _)] = layer_data
            self._viewer.add_image(arrays, **options)
            summary = options["metadata"]["volume_summary"]
            self.summary_table.setRowCount(summary["level_count"])
            keys = ("key", "shape", "dtype", "chunks", "scale", "estimated_bytes")
            for row, level in enumerate(summary["levels"]):
                for column, key in enumerate(keys):
                    self.summary_table.setItem(row, column, QTableWidgetItem(str(level[key])))
            self.summary_table.resizeColumnsToContents()
            self.status_label.setText("Volume ouvert.")
        except Exception as error:
            self._error(error)

    def _error(self, error):
        # Only our French domain errors are safe to show verbatim. Storage/backend
        # failures may contain English internals or Python representations.
        message = str(error)
        if isinstance(error, (ValueError, FileNotFoundError)) and message.startswith(
            (
                "Indiquer",
                "Utiliser",
                "Volume introuvable",
                "Aucun tableau",
                "Le tableau",
                "Ordre des axes",
            )
        ):
            self.status_label.setText(message)
        else:
            self.status_label.setText(
                "Impossible d'ouvrir le volume. Vérifier le chemin, le format OME-Zarr "
                "et l'accès au stockage ou au réseau."
            )
