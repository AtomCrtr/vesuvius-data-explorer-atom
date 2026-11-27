"""Geometry and fusion controls for the label-free CPU pilot."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[1] / "docs/validation"))
import phase18_cpu_pilot as pilot  # noqa: E402


def test_patch_is_aligned_and_has_the_full_common_mask():
    mask = np.zeros((1024, 1024), dtype=bool)
    mask[384:640, 384:640] = True
    assert pilot.choose_patch(mask) == (256, 256)


def test_replication_regions_use_mask_quartiles_and_avoid_the_central_patch():
    mask = np.ones((4096, 1024), dtype=bool)
    assert pilot.select_region(mask, "central") == (1792, 256)
    assert pilot.select_region(mask, "upper") == (768, 256)
    assert pilot.select_region(mask, "lower") == (2816, 256)


def test_stitch_uses_the_right_tiles_for_each_stride():
    predictions = {(v, u): np.full((256, 256), value, dtype=np.float32)
                   for value, (v, u) in enumerate(pilot.local_origins(128))}
    non_overlapping = pilot.stitch_core(predictions, 256)
    overlapping = pilot.stitch_core(predictions, 128)
    assert non_overlapping.shape == (256, 256)
    assert non_overlapping[63, 63] == 0.0
    assert non_overlapping[-64, -64] == 8.0
    assert 0 < overlapping[63, 63] < 4
    assert 4 < overlapping[-64, -64] < 8
    assert len(predictions) == 9


def test_uniform_overlap_averages_the_same_four_tiles():
    predictions = {(v, u): np.full((256, 256), value, dtype=np.float32)
                   for value, (v, u) in enumerate(pilot.local_origins(128))}
    uniform = pilot.stitch_core(predictions, 128, uniform=True)
    assert uniform[0, 0] == 2.0
    assert uniform[-1, -1] == 6.0
    assert pilot.stitch_core(predictions, 128)[0, 0] < uniform[0, 0]
