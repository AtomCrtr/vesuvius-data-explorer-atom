"""Phase 16: PPM pitch on a synthetic non-isometric mesh and real-pitch resampling."""

from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "docs" / "validation"))
    return pytest.importorskip("phase16_scale")


def test_lattice_pitch_recovers_a_non_isometric_sheared_map(module):
    rows, cols = np.mgrid[0:40, 0:30] * module.LATTICE
    # 1.25 voxel per UV column (x and a z tilt), 0.9 per UV row along y.
    points = np.stack([1.0 * cols, 0.9 * rows, 0.75 * cols], -1).astype(float)
    valid = np.ones(rows.shape, bool)
    valid[5, 5] = False
    out = module.lattice_pitch(points, valid)
    assert out["pitch_col_vox"] == pytest.approx(1.25)
    assert out["pitch_row_vox"] == pytest.approx(0.9)
    assert out["abs_cos_median"] == pytest.approx(0.0, abs=1e-12)
    sheared = points + np.stack([0.9 * rows, 0 * rows, 0 * rows], -1)
    assert module.lattice_pitch(sheared, valid)["abs_cos_median"] > 0.5


class FakeSurface:
    def layer(self, k, r0, c0, h, w):
        r, c = np.mgrid[r0:r0 + h, c0:c0 + w]
        return (100 * k + 3 * r + 7 * c).astype(np.uint16)


def test_extract_scaled_at_nominal_step_matches_phase13(module):
    import phase13_eval as ev

    mask = np.ones((2000, 2000), bool)
    coords = np.linspace(20, 44, 62)
    w2 = {"w2_mean_u16": 20000.0, "w2_std_u16": 3000.0}
    nominal = ev.extract(FakeSurface(), mask, (600, 700), coords, w2)
    scaled = module.extract_scaled(FakeSurface(), mask, (600, 700), coords, w2, [module.NOMINAL_STEP] * 2)
    assert np.array_equal(nominal[0], scaled[0]) and np.array_equal(nominal[1], scaled[1])
    assert nominal[2] == scaled[2]


def test_scaled_label_grid_follows_the_steps(module):
    labels = np.zeros((3000, 3000), bool)
    labels[:, 1000:] = True
    truth = module.sample_labels_scaled(labels, [0, 0], [0.5, 1.0])
    assert abs(2 + np.argmax(truth[0]) * 1.0 - 1000) <= 1
