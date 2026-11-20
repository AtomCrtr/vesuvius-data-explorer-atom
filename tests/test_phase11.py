"""Phase 11 validation scripts: sign conventions that the Frag4 measurements depend on."""

from pathlib import Path

import numpy as np
import pytest
from scipy import ndimage


@pytest.fixture
def scripts(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "docs" / "validation"))


def test_phase_shift_returns_ir_minus_ct_displacement(scripts):
    module = pytest.importorskip("phase11_ir_registration")
    rng = np.random.default_rng(0)
    big = ndimage.gaussian_filter(rng.normal(size=(400, 400)), 2)
    a = big[100:228, 100:228]
    b = ndimage.shift(big, (-4.0, 6.0), order=1)[100:228, 100:228]  # b(y - 4, x + 6) = a(y, x)
    shift, ratio = module.phase_shift(a, b)
    np.testing.assert_allclose(shift, (-4.0, 6.0), atol=0.5)
    assert ratio > 2


def test_frag4_planes_are_symmetric_about_the_surface_and_ascend_toward_air(scripts):
    module = pytest.importorskip("phase11_z_frag4")
    layers = module.layer_coords()
    assert layers.shape == (62,) and np.all(np.diff(layers) > 0)
    np.testing.assert_allclose(layers[0] + layers[-1], 2 * 32, atol=1e-9)
    np.testing.assert_allclose(np.diff(layers), 2.215 / 3.24)
    assert 11 <= layers.min() and layers.max() <= 53  # Layers read by --prepare.
