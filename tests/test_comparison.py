import json

import numpy as np
import pytest
import tifffile

from vesuvius_data_explorer.core.comparison import load_comparison


@pytest.fixture(name="comparison_manifest")
def comparison_fixture(tmp_path):
    planes = {
        "ct.tif": np.arange(20, dtype=np.uint16).reshape(4, 5),
        "surface.tif": np.arange(20, dtype=np.uint8).reshape(4, 5),
        "reader.tif": np.linspace(0, 255, 20, dtype=np.uint8).reshape(4, 5),
        "alternative.tif": np.linspace(0, 1, 20, dtype=np.float32).reshape(4, 5),
    }
    for name, image in planes.items():
        tifffile.imwrite(tmp_path / name, image, photometric="minisblack")
    manifest = tmp_path / "comparison.json"
    document = {
        "version": 1, "axes": ["v", "u"], "volume_id": "scan", "segment_id": "segment",
        "surface_revision": "sha256:abc", "origin_vu": [13, 29], "pixel_size_um_vu": [8.64, 9.1],
        "ct": "ct.tif", "surface": "surface.tif", "predictions": [
            {"name": "Reader", "model": "Reader V3", "path": "reader.tif", "score_scale": 255},
            {"name": "Autre", "model": "témoin 1", "path": "alternative.tif", "score_scale": 1},
        ],
    }
    manifest.write_text(json.dumps(document), encoding="utf-8")
    return manifest


def test_load_comparison_keeps_values_and_registration(comparison_manifest):
    result = load_comparison(comparison_manifest)
    assert result.origin_vu == (13, 29) and result.pixel_size_um_vu == (8.64, 9.1)
    assert [plane.score_scale for plane in result.predictions] == [255, 1]
    assert result.ct.pixels.dtype == np.uint16 and result.predictions[1].image.pixels.dtype == np.float32
    for plane in (result.ct, result.surface, *(item.image for item in result.predictions)):
        np.testing.assert_array_equal(plane.pixels, tifffile.imread(plane.path))
        assert not plane.pixels.flags.writeable


@pytest.mark.parametrize("key, value, error", [
    ("axes", ["u", "v"], "axes"),
    ("origin_vu", [True, 1], "Origine"),
    ("pixel_size_um_vu", [1, -2], "positif"),
    ("ct", "../ct.tif", "hors du dossier"),
])
def test_inconsistent_registration_fails(comparison_manifest, key, value, error):
    data = json.loads(comparison_manifest.read_text(encoding="utf-8"))
    data[key] = value
    comparison_manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match=error):
        load_comparison(comparison_manifest)


def test_rejects_wrong_size_and_scores_outside_declared_range(comparison_manifest):
    prediction = comparison_manifest.parent / "reader.tif"
    tifffile.imwrite(prediction, np.zeros((5, 4), dtype=np.uint8), photometric="minisblack")
    with pytest.raises(ValueError, match="Grille UV"):
        load_comparison(comparison_manifest)
    tifffile.imwrite(prediction, np.full((4, 5), 256, dtype=np.uint16), photometric="minisblack")
    with pytest.raises(ValueError, match="scores"):
        load_comparison(comparison_manifest)
