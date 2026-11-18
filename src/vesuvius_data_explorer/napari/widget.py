"""Asynchronous volume opener, with a picker fed by the official catalogue.

All data work lives in core/reader; this module only wires widgets and workers.
"""

from dataclasses import asdict

from napari.qt.threading import thread_worker
from napari.settings import get_settings
from napari.viewer import Viewer
from qtpy.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vesuvius_data_explorer.core.cache import (
    cache_enabled,
    cache_size,
    chunk_cache_root,
    clear_cache,
)
from vesuvius_data_explorer.core.catalog import Catalog, CatalogVolume, format_um, load_catalog

from .reader import read_volume


def _async_enabled() -> bool:
    return bool(get_settings().experimental.async_)


class OpenVolumeWidget(QWidget):
    def __init__(self, napari_viewer: Viewer):
        super().__init__()
        self._viewer = napari_viewer
        self._worker = None
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Chemin local ou s3://…/volume.zarr")
        self.open_button = QPushButton("Ouvrir")
        self.async_button = QPushButton("Activer le chargement asynchrone (préférence napari)")
        self.summary_table = QTableWidget(0, 6)
        self.summary_table.setHorizontalHeaderLabels(
            ["Niveau", "Forme (z, y, x)", "dtype", "Chunks", "Échelle", "Taille estimée (octets)"]
        )
        self.status_label = QLabel("Indiquer le chemin d'un volume .zarr.")
        self.status_label.setWordWrap(True)
        self.cache_button = QPushButton()
        self._cache_worker = None
        layout = QVBoxLayout(self)
        layout.addWidget(self._catalog_box())
        controls = (
            self.path_input,
            self.open_button,
            self.async_button,
            self.summary_table,
            self.status_label,
            self.cache_button,
        )
        for control in controls:
            layout.addWidget(control)
        self.open_button.clicked.connect(self._open)
        self.async_button.clicked.connect(self._enable_async)
        self.async_button.setVisible(not _async_enabled())
        self.cache_button.clicked.connect(self._clear_cache)
        self._show_cache_size()

    # --- Local chunk cache (T6) -----------------------------------------------------------

    def _show_cache_size(self):
        if not cache_enabled():
            self.cache_button.setText("Cache local désactivé (VESUVIUS_CACHE=0)")
            self.cache_button.setEnabled(False)
            return
        self.cache_button.setText(f"Vider le cache local ({format_size(cache_size())})")
        self.cache_button.setToolTip(str(chunk_cache_root()))
        self.cache_button.setEnabled(True)

    def _clear_cache(self):
        self.cache_button.setEnabled(False)
        self._cache_worker = thread_worker(clear_cache, ignore_errors=True)()
        self._cache_worker.returned.connect(self._cache_cleared)
        self._cache_worker.errored.connect(
            lambda error: self.status_label.setText("Impossible de vider le cache local."))
        self._cache_worker.finished.connect(self._show_cache_size)
        self._cache_worker.start()

    def _cache_cleared(self, freed):
        self.status_label.setText(f"Cache local vidé : {format_size(freed)} libérés.")

    # --- Official catalogue -------------------------------------------------------------

    def _catalog_box(self) -> QGroupBox:
        self._catalog: Catalog | None = None
        self._catalog_worker = None
        self.catalog_button = QPushButton("Charger le catalogue officiel")
        self.sample_combo = QComboBox()
        self.volume_combo = QComboBox()
        self.volume_info = QLabel("Catalogue non chargé.")
        self.volume_info.setWordWrap(True)
        for combo in (self.sample_combo, self.volume_combo):
            combo.setEnabled(False)
        box = QGroupBox("Catalogue officiel (Vesuvius Atlas)")
        form = QFormLayout(box)
        form.addRow(self.catalog_button)
        form.addRow("Échantillon", self.sample_combo)
        form.addRow("Volume", self.volume_combo)
        form.addRow(self.volume_info)
        self.catalog_button.clicked.connect(self._load_catalog)
        self.sample_combo.currentIndexChanged.connect(self._sample_changed)
        self.volume_combo.currentIndexChanged.connect(self._volume_changed)
        return box

    def _load_catalog(self):
        self.catalog_button.setEnabled(False)
        self.volume_info.setText("Chargement du catalogue…")
        # About 9 MB on the first call, then a local cache: never on the GUI thread.
        self._catalog_worker = thread_worker(load_catalog, ignore_errors=True)(
            refresh=self._catalog is not None
        )
        self._catalog_worker.returned.connect(self._catalog_loaded)
        self._catalog_worker.errored.connect(self._catalog_error)
        self._catalog_worker.finished.connect(lambda: self.catalog_button.setEnabled(True))
        self._catalog_worker.start()

    def _catalog_loaded(self, catalog: Catalog):
        self._catalog = catalog
        self.catalog_button.setText("Actualiser le catalogue")
        self.sample_combo.blockSignals(True)
        self.sample_combo.clear()
        self.sample_combo.addItems(catalog.samples())
        self.sample_combo.blockSignals(False)
        self.sample_combo.setEnabled(bool(catalog.volumes))
        self._sample_changed()
        if catalog.stale:
            self.volume_info.setText(
                "Réseau indisponible : copie locale plus ancienne du catalogue utilisée. "
                + self.volume_info.text()
            )

    def _catalog_error(self, error):
        message = str(error)
        if not isinstance(error, (ConnectionError, ValueError)) or not message.startswith(
            "Catalogue"
        ):
            message = "Catalogue officiel inaccessible ou illisible."
        self.volume_info.setText(message)

    def _sample_changed(self, *_):
        self.volume_combo.blockSignals(True)
        self.volume_combo.clear()
        if self._catalog is not None:
            for volume in self._catalog.volumes_of(self.sample_combo.currentText()):
                self.volume_combo.addItem(volume.label, volume)
        self.volume_combo.blockSignals(False)
        self.volume_combo.setEnabled(self.volume_combo.count() > 0)
        self._volume_changed()

    def _volume_changed(self, *_):
        volume = self.volume_combo.currentData()
        if volume is None:
            self.volume_info.setText("Aucun volume ouvrable pour cet échantillon.")
            return
        self.path_input.setText(volume.uri)
        self.volume_combo.setToolTip(volume.label)  # The dock is often narrower than the label.
        self.volume_info.setText(describe_volume(volume))

    def _catalog_entry(self, source: str) -> CatalogVolume | None:
        return self._catalog.find(source) if self._catalog is not None else None

    def _enable_async(self):
        # Explicit user action: napari saves this preference for later sessions.
        get_settings().experimental.async_ = True
        self.async_button.setVisible(False)
        self.status_label.setText(
            "Chargement asynchrone activé (préférence napari enregistrée). Cliquer sur Ouvrir."
        )

    def _open(self):
        # Without napari's async preference, viewport Dask computations (S3 reads) run on
        # the GUI thread and freeze it. The preference is global and persisted, so the
        # plugin never changes it silently: it asks, and reads nothing until enabled.
        if not _async_enabled():
            self.async_button.setVisible(True)
            self.status_label.setText(
                "Le chargement asynchrone de napari est désactivé : sans lui, la navigation "
                "dans le volume bloquerait l'interface. Cliquer sur « Activer le chargement "
                "asynchrone » (préférence napari conservée pour les sessions suivantes)."
            )
            return
        self.open_button.setEnabled(False)
        self.status_label.setText("Ouverture en cours…")
        # Both metadata I/O and the bounded contrast sample run off the GUI thread.
        self._worker = thread_worker(read_volume, ignore_errors=True)(self.path_input.text())
        self._worker.returned.connect(self._loaded)
        self._worker.errored.connect(self._error)
        self._worker.finished.connect(lambda: self.open_button.setEnabled(True))
        self._worker.start()

    def _loaded(self, layer_data):
        # The preference may have been turned off while the metadata were loading: adding
        # the layer now would run viewport reads on the GUI thread and freeze it.
        if not _async_enabled():
            self.async_button.setVisible(True)
            self.status_label.setText(
                "Le chargement asynchrone de napari a été désactivé pendant l'ouverture : volume "
                "non ajouté. Le réactiver, puis cliquer à nouveau sur Ouvrir."
            )
            return
        try:
            [(arrays, options, _)] = layer_data
            entry = self._catalog_entry(options["metadata"]["source"])
            if entry is not None:
                # Physical voxel size comes from the catalogue only (OME scales are 1).
                options["metadata"]["catalog"] = asdict(entry)
                options["metadata"]["pixel_size_um"] = entry.pixel_size_um
            self._viewer.add_image(arrays, **options)
            summary = options["metadata"]["volume_summary"]
            self.summary_table.setRowCount(summary["level_count"])
            keys = ("key", "shape", "dtype", "chunks", "scale", "estimated_bytes")
            for row, level in enumerate(summary["levels"]):
                for column, key in enumerate(keys):
                    self.summary_table.setItem(row, column, QTableWidgetItem(str(level[key])))
            self.summary_table.resizeColumnsToContents()
            self.status_label.setText(opened_message(entry, summary))
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
                "Codec de compression",
            )
        ):
            self.status_label.setText(message)
        else:
            self.status_label.setText(
                "Impossible d'ouvrir le volume. Vérifier le chemin, le format OME-Zarr "
                "et l'accès au stockage ou au réseau."
            )


def describe_volume(volume: CatalogVolume) -> str:
    """French description of a catalogue entry, shown before opening."""
    lines = [volume.name]
    if volume.pixel_size_um is not None:
        lines.append(f"Taille de voxel : {format_um(volume.pixel_size_um)} µm")
    shape = f"{volume.shape}" if volume.shape else "inconnue"
    lines.append(f"Forme (z, y, x) : {shape} — {volume.dtype or 'type inconnu'}")
    if volume.license:
        lines.append(f"Licence : {volume.license}")
    if volume.codec == "vc-delta3d":
        lines.append(
            "Codec vc-delta3d : extra requis, pip install 'vesuvius-data-explorer[vcdelta3d]' "
            "(Python 3.12 ou plus)."
        )
    if volume.superseded_by:
        lines.append(f"Remplacé par le volume {volume.superseded_by}.")
    return "\n".join(lines)


def opened_message(entry: CatalogVolume | None, summary: dict) -> str:
    if entry is None:
        return "Volume ouvert."
    message = "Volume ouvert"
    if entry.pixel_size_um is not None:
        message += f" ; taille de voxel {format_um(entry.pixel_size_um)} µm (catalogue officiel)"
    message += "."
    level0 = tuple(summary["levels"][0]["shape"]) if summary["levels"] else None
    if entry.shape is not None and level0 is not None and tuple(entry.shape) != level0:
        message += (
            f" Attention : forme du niveau 0 {level0} différente de celle du catalogue "
            f"{tuple(entry.shape)}."
        )
    return message


def format_size(count: int) -> str:
    """French size: '0 Mio', '151 Mio', '2,4 Gio'."""
    if count >= 2**30:
        return f"{count / 2**30:.1f} Gio".replace(".", ",")
    return f"{count / 2**20:.0f} Mio"
