"""Qt views for descriptive agreement and reviews of UV observations."""

import json
from dataclasses import replace
from math import ceil

import numpy as np
from qtpy.QtCore import Qt
from qtpy.QtGui import QImage, QPixmap
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.comparison import CONFIDENCE_LEVELS, roi_coordinates
from ..core.ink_exam import candidate_id, review_stage

STAGE_LABELS = {
    "a_examiner": "À examiner",
    "trace_observee": "Trace observée",
    "encre_candidate": "Encre candidate",
    "caractere_hypothetique": "Caractère hypothétique",
    "caractere_valide_par_expertise": "Caractère validé par expertise",
}


def _table(columns, rows):
    table = QTableWidget(len(rows), len(columns))
    table.setHorizontalHeaderLabels(columns)
    for row, values in enumerate(rows):
        for col, value in enumerate(values):
            label = "—" if value is None else f"{value:.4f}" if isinstance(value, float) else str(value)
            table.setItem(row, col, QTableWidgetItem(label))
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.resizeColumnsToContents()
    return table


def agreement_dialog(parent, report):
    dialog = QDialog(parent)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dialog.setWindowTitle("Accord descriptif des cartes")
    layout = QVBoxLayout(dialog)
    coord = report["coordinates"]
    layout.addWidget(QLabel(f"{report['paired_pixels']:,} pixels communs · "
                            f"{report['missing_pixels']:,} manquants · "
                            f"V/U {coord['start_vu']} → {coord['stop_vu']}"))
    models = QLabel(f"A · {report['models'][0]['model']}\nB · {report['models'][1]['model']}")
    models.setTextFormat(Qt.TextFormat.PlainText)
    layout.addWidget(models)
    tabs = QTabWidget()
    columns = ("Seuil A/B %", "A et B", "A seule", "B seule", "Sous seuil", "Proches",
               "Jaccard", "Dice", "Désaccord")
    tabs.addTab(_table(columns, [
        ("/".join(map(str, row["thresholds_percent"])), row["both_positive"], row["a_only"],
         row["b_only"], row["both_below"], row["uncertain_pixels"], row["jaccard"],
         row["dice"], row["disagreement_rate"]) for row in report["thresholds"]]), "Seuils")
    tabs.addTab(_table(("Rang %", "A retenus", "B retenus", "En commun", "Jaccard", "Dice"), [
        (row["fraction"] * 100, row["a_selected"], row["b_selected"], row["both_positive"],
         row["jaccard"], row["dice"]) for row in report["rank_agreement"]]), "Rangs")
    a, b = report["score_distributions"]
    bins = a["normalized_bin_edges"]
    tabs.addTab(_table(("Intervalle du score normalisé", "Pixels A", "Pixels B"), [
        (f"{left:.2f}–{right:.2f}", ca, cb)
        for left, right, ca, cb in zip(bins, bins[1:], a["counts"], b["counts"])]), "Distribution")
    provenance = QPlainTextEdit(json.dumps({"surface": report.get("surface"), "models": report["models"]},
                                          indent=2, ensure_ascii=False))
    provenance.setReadOnly(True)
    tabs.addTab(provenance, "Provenance")
    layout.addWidget(tabs)
    r = report["correlations"]
    values = " · ".join(f"{name} {r[name.lower()]:.4f}" if r[name.lower()] is not None else f"{name} —"
                        for name in ("Pearson", "Spearman"))
    layout.addWidget(QLabel(values))
    sensitivity = report.get("z_sensitivity")
    if sensitivity and sensitivity["estimate"] is not None:
        bounds = sensitivity["interval_95"]
        suffix = (f" · intervalle 95 % [{bounds[0]:.3f}, {bounds[1]:.3f}]" if bounds else
                  " · support insuffisant pour un intervalle")
        layout.addWidget(QLabel(f"Écart Z absolu moyen {sensitivity['estimate']:.3f}{suffix}"))
    context = ("Écart absolu moyen de probabilité déclarée "
               f"{report['probability_differences']['mean_absolute_difference']:.4f}"
               if report["probability_differences"] is not None else
               "Seuils et distributions sur les échelles de score propres à chaque carte.")
    layout.addWidget(QLabel(context))
    dialog.resize(820, 400)
    dialog.show()


def edit_candidate(parent, candidate):
    dialog = QDialog(parent)
    dialog.setWindowTitle("Documenter l’observation")
    form = QFormLayout(dialog)
    fields = {}
    for key, name in (
        ("observation", "Traces visibles"), ("hypothesis", "Hypothèse de caractère"),
        ("comment", "Commentaire paléographique"), ("reviewer", "Expert ou experte"),
        ("evidence", "Référence indépendante de validation"),
        ("palaeography_reference", "Référence paléographique (DOI, page ou cote)"),
    ):
        fields[key] = QLineEdit(getattr(candidate, key))
        fields[key].setMaxLength(240)
        form.addRow(name, fields[key])
    ink = QCheckBox("Région compatible avec de l’encre")
    ink.setChecked(candidate.ink_candidate)
    form.addRow(ink)
    confirmed = QCheckBox("Lecture confirmée par expertise indépendante")
    confirmed.setChecked(candidate.character_confirmed)
    form.addRow(confirmed)
    confidence = QComboBox()
    confidence.addItems(["Non évaluée", "Faible", "Moyenne", "Haute"])
    confidence.setCurrentIndex(CONFIDENCE_LEVELS.index(candidate.confidence))
    form.addRow("Confiance de l’observation", confidence)
    message = QLabel()
    message.setWordWrap(True)
    form.addRow(message)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)

    def accept():
        if bool(fields["reviewer"].text().strip()) != bool(fields["evidence"].text().strip()):
            message.setText("La validation externe requiert une personne et une référence indépendante.")
            return
        if confirmed.isChecked() and not (ink.isChecked() and all(fields[key].text().strip() for key in
                ("observation", "hypothesis", "reviewer", "evidence", "palaeography_reference"))):
            message.setText("Renseigner l’observation, l’hypothèse, l’expertise et les deux références.")
            return
        dialog.accept()

    buttons.accepted.connect(accept)
    buttons.rejected.connect(dialog.reject)
    form.addRow(buttons)
    if not dialog.exec():
        return None
    return replace(candidate, confidence=CONFIDENCE_LEVELS[confidence.currentIndex()],
                   ink_candidate=ink.isChecked(), character_confirmed=confirmed.isChecked(),
                   **{key: field.text().strip() for key, field in fields.items()})


def _thumbnail(pixels, roi, score_scale=None):
    v, u, h, w = roi
    stride = max(1, ceil(max(h, w)/128))
    data = pixels[v:v+h:stride, u:u+w:stride].astype(float)
    finite = data[np.isfinite(data)]
    if score_scale is not None:
        data = np.nan_to_num(data / score_scale)
    elif finite.size and finite.max() > finite.min():
        data = np.nan_to_num((data-finite.min()) / (finite.max()-finite.min()))
    else:
        data.fill(0)
    gray = np.ascontiguousarray(np.rint(255*data).astype(np.uint8))
    rows, cols = gray.shape
    image = QImage(gray.data, cols, rows, gray.strides[0], QImage.Format.Format_Grayscale8)
    return QPixmap.fromImage(image.copy())


def candidate_gallery(parent, comparison, candidates, selected):
    dialog = QDialog(parent)
    dialog.setWindowTitle("Galerie des observations UV")
    layout = QHBoxLayout(dialog)
    listing = QListWidget()
    listing.addItems([item.label for item in candidates])
    layout.addWidget(listing)
    right = QVBoxLayout()
    layout.addLayout(right)
    previews = QWidget()
    images = QHBoxLayout(previews)
    right.addWidget(previews)
    details = QLabel()
    details.setTextFormat(Qt.TextFormat.PlainText)
    details.setWordWrap(True)
    right.addWidget(details)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Close)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    right.addWidget(buttons)

    def show(index):
        if index < 0:
            return
        item = candidates[index]
        while images.count():
            images.takeAt(0).widget().deleteLater()
        planes = [("CT", comparison.ct, None), ("Surface UV", comparison.surface, None)]
        planes += [(model.model, model.image, model.score_scale)
                   for model in (comparison.predictions[i-1] for i in item.models)]
        for title, plane, score_scale in planes:
            panel = QWidget()
            column = QVBoxLayout(panel)
            name = QLabel(title)
            name.setTextFormat(Qt.TextFormat.PlainText)
            name.setWordWrap(True)
            image = QLabel()
            image.setPixmap(_thumbnail(plane.pixels, item.roi, score_scale))
            column.addWidget(name)
            column.addWidget(image)
            images.addWidget(panel)
        bounds = roi_coordinates(comparison, item.roi)
        description = STAGE_LABELS[review_stage(item)]
        confidence = ("non évaluée", "faible", "moyenne", "haute")[
            CONFIDENCE_LEVELS.index(item.confidence)]
        details.setText(f"V/U {bounds['start_vu']} → {bounds['stop_vu']} · {description}"
                        f"\nIdentifiant · {candidate_id(comparison, item)}"
                        f"\nSélection · {item.selection or 'Manuelle'}"
                        f"\nConfiance · {confidence}"
                        f"\nObservation · {item.observation or '—'}"
                        f"\nHypothèse · {item.hypothesis or '—'}"
                        f"\nCommentaire · {item.comment or '—'}"
                        f"\nRéférence paléographique · {item.palaeography_reference or '—'}"
                        f"\nRelecture · {item.reviewer or '—'}"
                        f"\nRéférence · {item.evidence or '—'}")

    listing.currentRowChanged.connect(show)
    listing.setCurrentRow(max(0, selected))
    dialog.resize(820, 380)
    return listing.currentRow() if dialog.exec() else None
