import numpy as np
import pytest

pytest.importorskip("napari")
pytest.importorskip("qtpy")

from test_comparison import comparison_fixture  # noqa: E402,F401

from vesuvius_data_explorer.napari.comparison_widget import ComparisonWidget  # noqa: E402


def test_registered_layers_and_display_threshold(make_napari_viewer, qtbot, comparison_manifest):
    viewer = make_napari_viewer()
    widget = ComparisonWidget(viewer)
    qtbot.addWidget(widget)
    source = comparison_manifest.parent / "reader.tif"
    original = source.read_bytes()
    widget.load(str(comparison_manifest))
    qtbot.waitUntil(lambda: widget.open_button.isEnabled(), timeout=5000)
    assert len(viewer.layers) == 4, widget.status.text()
    ct, surface, reader, other = viewer.layers
    assert [layer.visible for layer in viewer.layers] == [True, False, True, False]
    assert reader.metadata["model"] == "Reader V3"
    assert tuple(reader.scale) == tuple(ct.scale) == (8.64, 9.1)
    np.testing.assert_allclose(reader.translate, (13 * 8.64, 29 * 9.1))
    data = reader.data.copy()
    widget.threshold.setValue(80)
    assert np.allclose(reader.colormap.controls, [0.0, 0.8, 1.0])
    assert reader.colormap.map([0.79, 0.81])[0, 3] == 0
    assert reader.colormap.map([0.79, 0.81])[1, 3] > 0
    np.testing.assert_array_equal(reader.data, data)
    assert source.read_bytes() == original
    widget.reference.setCurrentIndex(1)
    widget.prediction.setCurrentIndex(2)
    assert [layer.visible for layer in (ct, surface, reader, other)] == [False, True, False, True]


def test_overlay_disagreement_and_candidate_roi(
    make_napari_viewer, qtbot, comparison_manifest, monkeypatch
):
    from qtpy.QtWidgets import QInputDialog

    viewer = make_napari_viewer()
    widget = ComparisonWidget(viewer)
    qtbot.addWidget(widget)
    widget.load(str(comparison_manifest))
    qtbot.waitUntil(widget.open_button.isEnabled, timeout=5000)
    widget.prediction.setCurrentIndex(2)
    widget.prediction_b.setCurrentIndex(1)
    widget.opacity.setValue(35)
    assert viewer.layers["Reader"].visible and viewer.layers["Autre"].visible
    assert viewer.layers.index("Autre") < viewer.layers.index("Reader")
    assert viewer.layers["Reader"].opacity == pytest.approx(0.35)
    widget.disagreement.setChecked(True)
    qtbot.waitUntil(lambda: widget._analysis_worker is None, timeout=5000)
    discrepancy = viewer.layers["Désaccord au seuil"]
    assert discrepancy.visible and not viewer.layers["Reader"].visible
    assert discrepancy.opacity == pytest.approx(0.35)
    assert tuple(discrepancy.scale) == (8.64, 9.1)

    widget.roi[0].setValue(1)
    widget.roi[1].setValue(2)
    widget.roi[2].setValue(2)
    widget.roi[3].setValue(2)
    monkeypatch.setattr(QInputDialog, "getText", lambda *_: ("α ?", True))
    widget.add_candidate.click()
    assert "V 14, U 31" in widget.candidates.currentText()
    assert widget._view().candidates[0].roi == (1, 2, 2, 2)
    widget.remove_candidate.click()
    assert not widget._view().candidates


def test_obsolete_analysis_is_ignored(make_napari_viewer, qtbot, comparison_manifest, monkeypatch):
    import threading

    from vesuvius_data_explorer.napari import comparison_widget

    viewer = make_napari_viewer()
    widget = ComparisonWidget(viewer)
    qtbot.addWidget(widget)
    widget.load(str(comparison_manifest))
    qtbot.waitUntil(widget.open_button.isEnabled, timeout=5000)
    widget.prediction_b.setCurrentIndex(2)
    started, release = threading.Event(), threading.Event()
    apply = comparison_widget._analysis_pixels
    calls = []

    def slow(*args):
        calls.append((args[-1], threading.get_ident()))
        if len(calls) == 1:
            started.set()
            assert release.wait(10)
        return apply(*args)

    monkeypatch.setattr(comparison_widget, "_analysis_pixels", slow)
    widget.disagreement.setChecked(True)
    try:
        qtbot.waitUntil(started.is_set, timeout=5000)
        widget.analysis.setCurrentIndex(1)
        widget.analysis.setCurrentIndex(2)
        assert widget._disagreement is None
    finally:
        release.set()
    qtbot.waitUntil(lambda: widget._analysis_worker is None, timeout=5000)
    assert [mode for mode, _ in calls] == ["disagreement", "consensus"]
    assert all(thread != threading.get_ident() for _, thread in calls)
    assert widget._disagreement.metadata["mode"] == "consensus"
    assert widget._disagreement.data.dtype == np.uint8


def test_agreement_dialog_and_gallery(make_napari_viewer, qtbot, comparison_manifest, monkeypatch):
    from qtpy.QtCore import QTimer
    from qtpy.QtWidgets import QDialog, QInputDialog, QLabel, QTabWidget

    viewer = make_napari_viewer()
    widget = ComparisonWidget(viewer)
    qtbot.addWidget(widget)
    widget.load(str(comparison_manifest))
    qtbot.waitUntil(widget.open_button.isEnabled, timeout=5000)
    widget.prediction_b.setCurrentIndex(2)
    widget.analysis.setCurrentIndex(3)
    qtbot.waitUntil(lambda: widget._analysis_worker is None, timeout=5000)
    assert widget._disagreement.metadata["mode"] == "uncertainty"
    widget.agreement_button.click()
    qtbot.waitUntil(lambda: bool(widget.findChildren(QTabWidget)), timeout=5000)
    tabs = widget.findChild(QTabWidget)
    assert tabs.count() == 4 and tabs.tabText(3) == "Provenance"
    widget.findChild(QDialog).close()
    qtbot.waitUntil(lambda: not widget.findChildren(QDialog), timeout=5000)
    monkeypatch.setattr(QInputDialog, "getText", lambda *_: ("Trace test", True))
    widget.add_candidate.click()
    captured = []

    def open_region():
        dialog = widget.findChild(QDialog)
        captured.extend(label for label in dialog.findChildren(QLabel)
                        if label.pixmap() is not None and not label.pixmap().isNull())
        dialog.accept()

    QTimer.singleShot(0, open_region)
    widget.gallery_button.click()
    assert len(captured) == 4
    assert widget._view().candidates[0].models == (1, 2)


def test_propose_and_export_review(make_napari_viewer, qtbot, comparison_manifest, monkeypatch):
    from qtpy.QtWidgets import QFileDialog

    viewer = make_napari_viewer()
    widget = ComparisonWidget(viewer)
    qtbot.addWidget(widget)
    widget.load(str(comparison_manifest))
    qtbot.waitUntil(widget.open_button.isEnabled, timeout=5000)
    widget.prediction_b.setCurrentIndex(2)
    assert widget.propose_button.isEnabled()
    widget.propose_button.click()
    qtbot.waitUntil(widget.propose_button.isEnabled, timeout=5000)
    proposal, = widget._view().candidates
    assert proposal.selection and not proposal.character_confirmed
    widget.propose_button.click()
    qtbot.waitUntil(widget.propose_button.isEnabled, timeout=5000)
    assert widget._view().candidates == (proposal,)
    path = comparison_manifest.parent / "review.zip"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(path), ""))
    widget.export_exam.click()
    qtbot.waitUntil(lambda: widget.open_button.isEnabled() and path.is_file(), timeout=5000)


@pytest.mark.parametrize("available", [("A+", "A-"), ("A+", "A-", "B+", "B-")])
def test_factorial_dialog_preserves_four_slots_and_common_roi(
    make_napari_viewer, qtbot, comparison_manifest, available
):
    import json

    from qtpy.QtWidgets import QDialog, QGroupBox, QLabel, QTabWidget

    document = json.loads(comparison_manifest.read_bytes())
    source = document["predictions"]
    document["predictions"] = [
        {**source[i % 2], "name": label, "provenance": {"factorial_condition": label}}
        for i, label in enumerate(available)
    ]
    comparison_manifest.write_text(json.dumps(document), encoding="utf-8")
    widget = ComparisonWidget(make_napari_viewer())
    qtbot.addWidget(widget)
    widget.load(str(comparison_manifest))
    qtbot.waitUntil(widget.factorial_button.isEnabled, timeout=5000)
    widget.factorial_button.click()
    qtbot.waitUntil(lambda: widget.findChild(QDialog) is not None, timeout=5000)
    dialog = widget.findChild(QDialog)
    tabs = dialog.findChild(QTabWidget)
    assert tabs.count() == 3
    for page in (0, 1):
        groups = tabs.widget(page).findChildren(QGroupBox)
        assert [g.title() for g in groups] == ["A+", "A-", "B+", "B-"]
        for group in groups:
            has_preview = any(label.pixmap() is not None and not label.pixmap().isNull()
                              for label in group.findChildren(QLabel))
            assert has_preview == (group.title() in available)
    assert "V/U [13, 29] → [17, 34]" in [q.text() for q in dialog.findChildren(QLabel)][0]
    dialog.close()


def test_z_layer_uses_audited_pair_and_agreement_reports_region(
    make_napari_viewer, qtbot, comparison_manifest
):
    import json

    from qtpy.QtWidgets import QDialog, QLabel

    doc = json.loads(comparison_manifest.read_bytes())
    for row, tag in zip(doc["predictions"], ("A+", "A-")):
        row.update(path="alternative.tif", score_scale=1,
                   provenance={"factorial_condition": tag, "experiment": {"weights_sha256": "a"*64}})
    comparison_manifest.write_text(json.dumps(doc), encoding="utf-8")
    viewer = make_napari_viewer()
    widget = ComparisonWidget(viewer)
    qtbot.addWidget(widget)
    widget.load(str(comparison_manifest))
    qtbot.waitUntil(widget.z_button.isEnabled, timeout=5000)
    widget.z_button.click()
    qtbot.waitUntil(lambda: any(layer.metadata.get("mode") == "z_sensitivity" for layer in viewer.layers),
                    timeout=5000)
    layer = next(layer for layer in viewer.layers if layer.metadata.get("mode") == "z_sensitivity")
    assert layer.visible and layer.metadata["threshold"] is None
    np.testing.assert_array_equal(layer.data, 0)
    widget.agreement_button.click()
    qtbot.waitUntil(lambda: widget.findChild(QDialog) is not None, timeout=5000)
    dialog = widget.findChild(QDialog)
    assert any("Écart Z absolu moyen 0.000" in w.text() for w in dialog.findChildren(QLabel))
    dialog.close()
