import json

import numpy as np
import pytest
import tifffile
from PIL import Image
from test_comparison import comparison_fixture  # noqa: F401

from vesuvius_data_explorer.core.comparison import (
    Candidate,
    ComparisonView,
    comparison_values,
    export_comparison_png,
    load_comparison,
    load_comparison_session,
    save_comparison_session,
)
from vesuvius_data_explorer.core.consensus import analyze_comparison, analyze_pair, rank_agreement


def registered_manifest(path):
    doc = json.loads(path.read_bytes())
    for entry in doc["predictions"]:
        entry["registration"] = {"axes": ["v", "u"], "orientation_vu": ["+v", "+u"],
                                 "origin_vu": [13, 29], "pixel_size_um_vu": [8.64, 9.1],
                                 "surface_revision": "sha256:abc", "face": "recto",
                                 "evidence": "registered test fixture"}
        entry["calibration"] = {"method": "isotonic", "reference": "fixture", "event": "ink"}
    return doc


@pytest.mark.parametrize(("field", "incorrect"), [
    ("orientation_vu", ["+u", "+v"]), ("origin_vu", [29, 13]), ("face", "verso"),
    ("pixel_size_um_vu", [9.1, 8.64]), ("surface_revision", "sha256:def"),
])
def test_conflicting_map_registration(comparison_manifest, field, incorrect):
    doc = registered_manifest(comparison_manifest)
    doc["predictions"][1]["registration"][field] = incorrect
    comparison_manifest.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError, match="Recalage|faces"):
        load_comparison(comparison_manifest)


def test_tiff_orientation_rejected(comparison_manifest):
    tifffile.imwrite(comparison_manifest.parent / "reader.tif", np.zeros((4, 5), "u1"),
                     extratags=[(274, "H", 1, 3, False)], photometric="minisblack")
    with pytest.raises(ValueError, match="Orientation TIFF"):
        load_comparison(comparison_manifest)


def test_threshold_counts_missing_and_raster_order(comparison_manifest):
    folder = comparison_manifest.parent
    a = np.zeros((4, 5), np.uint8)
    b = np.zeros((4, 5), np.float32)
    a[1:3, 2:5] = [[200, 255, 10], [5, 128, 0]]
    b[1:3, 2:5] = [[1, 0.3, 0.8], [0.2, np.nan, 0.54]]
    tifffile.imwrite(folder / "reader.tif", a, photometric="minisblack")
    tifffile.imwrite(folder / "alternative.tif", b, photometric="minisblack")
    comparison = load_comparison(comparison_manifest)
    roi = (1, 2, 2, 3)
    report = analyze_pair(comparison, (1, 2), roi, (50, (100, 100)))
    assert report["coordinates"]["start_vu"] == [14, 31]
    assert report["coordinates"]["stop_vu"] == [16, 34]
    assert (report["paired_pixels"], report["missing_pixels"]) == (5, 1)
    assert report["probability_differences"] is None
    row, hundred = report["thresholds"]
    assert row == {"thresholds_percent": [50, 50], "uncertain_pixels": 1, "both_positive": 1,
                   "a_only": 1, "b_only": 2, "both_below": 1, "jaccard": 0.25,
                   "dice": 0.4, "disagreement_rate": 0.6}
    assert hundred["jaccard"] == 0 and hundred["a_only"] == hundred["b_only"] == 1
    assert report["score_distributions"][0]["finite_pixels"] == 6
    assert report["score_distributions"][1]["finite_pixels"] == 5
    assert report == analyze_pair(comparison, (1, 2), roi, (50, (100, 100)))
    np.testing.assert_array_equal(
        comparison_values(*comparison.predictions, 50, "uncertainty")[1:3, 2:5],
        [[0, 0, 0], [0, 2, 1]],
    )
    with pytest.raises(ValueError, match="seuils"):
        analyze_pair(comparison, (1, 2), roi, (101,))


def test_rank_ties_and_empty_decisions(comparison_manifest):
    a, b = np.array([9, 1, 9, 0]), np.array([0, 9, 1, 9])
    row, = rank_agreement(a, b, (0.25,))
    assert (row["requested_pixels"], row["a_selected"], row["b_selected"]) == (1, 2, 2)
    assert row["both_positive"] == row["jaccard"] == 0
    comparison = load_comparison(comparison_manifest)
    report = analyze_pair(comparison, (1, 2), (0, 0, 1, 1), (50,))
    assert report["thresholds"][0]["jaccard"] is None
    assert report["thresholds"][0]["dice"] is None


def test_probability_gate_and_unique_pairs(comparison_manifest):
    doc = registered_manifest(comparison_manifest)
    doc["predictions"].append({**doc["predictions"][1], "name": "Troisième"})
    comparison_manifest.write_text(json.dumps(doc), encoding="utf-8")
    comparison = load_comparison(comparison_manifest)
    reports = analyze_comparison(comparison, (0, 0, 4, 5), iter((25, 50)))
    assert [[m["name"] for m in row["models"]] for row in reports] == [
        ["Reader", "Autre"], ["Reader", "Troisième"], ["Autre", "Troisième"],
    ]
    assert all(len(row["thresholds"]) == 2 for row in reports)
    assert reports[0]["probability_differences"]["event"] == "ink"
    assert reports[2]["probability_differences"]["mean_absolute_difference"] == 0
    del doc["predictions"][1]["registration"]
    comparison_manifest.write_text(json.dumps(doc), encoding="utf-8")
    report = analyze_pair(load_comparison(comparison_manifest), (1, 2), (0, 0, 4, 5))
    assert report["probability_differences"] is None


def test_candidate_review_and_registration_in_exports(comparison_manifest, tmp_path):
    doc = registered_manifest(comparison_manifest)
    comparison_manifest.write_text(json.dumps(doc), encoding="utf-8")
    comparison = load_comparison(comparison_manifest)
    roi = (1, 2, 2, 2)
    candidate = Candidate("Trace 7", roi, observation="Deux traits visibles", hypothesis="Alpha ?",
                          confidence="faible", comment="Champ de revue",
                          reviewer="Relecteur du test", evidence="fixture:separate", models=(2, 1))
    view = ComparisonView(0, (1, 2), 65, 75, False, roi, (candidate,), "uncertainty")
    session, png = tmp_path / "review.json", tmp_path / "review.png"
    save_comparison_session(session, comparison, view)
    export_comparison_png(png, comparison, view)
    _, recovered_view = load_comparison_session(session)
    assert view == recovered_view
    exported = json.loads(session.read_bytes())
    annotation = exported["settings"]["candidates"][0]
    assert annotation["status"] == "validation_externe_documentee"
    assert annotation["models"] == [2, 1]
    assert exported["sources"]["predictions"][1]["registration"]["face"] == "recto"
    with Image.open(png) as image:
        assert json.loads(image.info["vesuvius_comparison"]) == exported
    annotation["evidence"] = ""
    session.write_text(json.dumps(exported), encoding="utf-8")
    with pytest.raises(ValueError):
        load_comparison_session(session)
