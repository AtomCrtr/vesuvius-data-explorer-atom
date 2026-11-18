"""Pure coordinate helpers: QC location -> napari world, view -> bounded read."""

import numpy as np
import pytest

from vesuvius_data_explorer.core.volume import read_slice, slice_stats
from vesuvius_data_explorer.qc.locate import location_to_world, view_metrics, visible_region
from vesuvius_data_explorer.qc.model import Location

LEVELS = [
    {"key": "0", "shape": [64, 128, 256]},
    {"key": "1", "shape": [32, 64, 128]},
    {"key": "2", "shape": [16, 32, 64]},
]
SCALE = (2.0, 1.0, 0.5)


def test_level_k_location_maps_to_world_with_non_uniform_scale():
    box = location_to_world(Location("1", "z", 5, (10, 20), (4, 8)), LEVELS, SCALE)
    assert box.axis == "z"
    # Centre of level-1 voxel 5 -> level-0 index 10 -> world 20.
    assert box.plane == 20.0
    # y: level-0 [20, 28) -> world [19.5, 27.5]; x: level-0 [40, 56) -> world [19.75, 27.75].
    assert box.low == (19.5, 19.75)
    assert box.high == (27.5, 27.75)
    assert box.center == (23.5, 23.75)
    assert box.rectangle() == [
        [20.0, 19.5, 19.75], [20.0, 19.5, 27.75], [20.0, 27.5, 27.75], [20.0, 27.5, 19.75],
    ]


def test_level_zero_is_identity_and_dict_input_is_accepted():
    box = location_to_world(
        {"level": "0", "axis": "z", "index": 7, "origin": [3, 4], "size": [2, 2]}, LEVELS, (1, 1, 1)
    )
    assert box.plane == 7.0
    assert box.low == (2.5, 3.5) and box.high == (4.5, 5.5)


def test_non_integer_ratios_and_unit_fallback_scales():
    levels = [{"key": "a", "shape": [10, 10, 10]}, {"key": "b", "shape": [3, 3, 3]}]
    box = location_to_world(Location("b", "z", 1, (0, 0), (3, 3)), levels, (1, 1, 1))
    # Level-b voxel 1 covers level-0 [3.33, 6.67): centre floor(4.5) = 4.
    assert box.plane == 4.0
    # The rectangle is clipped to the level-0 extent (10), not 3 * 10/3 rounded up.
    assert box.low == (-0.5, -0.5) and box.high == (9.5, 9.5)


def test_other_plane_axes_and_errors():
    box = location_to_world(Location("0", "y", 3, (1, 2), (1, 1)), LEVELS, SCALE)
    assert box.axis == "y" and box.plane == 3.0
    assert box.rectangle()[0] == [box.low[0], 3.0, box.low[1]]
    with pytest.raises(KeyError):
        location_to_world(Location("9", "z", 0, (0, 0), (1, 1)), LEVELS, SCALE)


def test_visible_region_uses_finest_level_that_fits():
    region = visible_region(LEVELS, SCALE, "z", 20.0, (10.0, 5.0), (60.0, 40.0))
    # y 10..60 (scale 1) and x 5..40 (scale 0.5, i.e. voxels 10..80): a 51 x 71 rectangle.
    assert region == {"level": "0", "axis": "z", "index": 10, "start_a": 10, "start_b": 10,
                      "width_a": 51, "width_b": 71, "width": 71}


def test_visible_region_falls_back_to_coarser_level_and_bounds():
    # Whole volume visible: level 0 is 128 x 256 (too wide for 100), level 1 is 64 x 128,
    # level 2 is 32 x 64 and fits.
    region = visible_region(LEVELS, SCALE, "z", 0.0, (-1e6, -1e6), (1e6, 1e6), max_side=100)
    assert region["level"] == "2"
    assert (region["start_a"], region["start_b"], region["width"]) == (0, 0, 64)
    assert (region["width_a"], region["width_b"]) == (32, 64)


def test_visible_region_central_window_when_nothing_fits():
    region = visible_region(LEVELS, SCALE, "z", 0.0, (-1e6, -1e6), (1e6, 1e6), max_side=16)
    assert region["level"] == "2" and region["width"] == 16
    assert (region["start_a"], region["start_b"]) == (8, 24)


def test_location_plane_round_trips_through_visible_region():
    box = location_to_world(Location("1", "z", 5, (10, 20), (4, 8)), LEVELS, SCALE)
    region = visible_region(LEVELS, SCALE, "z", box.plane, box.low, box.high)
    assert region["level"] == "0" and region["index"] == 10
    assert (region["start_a"], region["start_b"]) == (20, 40)


def test_view_metrics_matches_slice_stats_and_counts_background():
    data = np.zeros((4, 4), dtype=np.uint8)
    data[:2] = np.arange(8).reshape(2, 4) + 10
    metrics = view_metrics(data)
    assert metrics["background_pct"] == 50.0
    assert {k: metrics[k] for k in slice_stats(data)} == slice_stats(data)
    assert view_metrics(data, background_enabled=False)["background_pct"] is None


def test_visible_region_arguments_are_valid_read_slice_arguments():
    volume = np.arange(16 * 32 * 64, dtype=np.uint16).reshape(16, 32, 64)
    region = visible_region(LEVELS[2:], (1, 1, 1), "z", 3.0, (-5, -5), (100, 100), max_side=20)
    data = read_slice(volume, region["axis"], region["index"], region["start_a"],
                      region["start_b"], width=region["width_a"], width_b=region["width_b"])
    assert data.shape == (20, 20)


def test_thin_view_is_measured_on_its_rectangle_not_a_square():
    """Audit case: a 10 x 2 view used to be read as 10 x 10, mixing off-screen pixels."""
    volume = np.full((4, 32, 32), 100.0)
    volume[:, 10:20, 5:7] = 1.0  # the visible stripe
    levels = [{"key": "0", "shape": [4, 32, 32]}]
    region = visible_region(levels, (1, 1, 1), "z", 1.0, (10.0, 5.0), (19.0, 6.0))
    assert (region["width_a"], region["width_b"]) == (10, 2)
    data = read_slice(volume, region["axis"], region["index"], region["start_a"],
                      region["start_b"], width=region["width_a"], width_b=region["width_b"])
    metrics = view_metrics(data)
    assert data.shape == (10, 2) and metrics["p1"] == metrics["p99"] == 1.0


def test_central_window_keeps_the_view_aspect():
    levels = [{"key": "0", "shape": [4, 2000, 2000]}]
    region = visible_region(levels, (1, 1, 1), "z", 0.0, (0.0, 0.0), (1999.0, 99.0))
    assert (region["width_a"], region["width_b"]) == (512, 100)
