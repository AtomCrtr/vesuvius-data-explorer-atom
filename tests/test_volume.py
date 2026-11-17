import numpy as np
import pytest

from vesuvius_data_explorer.demo import demo_volume
from vesuvius_data_explorer.volume import list_levels, normalized_preview, read_slice, slice_stats


def test_demo_is_reproducible():
    a = demo_volume((8, 16, 24))
    assert a.shape == (8, 16, 24)
    assert a.dtype == np.uint8
    np.testing.assert_array_equal(a, demo_volume((8, 16, 24)))


def test_read_slice_axis_order_and_bounded_roi():
    data = np.arange(4 * 5 * 6).reshape(4, 5, 6)
    np.testing.assert_array_equal(read_slice(data, 'z', 1, 1, 2, 2), data[1, 1:3, 2:4])
    np.testing.assert_array_equal(read_slice(data, 'y', 1, 1, 2, 2), data[1:3, 1, 2:4])
    np.testing.assert_array_equal(read_slice(data, 'x', 1, 1, 2, 2), data[1:3, 2:4, 1])
    assert read_slice(data, 'z', 0, 4, 5, 256).shape == (1, 1)


def test_invalid_axis_and_limits():
    data = np.ones((4, 5, 6))
    with pytest.raises(ValueError):
        read_slice(data, 'bad', 0, 0, 0)
    with pytest.raises(IndexError):
        read_slice(data, 'z', 4, 0, 0)
    with pytest.raises(ValueError):
        read_slice(data, 'z', 0, 0, 0, 513)


def test_image_stats_and_normalization():
    data = np.array([[0, 100], [np.nan, 50]])
    assert slice_stats(data)['finite_pct'] == 75
    view = normalized_preview(data)
    assert view.shape == data.shape
    assert np.all(np.isfinite(view))
    assert (view >= 0).all() and (view <= 1).all()


def test_list_level_from_array():
    levels = list_levels(np.zeros((3, 6, 7)))
    assert levels[0].key == '__root__' and levels[0].shape == (3, 6, 7)
