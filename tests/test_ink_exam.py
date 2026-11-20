import json
from dataclasses import replace
from hashlib import sha256
from zipfile import ZipFile

import numpy as np
import pytest
import tifffile
from test_comparison import comparison_fixture  # noqa: F401

from vesuvius_data_explorer.core.comparison import (
    Candidate,
    ComparisonView,
    load_comparison,
    load_comparison_session,
)
from vesuvius_data_explorer.core.ink_disagreement import correlations, shift_metrics, top_masks
from vesuvius_data_explorer.core.ink_exam import (
    candidate_id,
    export_examination,
    propose_candidates,
    review_stage,
)


def test_ct_order_preserves_uv_type_support_and_source():
    pilot = pytest.importorskip("docs.validation.phase6_cuda")
    shape, prepare_tile = pilot.SHAPE, pilot.prepare_tile
    a = np.zeros(shape, "u1")
    a[0, 4, 7], a[-1, 4, 7], a[0, 7, 4] = 255, 50, 25
    normal, valid = prepare_tile(a)
    reversed_z, reversed_valid = prepare_tile(a, reverse=True)
    assert normal.shape == (1, 1, *shape) and normal.dtype == np.float32
    assert normal[0, 0, 0, 4, 7] == 1 and reversed_z[0, 0, 0, 4, 7] == 0.25
    assert reversed_z[0, 0, -1, 7, 4] == 0.125
    np.testing.assert_array_equal(normal[:, :, ::-1], reversed_z)
    np.testing.assert_array_equal(valid, reversed_valid)
    assert valid.sum() == 2 and a[0, 4, 7] == 255
    with pytest.raises(ValueError, match="uint8"):
        prepare_tile(a.astype("u2"))


def test_midrank_and_top_k_preserve_ties_and_exclude_non_finite():
    a, b = np.array([[0., 2., 2., np.nan, 9.]]), np.array([[5., 3., 3., 1., np.inf]])
    a_mask, b_mask = top_masks(a, b, np.ones_like(a, bool), 1/3)
    np.testing.assert_array_equal(a_mask, [[False, True, True, False, False]])
    np.testing.assert_array_equal(b_mask, [[True, False, False, False, False]])
    r = correlations(a, b)
    assert r["paired_pixels"] == 3
    assert r["pearson"] == pytest.approx(-1) and r["spearman"] == pytest.approx(-1)
    assert correlations(a, np.ones_like(a))["spearman"] is None


def test_known_translation_and_reflection_in_asymmetric_control():
    a = np.zeros((8, 10))
    a[1, 2], a[2, 3], a[4, 2] = 7, 8, 9
    b = np.zeros_like(a)
    b[2, 4], b[3, 5], b[5, 4] = 7, 8, 9
    valid = np.ones_like(a, bool)
    pair = top_masks(a, b, valid, 0.03)
    assert shift_metrics(a, b, valid, pair, (0, 0))["top"]["both_positive"] == 0
    aligned = shift_metrics(a, b, valid, pair, (-1, -2))
    assert aligned["top"]["both_positive"] == 3 and aligned["top"]["jaccard"] == 1
    assert aligned["paired_pixels"] == 56 and aligned["spearman"] == pytest.approx(1)
    reflected = shift_metrics(a, b[:, ::-1], valid, (pair[0], pair[1][:, ::-1]), (-1, -2))
    assert reflected["top"]["jaccard"] < 1
    with pytest.raises(ValueError, match="portée"):
        shift_metrics(a, b, valid, pair, (0, 10))


def test_proposals_use_distinct_tiles_and_repeat_exactly(comparison_manifest):
    c = load_comparison(comparison_manifest)
    p = propose_candidates(c, (1, 2), (0, 0, 4, 5), side=2)
    assert p and p == propose_candidates(c, (1, 2), (0, 0, 4, 5), side=2)
    assert len({item.roi for item in p}) == len(p)
    assert all(item.selection and item.models == (1, 2) and not item.hypothesis for item in p)
    assert all(review_stage(item) != "caractere_valide_par_expertise" for item in p)


def test_portable_examination_and_independent_validation(comparison_manifest, tmp_path):
    c = load_comparison(comparison_manifest)
    candidate = Candidate("Trace", (0, 0, 2, 2), models=(1, 2), observation="Trace observée")
    assert review_stage(candidate) == "trace_observee"
    hypothetical = replace(candidate, ink_candidate=True, hypothesis="Hypothèse")
    assert review_stage(hypothetical) == "caractere_hypothetique"
    reviewed = replace(hypothetical, reviewer="Spécialiste", evidence="doi:validation",
                       palaeography_reference="doi:édition", character_confirmed=True)
    assert candidate_id(c, candidate) == candidate_id(c, reviewed)
    view = ComparisonView(0, (1, 2), 50, 100, True, candidate.roi, (reviewed,))
    path = tmp_path/"out.zip"
    with pytest.raises(ValueError, match="références"):
        export_examination(path, c, replace(view, candidates=(replace(reviewed, palaeography_reference=""),)))
    assert not path.exists()
    export_examination(path, c, view)
    first = path.read_bytes()
    export_examination(path, c, view)
    assert path.read_bytes() == first
    restored = tmp_path/"restored"
    with ZipFile(path) as archive:
        index = json.loads(archive.read("examen.json"))
        assert index["samples"][0]["stage"] == "caractere_valide_par_expertise"
        assert all(sha256(archive.read(f)).hexdigest() == h for f, h in index["sha256"].items())
        archive.extractall(restored)
    loaded, state = load_comparison_session(restored/"session.json")
    assert loaded.manifest_sha256 == c.manifest_sha256 and state == view
    np.testing.assert_array_equal(loaded.ct.pixels, c.ct.pixels)
    tifffile.imwrite(c.ct.path, np.ones_like(c.ct.pixels), photometric="minisblack")
    with pytest.raises(ValueError, match="ont changé"):
        export_examination(path, c, view)
    with ZipFile(path) as archive:
        assert archive.testzip() is None
