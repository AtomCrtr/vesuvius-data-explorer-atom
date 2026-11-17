import numpy as np
import pytest

from vesuvius_data_explorer.demo import demo_surface
from vesuvius_data_explorer.surface import load_surface_patch, surface_metrics


def test_flat_regular_surface_has_no_flips():
    y, x = np.mgrid[:30, :40].astype(float)
    z = np.zeros_like(x)
    result = surface_metrics(x, y, z)
    assert result['valid_pct'] == 100
    assert result['median_step'] == pytest.approx(1)
    assert result['normal_flip_pct'] == pytest.approx(0)


def test_missing_values():
    metrics = surface_metrics(*demo_surface())
    assert 90 < metrics['valid_pct'] < 100


def test_npy_patch_loading(tmp_path):
    y, x = np.mgrid[:30, :40].astype(float)
    for name, arr in [('x', x), ('y', y), ('z', x * 0)]:
        np.save(tmp_path / f'{name}.npy', arr)
    a, b, c = load_surface_patch(tmp_path, limit=16)
    assert a.shape == b.shape == c.shape == (16, 16)
