"""Validation controls for the existing comparison panel."""

import json

import numpy as np
from napari.qt.threading import thread_worker
from qtpy.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..core.multimodal import export_multimodal, load_multimodal

NAMES = {"ct": "CT · coupe 59", "surface": "Surface déroulée", "height": "Relief optique (µm)",
         "brightfield": "Photographie optique", "ink_mask": "Annotation d’encre",
         "a_plus": "Score A+", "a_minus": "Score A−", "uncertainty": "Incertitude géométrique (µm)"}


def show_layers(viewer, result):
    data, ct, optical, images, report = result
    optical_x = ct.origin[1] + ct.shape[1]*ct.pitch[1] + 200
    offsets = (optical.origin[0], optical_x)
    linked = "registered_height" in images
    sensitivity = []
    for name, pixels in images.items():
        key = name.removeprefix("registered_")
        native = name in ("height", "brightfield", "ink_mask")
        blind = key in ("ink_mask", "a_plus", "a_minus")
        base = key in ("ct", "brightfield") and not name.startswith("registered_")
        grid = optical if native else ct
        limits = {}
        if key == "height":
            finite = pixels[np.isfinite(pixels)]
            if finite.size:
                lo, hi = np.quantile(finite, [.01,.99])
                limits = {"contrast_limits": (float(lo), float(max(hi, lo+1e-6)))}
        if key in ("a_plus", "a_minus"):
            limits = {"contrast_limits": (0,1), "opacity": .6,
                      "colormap": "magma" if key == "a_plus" else "cyan"}
        title = NAMES[key] + (" · recalée" if name.startswith("registered_") else "")
        if native and not linked:
            title += " · repère séparé"
        if key == "ink_mask":
            layer = viewer.add_labels(np.nan_to_num(pixels).astype("u1"), name=title,
                                      scale=grid.pitch, translate=offsets if native else grid.origin,
                                      visible=False, metadata={"validation_role": name})
        else:
            if key == "brightfield" and not native:
                pixels = np.nan_to_num(pixels / 255).clip(0,1)
            layer = viewer.add_image(pixels, name=title, rgb=(key == "brightfield"),
                                     scale=grid.pitch, translate=offsets if native else grid.origin,
                                     visible=base, metadata={"validation_role": name}, **limits)
        if blind:
            sensitivity.append(layer)
    if report:
        for scope, grid, offset, key in (("CT", ct, ct.origin, "ct_vu"),
                                         ("optique", optical, offsets, "optical_yx")):
            for split, color in (("fit", "orange"), ("check", "cyan")):
                points = [r[key] for r in report["landmarks"] if r["split"] == split]
                viewer.add_points(points, scale=grid.pitch, translate=offset, size=10,
                                  face_color=color, name=f"Repères {scope} · {split}")
    viewer.reset_view()
    return sensitivity


def open_validation(widget):
    path, _ = QFileDialog.getOpenFileName(widget, "Ouvrir un dossier multimodal",
                                          filter="Manifeste JSON (*.json)")
    if not path:
        return
    worker = thread_worker(load_multimodal)(path)
    widget.multimodal_button.setEnabled(False)
    widget.status.setText("Chargement des données CT et optiques…")
    worker.returned.connect(lambda result: _show_dialog(widget, path, result))
    worker.errored.connect(lambda error: widget.status.setText(str(error)))
    worker.finished.connect(lambda: widget.multimodal_button.setEnabled(True))
    widget._multimodal_worker = worker
    worker.start()


def _show_dialog(widget, path, result):
    data, _, _, images, report = result
    blind_layers = show_layers(widget.viewer, result)
    dialog = QDialog(widget)
    dialog.setWindowTitle("Validation CT–optique")
    box = QVBoxLayout(dialog)
    linked = "registered_height" in images
    status = ("Recalage géométrique chargé" if linked else
              "Champ non localisé dans le CT · repères CT et optique distincts")
    text = QLabel(status + "\n" + data["summary_fr"], dialog)
    text.setWordWrap(True)
    box.addWidget(text)
    provenance = QPlainTextEdit(json.dumps({
        "identity": data["identity"], "ct": data["ct"], "optical": data["optical"],
        "files": data["files"], "provenance": data.get("provenance", {}),
    }, indent=2, ensure_ascii=False), dialog)
    provenance.setReadOnly(True)
    provenance.hide()
    show_provenance = QPushButton("Provenance et empreintes", dialog)
    show_provenance.setCheckable(True)
    show_provenance.toggled.connect(provenance.setVisible)
    box.addWidget(show_provenance)
    box.addWidget(provenance)
    blind = QCheckBox("Afficher les annotations d’encre et les prédictions", dialog)
    blind.toggled.connect(lambda state: _visibility(widget.viewer, blind_layers, state))
    box.addWidget(blind)
    if report:
        summary = QLabel(f"Repères réservés · médiane {report['check_median_um']:.2f} µm · "
                         f"RMS {report['check_rms_um']:.2f} µm · seuil {report['limit_um']:.2f} µm")
        box.addWidget(summary)
        table = QTableWidget(len(report["landmarks"]), 4, dialog)
        table.setHorizontalHeaderLabels(("Repère", "Groupe", "Erreur (µm)", "Erreur (px CT)"))
        for row, item in enumerate(report["landmarks"]):
            for col, value in enumerate((item["id"], item["split"], f"{item['error_um']:.2f}",
                                        f"{item['error_ct_px']:.2f}")):
                table.setItem(row,col,QTableWidgetItem(str(value)))
        box.addWidget(table)
    button = QPushButton("Exporter le dossier de validation", dialog)
    button.clicked.connect(lambda: _export(dialog, path, text))
    box.addWidget(button)
    widget.status.setText(status)
    dialog.show()


def _visibility(viewer, layers, visible):
    for layer in layers:
        if layer in viewer.layers:
            layer.visible = visible


def _export(dialog, path, label):
    destination, _ = QFileDialog.getSaveFileName(dialog, "Dossier de validation", "validation.zip", "ZIP (*.zip)")
    if not destination:
        return
    worker = thread_worker(export_multimodal)(path, destination)
    worker.returned.connect(lambda _: label.setText("Dossier exporté"))
    worker.errored.connect(lambda error: label.setText(str(error)))
    dialog._export_worker = worker
    worker.start()
