"""Phase 13 evaluation script: paired block bootstrap and non-learned baselines."""

from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "docs" / "validation"))
    return pytest.importorskip("phase13_eval")


def test_paired_bootstrap_separates_informative_and_identical_scores(module):
    rng = np.random.default_rng(3)
    truth = np.zeros((256, 256), bool)
    truth[::16, :] = True  # Thin lines spread over every block.
    valid = np.ones_like(truth)
    noise = rng.random(truth.shape)
    maps = {"Z_out": np.clip(0.3 * noise + 0.6 * truth, 0, 1), "Z_in": noise, "B1": noise, "B2": noise}
    result = module.pooled(maps, truth, valid)
    assert result["Z_out"]["ROC_AUC"] == pytest.approx(1.0)
    assert result["Z_out"]["ROC_AUC_95"][0] > 0.99
    assert abs(result["Z_in"]["ROC_AUC"] - 0.5) < 0.05
    assert result["diff_PR_Zout_minus_Zin"]["interval_95"][0] > 0.5
    same = module.pooled({s: noise for s in module.SCORES}, truth, valid)
    assert same["diff_PR_Zout_minus_Zin"]["interval_95"] == [0.0, 0.0]


def test_sparse_bootstrap_matches_dense_integer_counts(module):
    weights = np.array([[2, 0, 1], [0, 3, 0]], dtype=np.int64)
    histograms = np.array([[0, 0, 4, 0], [0, 2**30, 0, 0], [0, 5, 6, 0]], dtype=np.int64)
    counts = module.bootstrap_counts(weights, histograms)
    np.testing.assert_array_equal(counts, weights @ histograms, strict=True)


def test_phase13_rechecks_protocol_before_preparation_or_report(module, monkeypatch, tmp_path):
    path = tmp_path / "phase13-protocol.json"
    frozen = (module.HERE / path.name).read_bytes().replace(b"\r\n", b"\n")
    path.write_bytes(frozen.replace(b"\n", b"\r\n"))
    monkeypatch.setattr(module, "PROTOCOL", path)
    monkeypatch.setattr(module, "WORK", tmp_path)
    module.use_protocol(path)
    path.write_bytes(frozen.replace(b'"Frag3":', b'"Frag9":'))
    with pytest.raises(ValueError, match="not a frozen protocol"):
        module.prepare("Frag4")
    output = tmp_path / "report.json"
    with pytest.raises(ValueError, match="not a frozen protocol"):
        module.report(output)
    assert not output.exists()


def test_frozen_protocols_are_verified_and_modified_ones_refused(module, tmp_path):
    source = Path(module.__file__).parent / "phase14-protocol.json"
    text = source.read_bytes().replace(b"\r\n", b"\n")
    crlf = tmp_path / "phase14-protocol.json"
    crlf.write_bytes(text.replace(b"\n", b"\r\n"))  # Windows checkout with core.autocrlf.
    module.use_protocol(crlf)
    assert module.WORK == Path("data/phase14")
    crlf.write_bytes(text.replace(b"Frag6", b"Frag7"))
    with pytest.raises(ValueError, match="not a frozen protocol"):
        module.use_protocol(crlf)
    module.use_protocol(Path(module.__file__).parent / "phase13-protocol.json")  # Restore the default.


def test_baselines_follow_the_surface_planes(module):
    volume = np.full((62, 64, 64), 100, np.uint8)
    volume[30:32, :, :32] = 50  # Darker surface on the left half.
    b1, b2 = module.baselines(volume)
    assert b1.shape == b2.shape == (64, 64)
    assert b1[:, :16].mean() > b1[:, 48:].mean()
    assert b2[:, 32].mean() > b2[:, 0].mean()  # Texture peaks at the edge.
