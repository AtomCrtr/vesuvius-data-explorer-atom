import json
from hashlib import sha256
from zipfile import ZipFile

import numpy as np
import pytest
import tifffile

from vesuvius_data_explorer.core.multimodal import LAYER_ROLES, export_multimodal, load_multimodal
from vesuvius_data_explorer.core.optical_registration import (
    Grid,
    landmarks_fit,
    spatial_uncertainty,
    transform,
    warp_optical,
)
from vesuvius_data_explorer.core.optical_validation import (
    evaluate_registered,
    geometry_sha256,
    independence_status,
    measures,
)


def _landmarks(source, target, *, reflection=False):
    positions = [(4,4), (4,24), (24,4), (24,24), (11,11), (12,21), (21,12)]
    return [{"id": str(i), "split": "fit" if i < 4 else "check", "feature": "structural junction",
             "optical_yx": list(p),
             "ct_vu": target.pixels(source.physical(p) * [1, -1 if reflection else 1] + [1, 28 if reflection else 1]).tolist()}
            for i,p in enumerate(positions)]


def test_pitch_origin_and_inverse_are_applied_in_physical_units():
    optical = Grid((30,30), (1., 1.), (5., -4.))
    ct = Grid((30,30), (1.5, 2.), (2., -3.))
    points = _landmarks(optical, ct)
    fit = landmarks_fit(points, optical, ct, feature_um=20.)
    np.testing.assert_allclose(np.asarray(fit["ct_from_optical_um"])[:2,2], 1.)
    actual = optical.physical((4, 12))
    matrix, inverse = [np.asarray(fit[key]) for key in ("ct_from_optical_um", "optical_from_ct_um")]
    np.testing.assert_allclose(transform(inverse, transform(matrix, actual)), actual)
    assert fit["check_rms_um"] < 1e-9
    with pytest.raises(ValueError, match="calibrated"):
        Grid((10, 10), (.6879, 0.))


def test_reserved_landmarks_fail_gate_and_never_change_fit():
    grid = Grid((30,30), (1., 1.))
    points = _landmarks(grid, grid)
    fit = landmarks_fit(points, grid, grid, feature_um=15.)
    assert fit["quality_gate"]
    points[-1]["ct_vu"][0] -= 8
    bad = landmarks_fit(points, grid, grid, feature_um=15.)
    assert not bad["quality_gate"]
    np.testing.assert_equal(fit["ct_from_optical_um"], bad["ct_from_optical_um"])
    with pytest.raises(ValueError, match="independent check"):
        landmarks_fit(points[:6], grid, grid, feature_um=15.)
    with pytest.raises(ValueError, match="distinct IDs"):
        landmarks_fit([*points[:-1],points[0]], grid, grid, feature_um=15.)


def test_reflection_is_explicit_and_uncertainty_masks_extrapolation():
    grid = Grid((30,30), (1., 1.))
    points = _landmarks(grid, grid, reflection=True)
    ok = landmarks_fit(points, grid, grid, feature_um=12., parity=-1)
    assert ok["quality_gate"] and np.linalg.det(np.asarray(ok["ct_from_optical_um"])) < 0
    assert not landmarks_fit(points, grid, grid, feature_um=12.)["quality_gate"]
    with pytest.raises(ValueError, match="reflection"):
        landmarks_fit(points, grid, grid, feature_um=12., kind="affine")
    raster = np.eye(30)
    valid = np.ones(raster.shape, bool)
    valid[10,12] = False
    mapped, usable = warp_optical(raster,grid,grid,ok,support=valid,discrete=True)
    confidence = spatial_uncertainty(grid,ok,usable)
    assert not usable[0,0] and not usable[11,16]
    assert np.isnan(mapped[11,16]) and np.isnan(confidence[0,0])
    assert np.isfinite(confidence[usable]).all()


def test_independence_tracks_same_manuscript_and_derivatives():
    ref = {"manuscript": "500", "sample": "ν2", "sha256": "a"}
    assert independence_status(ref, []) == "unknown"
    assert independence_status(ref, [{"manuscript": "500", "sample": "IR #017", "sha256": "b"}]) == "same_manuscript"
    assert independence_status(ref, [{"manuscript": "other", "ancestors": ["a"]}]) == "same_source"
    assert independence_status(ref, [{"manuscript": "501", "sha256": "c"}], exhaustive=True) == "independent"


def test_metrics_handle_ties_absent_classes_and_frozen_quality_gate():
    s = np.array([[.9,.6,.6,.1]])
    y = np.array([[True,True,False,False]])
    valid = np.ones_like(y)
    result = measures(s,y,valid)
    mid = result["thresholds"][2]
    assert (mid["tp"],mid["fp"],mid["tn"],mid["fn"]) == (2,1,1,0)
    assert result["curves"]["roc_auc"] == pytest.approx(.875)
    assert measures(s,y,~y)["curves"] is None
    pair = {"A+":s, "A-":s[...,::-1]}
    with pytest.raises(ValueError, match="frozen geometry"):
        evaluate_registered(pair,y,valid,(1.,1.),{"quality_gate":True},{"face":"probable"},"unknown")
    gate = {"quality_gate":True,"check_p90_um":1.}
    identity = {"location":"confirmed","scale":"confirmed","face":"confirmed"}
    identity["frozen_geometry_sha256"] = geometry_sha256(gate, identity, (1.,1.), valid)
    evaluation = evaluate_registered(pair,y,valid,(1.,1.),gate,identity,"unknown")
    assert evaluation["status"] == "exploratory"
    assert len(evaluation["translations"]) == 2
    with pytest.raises(ValueError, match="frozen geometry"):
        evaluate_registered(pair,y,~valid,(1.,1.),gate,identity,"unknown")


@pytest.fixture
def multimodal_path(tmp_path):
    files = {}
    for name in LAYER_ROLES:
        shape = (30, 30, 3) if name == "brightfield" else (30, 30)
        path = tmp_path/f"{name}.tif"
        tifffile.imwrite(path, np.ones(shape, "u1"), photometric="rgb" if name == "brightfield" else "minisblack")
        files[name] = {"path": path.name, "sha256": sha256(path.read_bytes()).hexdigest()}
    grid = {"pitch_um": [1.,1.], "origin_um": [0.,0.]}
    doc = {"version": 1, "files": files, "ct": grid, "optical": grid, "summary_fr": "Exemple",
           "identity": {"location": "unverified", "scale": "unverified", "face": "indeterminate"},
           "landmarks": []}
    path = tmp_path/"validation.json"
    path.write_text(json.dumps(doc),encoding="utf8")
    return path


def test_export_keeps_hashes_and_does_not_register_an_unlocalized_field(multimodal_path,tmp_path):
    destination = tmp_path/"review.zip"
    export_multimodal(multimodal_path,destination)
    root = tmp_path/"copy"
    with ZipFile(destination) as archive:
        assert archive.testzip() is None
        archive.extractall(root)
    _, _, _, layers, fit = load_multimodal(root/multimodal_path.name)
    assert set(layers) == set(LAYER_ROLES) and fit is None
    (root/"ct.tif").write_bytes(b"invalid")
    with pytest.raises(ValueError,match="Empreinte"):
        load_multimodal(root/multimodal_path.name)


def test_multimodal_uses_registered_layers_only_with_scale_and_location_proof(multimodal_path):
    doc = json.loads(multimodal_path.read_bytes())
    grid = Grid((30,30),(1.,1.))
    doc["landmarks"] = _landmarks(grid,grid)
    doc["geometry"] = {"kind":"rigid","parity":1,"feature_um":10.}
    multimodal_path.write_text(json.dumps(doc), encoding="utf8")
    assert "uncertainty" not in load_multimodal(multimodal_path)[3]
    doc["identity"].update({"scale":"confirmed","location":"confirmed"})
    multimodal_path.write_text(json.dumps(doc), encoding="utf8")
    _,_,_,images,report = load_multimodal(multimodal_path)
    assert report["quality_gate"] and np.isfinite(images["registered_height"]).any()
    assert np.isnan(images["uncertainty"][0,0])


def test_napari_open_validation_keeps_unlocalized_modalities_separate(multimodal_path, monkeypatch, request):
    napari = pytest.importorskip("napari")
    pytest.importorskip("pytestqt")
    from vesuvius_data_explorer.napari import multimodal
    from vesuvius_data_explorer.napari.comparison_widget import ComparisonWidget

    qtbot = request.getfixturevalue("qtbot")
    viewer = napari.Viewer(show=False)
    try:
        widget = ComparisonWidget(viewer)
        qtbot.addWidget(widget)
        monkeypatch.setattr(multimodal.QFileDialog, "getOpenFileName", lambda *a, **kw: (str(multimodal_path), "JSON"))
        widget.multimodal_button.click()
        qtbot.waitUntil(lambda: len(viewer.layers) == 7, timeout=10000)
        layers = {layer.metadata["validation_role"]:layer for layer in viewer.layers}
        assert layers["ct"].visible and layers["brightfield"].visible
        assert layers["brightfield"].translate[1] > 30.
        assert not any(layers[key].visible for key in ("ink_mask","a_plus","a_minus"))
        widget.findChild(multimodal.QDialog).findChild(multimodal.QCheckBox).setChecked(True)
        assert layers["ink_mask"].visible and layers["a_plus"].visible
    finally:
        viewer.close()
