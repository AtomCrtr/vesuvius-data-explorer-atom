"""Contrast uses one bounded coarse slice and always gives usable finite limits."""

import dask.array as da
import numpy as np
import pytest

from vesuvius_data_explorer.core import volume


def test_contrast_uses_only_central_bounded_coarse_slice():
    class UnreadableFine:
        def __getitem__(self, item):
            pytest.fail("The fine level must not be sampled")

    class TrackedCoarse:
        shape = (10, 1000, 2000)
        dtype = np.dtype("uint16")

        def __getitem__(self, selection):
            assert selection == (5, slice(498, 502), slice(998, 1002))
            return np.arange(16, dtype=self.dtype).reshape(4, 4)

    assert volume.estimate_contrast([UnreadableFine(), TrackedCoarse()], max_side=4) == (
        0.15,
        14.85,
    )


def test_contrast_ignores_nan_and_infinite_values():
    data = np.array([[[np.nan, -np.inf, 0], [10, np.inf, 20]]], dtype=np.float32)
    assert volume.estimate_contrast([da.from_array(data)]) == (0.2, 19.8)


@pytest.mark.parametrize(
    "data, expected",
    [
        (np.full((2, 4, 4), 7, dtype=np.uint16), (0.0, 65535.0)),
        (np.full((2, 4, 4), np.nan, dtype=np.float32), (-np.finfo("f4").max, np.finfo("f4").max)),
        (np.empty((0, 4, 4), dtype=np.int8), (-128.0, 127.0)),
        (np.ones((2, 4, 4), dtype=bool), (0.0, 1.0)),
        (np.zeros((1, 1, 1), dtype=np.float64), (-np.finfo("f8").max, np.finfo("f8").max)),
    ],
)
def test_empty_constant_and_nonfinite_samples_fall_back_to_dtype(data, expected):
    limits = volume.estimate_contrast([data])
    assert limits == expected
    assert all(np.isfinite(value) for value in limits)
    assert limits[0] < limits[1]


@pytest.mark.parametrize("max_side", [0, -1, 513, 2.5])
def test_invalid_contrast_bound_rejected(max_side):
    with pytest.raises(ValueError, match="1 à 512"):
        volume.estimate_contrast([np.zeros((2, 2, 2))], max_side=max_side)


def test_no_levels_rejected():
    with pytest.raises(ValueError, match="niveau"):
        volume.estimate_contrast([])
