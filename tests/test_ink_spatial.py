import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pytest
from test_comparison import comparison_fixture  # noqa: F401

from vesuvius_data_explorer.core.comparison import (
    ComparisonView,
    comparison_values,
    load_comparison,
    load_comparison_session,
)
from vesuvius_data_explorer.core.ink_exam import export_examination
from vesuvius_data_explorer.core.ink_spatial import block_interval, effect, windows


def test_fixed_windows_cover_surface_exactly_once_and_retain_boundary():
    shape = (211, 297)
    tiles = windows(shape, 128)
    coverage = np.zeros(shape, "u1")
    for v, u, h, w in tiles:
        coverage[v:v+h, u:u+w] += 1
    assert tiles[-1] == (128, 256, 83, 41)
    np.testing.assert_array_equal(coverage, np.ones(shape, "u1"))


def test_constant_maps_and_missing_values_have_no_artificial_correlation():
    a = np.full((16, 16), .25, "f4")
    b = np.full_like(a, .5)
    valid = np.ones_like(a, bool)
    valid[:4] = False
    b[7, 5] = np.nan
    r = effect(a, b, valid)
    assert r["agreement"]["pearson"] is None and r["agreement"]["spearman"] is None
    assert r["agreement"]["missing_within_mask"] == 1
    assert r["score_stats"][0]["variance"] == 0 and r["score_stats"][1]["almost_constant"]
    assert r["score_stats"][0]["entropy_bits"] == 0
    assert r["absolute_Z_effect_block32"]["estimate"] == .25
    assert r["absolute_Z_effect_block64"]["interval_95"] is None


def test_block_interval_is_deterministic_and_respects_spatial_blocks():
    a = np.repeat(np.repeat(np.arange(16).reshape(4, 4), 8, axis=0), 8, axis=1)
    mask = np.ones(a.shape, bool)
    mask[0, 0] = False
    first = block_interval(a, mask, block=8)
    assert first == block_interval(a, mask, block=8)
    assert first["blocks"] == 16
    assert first["interval_95"][0] < a[mask].mean() < first["interval_95"][1]
    assert np.ptp(first["interval_95"]) > np.ptp(block_interval(a, mask, block=1)["interval_95"])
    assert block_interval(a, np.zeros_like(mask))["estimate"] is None


def test_z_sensitivity_export_requires_one_experiment_and_roundtrips(comparison_manifest, tmp_path):
    doc = json.loads(comparison_manifest.read_bytes())
    for row, label in zip(doc["predictions"], ("A+", "A-")):
        row["path"] = "alternative.tif"
        row["score_scale"] = 1
        row["provenance"] = {"factorial_condition": label, "experiment": {"weights_sha256": "a"*64}}
    comparison_manifest.write_text(json.dumps(doc), encoding="utf-8")
    c = load_comparison(comparison_manifest)
    np.testing.assert_array_equal(comparison_values(*c.predictions, 50, "z_sensitivity"), 0)
    state = ComparisonView(0, (1, 2), 50, 100, False, (0, 0, 4, 5), (), "z_sensitivity")
    path = tmp_path/"surface.zip"
    export_examination(path, c, state)
    with ZipFile(path) as archive:
        archive.extractall(tmp_path/"unpacked")
    assert load_comparison_session(tmp_path/"unpacked"/"session.json")[1] == state
    doc["predictions"][1]["provenance"]["experiment"]["weights_sha256"] = "b"*64
    comparison_manifest.write_text(json.dumps(doc), encoding="utf-8")
    different = load_comparison(comparison_manifest)
    with pytest.raises(ValueError, match="même checkpoint"):
        comparison_values(*different.predictions, 50, "z_sensitivity")


def test_neutral_packet_is_deterministic_and_contains_only_ct(tmp_path, monkeypatch):
    folder = Path(__file__).parents[1]/"docs"/"validation"
    monkeypatch.syspath_prepend(str(folder))
    phase8 = pytest.importorskip("phase8_review")
    cube = np.zeros((62, 4, 6), "u1")
    cube[31] = np.arange(24, dtype="u1").reshape(4, 6)
    zip_path = tmp_path/"review.zip"
    samples = [("R03", [3, 7], cube)]
    phase8.export_blind(zip_path, samples, "s3://test/surface")
    first = zip_path.read_bytes()
    phase8.export_blind(zip_path, samples, "s3://test/surface")
    assert zip_path.read_bytes() == first
    with ZipFile(zip_path) as archive:
        assert set(archive.namelist()) == {
            "R03/ct-ZVU.tif", "R03/ct-59.tif", "R03/valid-mask.tif", "LIRE.txt", "ct-provenance.json",
        }
        row, = json.loads(archive.read("ct-provenance.json"))["regions"]
        assert row["start_vu"] == [3, 7] and row["stop_vu"] == [7, 13]
