from dataclasses import replace

import numpy as np
import zarr

from vesuvius_data_explorer.core.geometry import (
    level_factors,
    sampling_details,
    to_level,
    verified_sampling,
)
from vesuvius_data_explorer.core.volume import Level, list_levels

URI = ("s3://vesuvius-challenge-open-data/PHercParis4/volumes/"
       "20260310170716-45.532um-11.0m-74keV-masked.zarr")


def test_box_centres_use_scale_and_not_rounded_array_extent():
    shapes = [(4071, 2264, 2264), (2036, 1132, 1132), (1018, 566, 566), (509, 283, 283)]
    levels = [Level(str(i), shape, "uint8", (128,)*3, (2**i,)*3, True, (0, 0, 0))
              for i, shape in enumerate(shapes)]
    sampling = verified_sampling(URI, levels)
    assert sampling is not None
    centres = np.array([[3.5, 3.5, 3.5], [3075.5, 1027.5, 1027.5]])
    exact = to_level(centres, level_factors(shapes, sampling)[3])
    np.testing.assert_array_equal(exact, [[0, 0, 0], [384, 128, 128]])
    assert not np.allclose(to_level(centres, level_factors(shapes)[3]), exact)
    assert sampling_details(shapes, 3, sampling)["verified_source"] == URI
    assert verified_sampling(URI, [*levels[:3], replace(levels[3], translation=(1, 0, 0))]) is None
    assert verified_sampling(URI, [*levels[:3], replace(levels[3], scale=(7, 8, 8))]) is None
    assert verified_sampling(URI + "-other", levels) is None


def test_ngff_translation_composition_and_unknown_transform(tmp_path):
    root = zarr.open_group(str(tmp_path / "transform.zarr"), mode="w", zarr_format=3)
    root.create_array("0", shape=(6, 7, 8), dtype="uint8")
    root.create_array("1", shape=(3, 4, 4), dtype="uint8")
    root.attrs["multiscales"] = [{"axes": ["z", "y", "x"], "coordinateTransformations": [
        {"type": "scale", "scale": [2, 3, 4]},
        {"type": "translation", "translation": [100, 200, 300]},
    ], "datasets": [
        {"path": "0", "coordinateTransformations": [
            {"type": "scale", "scale": [1, 2, 3]},
            {"type": "translation", "translation": [1, 2, 3]},
        ]},
        {"path": "1", "coordinateTransformations": [
            {"type": "scale", "scale": [2, 4, 6]},
            {"type": "identity"},
        ]},
    ]}]
    fine, coarse = list_levels(root)
    assert fine.scale == (2, 6, 12) and fine.translation == (102, 206, 312)
    assert coarse.scale == (4, 12, 24) and coarse.translation is None
