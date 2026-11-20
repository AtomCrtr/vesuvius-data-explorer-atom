from hashlib import sha256
from pathlib import Path

import numpy as np
import pytest

from vesuvius_data_explorer.core.ink_factorial import factorial_report, summarize_pair


def test_missing_checkpoints_and_masked_nonfinite_scores():
    scores = np.array([[0.3, 0.9, 0.9, np.nan, np.inf, -40.]])
    alternate = np.array([[0.8, 0.4, 0.8, 0.2, 0., 4.]])
    mask = np.array([[True, True, True, True, True, False]])
    report = factorial_report({"A+": (scores, 1), "A-": (alternate, 1)}, mask)
    assert report["conditions"]["B+"] == "checkpoint_missing"
    assert set(report["contrasts"]) == {"A+/A-"}
    assert len(report["unavailable_contrasts"]) == 5 and report["rank_interaction"] is None
    assert (report["common_pixels"], report["masked"], report["missing_within_mask"]) == (3, 1, 2)
    top = report["contrasts"]["A+/A-"]["rank_agreement"][0]
    assert top["a_selected"] == top["b_selected"] == 2 and top["both_positive"] == 1


def test_checkpoint_order_interaction_and_declared_scale():
    a = np.array([[0, 10, 20, 30, 40]])
    b = np.flip(a, axis=1)
    mask = np.ones_like(a, bool)
    pair = summarize_pair(a, a/40, mask, (40, 1))
    assert pair["spearman"] == pytest.approx(1)
    assert all(row["jaccard"] == 1 for row in pair["thresholds"])
    both = {"A+": (a, 40), "A-": (b, 40), "B+": (a/40, 1), "B-": (b/40, 1)}
    same_effect = factorial_report(both, mask)
    assert len(same_effect["contrasts"]) == 6
    assert same_effect["rank_interaction"]["mean_absolute"] == 0
    both["B-"] = (a/40, 1)
    assert factorial_report(both, mask)["rank_interaction"]["mean_absolute"] > 0
    with pytest.raises(ValueError, match="grille"):
        summarize_pair(a, b[:, :-1], mask, (40, 40))


@pytest.fixture
def validation_scripts(monkeypatch):
    folder = Path(__file__).parents[1]/"docs"/"validation"
    monkeypatch.syspath_prepend(str(folder))


def test_checkpoint_integrity_gates_remote_lookups(validation_scripts, tmp_path, monkeypatch):
    module = pytest.importorskip("phase7_checkpoints")
    (tmp_path/"canonical").mkdir()
    path = tmp_path/"canonical"/module.CHECKPOINT
    monkeypatch.setattr(module, "WEIGHTS_SHA", sha256(b"verified").hexdigest())

    def fail(*args, **kwargs):
        pytest.fail("An invalid checkpoint must be rejected before remote lookups")

    monkeypatch.setattr(module, "request", fail)
    with pytest.raises(ValueError, match="missing"):
        module.run(tmp_path, tmp_path/"no-audit")
    path.write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="SHA-256"):
        module.run(tmp_path, tmp_path/"no-audit")


def test_shared_hann_assembly_preserves_uv_and_missing_mask(validation_scripts):
    module = pytest.importorskip("phase7_compare")
    origins = [(10, 20), (10, 22)]
    tile = np.array([np.full((2, 5, 5), .25), np.full((2, 5, 5), .75)], "f4")
    valid = np.ones((2, 5, 5), bool)
    valid[:, 1, 2] = False
    scores, mask = module.assemble(origins, tile, valid, (10, 20, 5, 7))
    assert scores.shape == (2, 5, 7)
    assert not mask[0].any() and not mask[:, 0].any() and not mask[1, 2]
    np.testing.assert_allclose(scores[0][mask], .25)
    np.testing.assert_allclose(scores[1][mask], .75)
    assert np.isnan(scores[:, ~mask]).all()


def test_z_preparation_and_tifxyz_orientation_sign(validation_scripts):
    experiment = pytest.importorskip("phase7_experiment")
    orientation = pytest.importorskip("phase7_orientation")
    from vesuvius_data_explorer.core.tifxyz import TifxyzSurface

    v, u = np.indices((12, 12))
    points = np.stack((np.full(v.shape, 25), v, u), axis=-1).astype(float)
    mesh = TifxyzSurface(points, {"scale": [1.]}, v.shape, 1, "synthetic", 0)
    _, n = orientation.uv_geometry(mesh, 6, 6, radius=3)
    np.testing.assert_array_equal(n, np.broadcast_to([1, 0, 0], n.shape))
    raw = np.arange(62, dtype="u1")[:, None, None] + np.zeros((62, 256, 256), "u1")
    plus, mask = experiment.prepare_tile(raw)
    minus, reversed_mask = experiment.prepare_tile(raw, True)
    np.testing.assert_array_equal(minus, plus[:, :, ::-1])
    np.testing.assert_array_equal(mask, reversed_mask)
