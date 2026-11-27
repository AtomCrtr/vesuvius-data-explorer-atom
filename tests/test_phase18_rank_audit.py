"""Exact checks for grid averaging and the top-k perturbation certificate."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[1] / "docs/validation"))
import phase18_cpu_pilot as pilot  # noqa: E402
import phase18_rank_audit as audit  # noqa: E402


def test_average_of_four_grid_phases_is_the_uniform_overlap():
    tiles = {(v, u): np.full((256, 256), value)
             for value, (v, u) in enumerate(pilot.local_origins(128))}
    mosaics = audit.phase_mosaics(tiles)
    np.testing.assert_array_equal(mosaics[:, 0, 0], [0, 1, 3, 4])
    np.testing.assert_array_equal(mosaics[:, -1, -1], [8, 7, 5, 4])
    np.testing.assert_array_equal(mosaics.mean(axis=0), pilot.stitch_core(tiles, 128, uniform=True))


def test_margin_distinguishes_certified_top_k_from_a_small_gap():
    a = np.array([0.75, 0.5, 0.0])
    b = np.array([0.625, 0.625, 0.0])
    assert audit.margin_check(a, b, 1) == {
        "top_k": 1, "cutoff_gap": 0.25, "max_change": 0.125, "certifies_top_k": False,
    }
    assert audit.margin_check(a, b, 2)["certifies_top_k"]
