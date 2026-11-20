import json

import numpy as np
import pytest
import tifffile
from PIL import Image

from vesuvius_data_explorer.core.comparison import (
    Candidate,
    ComparisonView,
    calibrated_pair,
    comparison_values,
    disagreement_codes,
    export_comparison_png,
    load_comparison,
    load_comparison_session,
    save_comparison_session,
)


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


def test_disagreement_session_and_png_provenance(comparison_manifest, tmp_path):
    a = np.full((4, 5), 128, dtype=np.uint8)
    a[1, 2] = 0
    b = np.full((4, 5), 0.75, dtype=np.float32)
    b[1, 1] = 0.49
    b[2, 1] = np.nan
    tifffile.imwrite(tmp_path / "reader.tif", a, photometric="minisblack")
    tifffile.imwrite(tmp_path / "alternative.tif", b, photometric="minisblack")
    document = json.loads(comparison_manifest.read_text(encoding="utf-8"))
    document["predictions"][0]["provenance"] = {"checkpoint": "fixture-v1", "batch": 4}
    comparison_manifest.write_text(json.dumps(document), encoding="utf-8")
    comparison = load_comparison(comparison_manifest)
    codes = disagreement_codes(*comparison.predictions, 50)
    assert codes[1, 1] == 1 and codes[1, 2] == 2 and codes[2, 1] == 0
    assert np.count_nonzero(codes) == 2
    roi = (1, 1, 2, 2)
    view = ComparisonView(0, (1, 2), 50, 70, True, roi, (Candidate("α ?", roi),))
    session = tmp_path / "session.json"
    capture = tmp_path / "roi.png"
    save_comparison_session(session, comparison, view)
    export_comparison_png(capture, comparison, view)
    loaded, saved_view = load_comparison_session(session)
    assert saved_view == view and loaded.manifest == comparison_manifest
    with Image.open(capture) as image:
        assert image.size == (2, 2)
        metadata = json.loads(image.info["vesuvius_comparison"])
        assert metadata == json.loads(session.read_text(encoding="utf-8"))
        assert metadata["roi_coordinates"]["start_vu"] == [14, 30]
        assert metadata["roi_coordinates"]["stop_vu"] == [16, 32]
        assert metadata["settings"]["candidates"][0]["status"] == "candidat_non_valide"
        assert metadata["sources"]["predictions"][0]["provenance"]["checkpoint"] == "fixture-v1"
        pixels = np.asarray(image)
        assert pixels[0, 0, 0] > pixels[0, 0, 2]
        assert pixels[0, 1, 2] > pixels[0, 1, 0]
    with pytest.raises(ValueError, match="fichiers sources"):
        save_comparison_session(comparison_manifest, comparison, view)
    a[0, 0] = 1
    tifffile.imwrite(tmp_path / "reader.tif", a, photometric="minisblack")
    with pytest.raises(ValueError, match="pixels sources ont changé"):
        load_comparison_session(session)


def test_signed_score_difference_and_calibration_require_explicit_evidence(comparison_manifest):
    comparison = load_comparison(comparison_manifest)
    a, b = comparison.predictions
    assert not calibrated_pair(a, b)
    original = a.image.pixels.copy()
    expected = original / 255.0 - b.image.pixels.astype(float)
    difference = comparison_values(a, b, 50, "difference")
    np.testing.assert_allclose(difference, expected, atol=1e-8, rtol=0)
    np.testing.assert_array_equal(a.image.pixels, original)
    consensus = comparison_values(a, b, 50, "consensus")
    assert int(consensus.sum()) == 10
    doc = json.loads(comparison_manifest.read_text(encoding="utf-8"))
    for item in doc["predictions"]:
        item["calibration"] = {"method": "isotonic", "reference": "fixture-holdout", "event": "ink"}
    comparison_manifest.write_text(json.dumps(doc), encoding="utf-8")
    assert calibrated_pair(*load_comparison(comparison_manifest).predictions)
