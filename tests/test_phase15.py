"""Phase 15 audit helpers: local ROC-AUC and label granularity."""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image


@pytest.fixture
def module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "docs" / "validation"))
    return pytest.importorskip("phase15_audit")


def test_local_roc_ignores_contrast_between_regions(module):
    rng = np.random.default_rng(5)
    truth = np.zeros((256, 256), bool)
    truth[:, ::8] = truth[:, 1::8] = True  # Strokes in every block.
    valid = np.ones_like(truth)
    fine = np.clip(0.4 * rng.random(truth.shape) + 0.5 * truth, 0, 1)
    assert module.local_roc(fine, truth, valid)["mean"] == pytest.approx(1.0)
    region = np.zeros(truth.shape)
    region[:, 128:] = 0.9  # A whole half scores higher, regardless of strokes.
    denser_right = truth & ((np.arange(256) >= 128)[None, :] | (rng.random(truth.shape) < 0.2))
    assert module.roc(region, denser_right, valid) > 0.65  # ~0.5 + (0.83 - 0.47) / 2 from the class shares.
    assert module.local_roc(region, denser_right, valid)["mean"] == pytest.approx(0.5)


def test_label_granularity_measures_a_known_rectangle(module, tmp_path):
    image = np.zeros((800, 800), np.uint8)
    image[100:200, 100:500] = 255  # 100 x 400 native px.
    Image.fromarray(image).save(tmp_path / "labels.png")
    out = module.label_granularity(tmp_path / "labels.png")
    assert out["components_ge_0p01_mm2"] == 1
    assert out["area_mm2_median"] == pytest.approx(100 * 400 * 3.24**2 / 1e6, rel=0.05)
    assert abs(out["max_inscribed_width_um_median"] - 324) < 30
