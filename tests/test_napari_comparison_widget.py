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
