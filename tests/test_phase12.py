"""Phase 12 evaluation script: binned ranking metrics against exact definitions."""

from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "docs" / "validation"))
    return pytest.importorskip("phase12_ink_eval")


def test_binned_ranking_matches_exact_average_precision_and_auc(module):
    rng = np.random.default_rng(1)
    n = 3000
    score = (rng.permutation(module.BINS)[:n] + 0.5) / module.BINS  # One score per bin: no ties.
    truth = rng.random(n) < np.clip(score, 0.05, 0.95)
    idx = module.binned(score)
    ap, roc = module.ranking(np.bincount(idx[truth], minlength=module.BINS),
                             np.bincount(idx[~truth], minlength=module.BINS))
    hits = truth[np.argsort(-score)]
    exact_ap = (np.cumsum(hits)[hits] / (np.flatnonzero(hits) + 1)).mean()
    exact_roc = (score[truth][:, None] > score[~truth][None, :]).mean()
    assert ap == pytest.approx(exact_ap, abs=1e-12)
    assert roc == pytest.approx(exact_roc, abs=1e-12)
    assert module.ranking(np.zeros(module.BINS), np.ones(module.BINS)) == (None, None)


def test_pixel_metrics_and_undefined_class(module):
    pred = np.array([1, 1, 0, 0], bool)
    truth = np.array([1, 0, 1, 0], bool)
    m = module.pixel_metrics(pred, truth)
    assert (m["TP"], m["FP"], m["FN"], m["TN"]) == (1, 1, 1, 1)
    assert m["Dice"] == pytest.approx(0.5) and m["Jaccard"] == pytest.approx(1 / 3)
    assert module.pixel_metrics(pred, np.zeros(4, bool))["defined"] is False
