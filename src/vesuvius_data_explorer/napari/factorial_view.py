"""Small synchronized UV previews of cached checkpoint × order conditions."""

from math import ceil

import numpy as np
from qtpy.QtCore import Qt
from qtpy.QtGui import QImage, QPixmap
from qtpy.QtWidgets import QDialog, QGridLayout, QGroupBox, QLabel, QTabWidget, QVBoxLayout, QWidget

from ..core.comparison import roi_coordinates
from ..core.consensus import _distribution
from ..core.ink_factorial import CONDITIONS, registered_conditions


def prepare_factorial(comparison, roi):
    indexes = registered_conditions(comparison)
    v, u, h, w = roi
    window = np.s_[v:v+h, u:u+w]
    base = comparison.ct.pixels[window]
    stride = max(1, ceil(max(h, w)/180))
    image = base[::stride, ::stride].astype(float)
    usable_ct = base[np.isfinite(base)]
    low, high = (usable_ct.min(), usable_ct.max()) if usable_ct.size else (0, 0)
    gray = np.nan_to_num((image-low)/(high-low), nan=0) if high > low else np.zeros_like(image)
    rgb = np.repeat(gray[..., None], 3, axis=-1)
    models = {condition: comparison.predictions[n-1] for condition, n in indexes.items()}
    planes = {condition: model.image.pixels[window] for condition, model in models.items()}
    support = np.ones((h, w), bool)
    for data in planes.values():
        support &= np.isfinite(data)
    use = int(support.sum())
    prepared = {}
    for condition, data in planes.items():
        model = models[condition]
        weights = np.where(support, data, 0)[::stride, ::stride]/model.score_scale
        mask = np.zeros(data.shape, dtype=bool)
        if use:
            samples = data[support]
            index = use - ceil(use*0.01)
            mask = support & (data >= np.partition(samples, index)[index])
        rows, cols = gray.shape
        padded = np.pad(mask, ((0, rows*stride-h), (0, cols*stride-w)))
        ranked_preview = padded.reshape(rows, stride, cols, stride).any(axis=(1, 3))
        layers = {}
        for kind, alpha in (("scores", weights*.8), ("rank", ranked_preview*.8)):
            alpha = alpha[..., None]
            values = (1-alpha)*rgb + alpha*np.array([0.18, 0.88, 0.80])
            layers[kind] = np.ascontiguousarray(np.rint(values*255), dtype="u1")
        prepared[condition] = {"images": layers, "distribution": _distribution(data[support],
                                                                                  model.score_scale),
                               "top_count": int(mask.sum()), "model": model.model}
    return {"coordinates": roi_coordinates(comparison, roi), "paired_pixels": use, "planes": prepared}


def factorial_dialog(parent, prepared):
    from .ink_review import _table

    dialog = QDialog(parent)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dialog.setWindowTitle("Conditions A+/A−/B+/B−")
    layout = QVBoxLayout(dialog)
    bounds = prepared["coordinates"]
    layout.addWidget(QLabel(f"V/U {bounds['start_vu']} → {bounds['stop_vu']} · "
                            f"{prepared['paired_pixels']:,} pixels appariés"))
    tabs = QTabWidget()
    planes = prepared["planes"]
    for key, title in (("scores", "Scores sur CT"), ("rank", "Top 1 % sur CT")):
        page = QWidget()
        grid = QGridLayout(page)
        for index, cell in enumerate(CONDITIONS):
            group = QGroupBox(cell)
            contents = QVBoxLayout(group)
            if cell not in planes:
                contents.addWidget(QLabel("Condition expérimentale indisponible"))
            else:
                info = planes[cell]
                label = QLabel(info["model"])
                label.setTextFormat(Qt.TextFormat.PlainText)
                label.setWordWrap(True)
                contents.addWidget(label)
                a = info["images"][key]
                view = QImage(a.data, a.shape[1], a.shape[0], a.strides[0], QImage.Format.Format_RGB888)
                image = QLabel()
                image.setPixmap(QPixmap.fromImage(view.copy()))
                contents.addWidget(image)
                if key == "rank":
                    contents.addWidget(QLabel(f"{info['top_count']:,} pixels retenus avec ex æquo"))
            grid.addWidget(group, index//2, index%2)
        tabs.addTab(page, title)
    rows = [(f"{i/20:.2f}–{(i+1)/20:.2f}",
             *(planes[k]["distribution"]["counts"][i] if k in planes else None for k in CONDITIONS))
            for i in range(20)]
    tabs.addTab(_table(("Intervalle", *CONDITIONS), rows), "Histogrammes")
    layout.addWidget(tabs)
    dialog.resize(680, 520)
    dialog.show()
    return dialog
