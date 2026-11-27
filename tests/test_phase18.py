"""Offline controls for the phase 18 protocol, tiling, supports and paired bootstrap."""

import json
from pathlib import Path

import numpy as np
import pytest
from scipy import ndimage


@pytest.fixture
def phase(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "docs/validation"))
    import phase18_eval
    return phase18_eval


def test_frozen_protocol(phase, tmp_path):
    path = tmp_path / phase.PROTOCOL.name
    path.write_bytes(phase.PROTOCOL.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    protocol = phase.read_protocol(path)
    assert protocol["support_N"]["tolerance_um"] == 301
    assert len(phase.combinations(protocol)) == 216
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError):
        phase.read_protocol(path)


def test_z_reversal_only_changes_plane_order(phase):
    assert phase.plane_indices((2, 63), "Z_out") == list(range(62, 0, -1))  # layers 63 -> 02
    assert phase.plane_indices((2, 63), "Z_in") == list(range(1, 63))
    assert phase.plane_indices((1, 62), "Z_out") == list(range(61, -1, -1))
    stack = np.random.default_rng(0).integers(0, 255, (63, 4, 4), dtype=np.uint8)
    out, inn = stack[phase.plane_indices((2, 63), "Z_out")], stack[phase.plane_indices((2, 63), "Z_in")]
    np.testing.assert_array_equal(out, inn[::-1])


def test_compact_preparation_preserves_padded_stack_and_baselines(phase, tmp_path, monkeypatch):
    from PIL import Image

    protocol = phase.read_protocol()
    source = tmp_path / "source"
    (source / "layers").mkdir(parents=True)
    height, width = 24, 35
    row, col = np.indices((height, width))
    protocol["fragment"].update(base_url=source.as_uri() + "/", canvas_shape_hw=[height, width])
    mask = np.full((height, width, 4), 255, dtype=np.uint8)
    mask[0, :, 3] = 0
    Image.fromarray(mask).save(source / protocol["fragment"]["mask"])
    for k in range(1, 64):
        Image.fromarray((row + 2 * col + k).astype(np.uint8)).save(source / "layers" / f"{k:02}.png")

    stacks = []
    baselines = []
    manifests = []
    for name, compact in [("dense", False), ("compact", True)]:
        work = tmp_path / name
        manifest = tmp_path / f"{name}.json"
        monkeypatch.setattr(phase, "PREPARE_JSON", manifest)
        protocol["work_dir"] = str(work)
        phase.prepare(protocol, compact_stack=compact)
        stack = phase.open_stack(protocol)
        assert tuple(stack.shape) == (63, 256, 256)
        assert stack.dtype == np.uint8
        if compact:
            assert (work / "layers01_63.zarr").is_dir()
            assert not (work / "layers01_63.npy").exists()
        for window, order, first, last in [((2, 63), "Z_out", 63, 2), ((1, 62), "Z_in", 1, 62)]:
            tile = phase.read_stack_window(stack, window, order, slice(5, 32), slice(7, 48))
            np.testing.assert_array_equal(tile[[0, -1], 0, 0], [19 + first, 19 + last])
            assert not tile[:, -1].any() and not tile[:, :, -1].any()
        stacks.append(np.asarray(stack))
        phase.baselines(protocol)
        baselines.append([np.load(work / f"{key}.npy") for key in ("B1", "B2")])
        manifests.append(json.loads(manifest.read_text()))

    np.testing.assert_array_equal(*stacks)
    np.testing.assert_array_equal(*baselines)
    assert manifests[0]["files_sha256"] == manifests[1]["files_sha256"]
    assert manifests[0]["run_tiles"] == manifests[1]["run_tiles"] == {"128": 1, "256": 1}


@pytest.mark.parametrize("stride, overlap", [(256, 1), (128, 4)])
def test_strides_tile_the_padded_canvas(phase, stride, overlap):
    shape = (300, 520)
    shape_p = phase.padded_shape(shape)
    assert shape_p == (512, 768)
    count = np.zeros(shape_p, int)
    for v, u in phase.tile_origins(shape_p, stride):
        count[v:v + 256, u:u + 256] += 1
    interior = count[256:-256, 256:-256] if stride == 128 else count
    assert count.min() >= 1 and (interior == overlap).all()
    mask = np.zeros(shape, bool)
    mask[10:20, 10:20] = True
    mask[-1, -1] = True
    kept = phase.run_tiles(mask, stride)
    assert kept == ([(0, 0), (128, 384), (128, 512), (256, 384), (256, 512)] if stride == 128
                    else [(0, 0), (256, 512)])
    assert phase.coverage(shape, kept)[mask].all()


def test_grid_reductions(phase):
    values = np.arange(36, dtype=float).reshape(6, 6)
    np.testing.assert_allclose(phase.reduce_mean(values, (2, 3)), [[6.5, 8.5, 10.5], [24.5, 26.5, 28.5]])
    values[0, 0] = np.nan
    reduced = phase.reduce_mean(values, (2, 3), finite_share=0.5)
    assert reduced[0, 0] == pytest.approx(np.mean([1, 6, 7, 12, 13]))
    assert np.isnan(phase.reduce_mean(np.full((4, 4), np.nan), (2, 2), finite_share=0.5)).all()
    binary = np.zeros((4, 4), bool)
    binary[0, 0] = True
    assert phase.reduce_binary(binary, (2, 2), "any")[0, 0]
    assert not phase.reduce_binary(binary, (2, 2), "area_half")[0, 0]
    assert phase.reduce_nearest(np.arange(16).reshape(4, 4), (2, 2)).tolist() == [[5, 7], [13, 15]]
    assert phase.grid_shape((13924, 8416), 0.2564, "round") == (3570, 2158)
    assert phase.grid_shape((13924, 8416), 0.2564, "floor") == (3570, 2157)


@pytest.mark.parametrize("metric, structure", [("taxicab", None), ("chessboard", np.ones((3, 3), bool))])
def test_erosion_metrics_match_iterated_erosion(phase, metric, structure):
    binary = np.random.default_rng(1).random((40, 40)) > 0.25
    binary = ndimage.binary_closing(binary, iterations=2)
    expected = ndimage.binary_erosion(binary, structure=structure, iterations=2, border_value=0)
    np.testing.assert_array_equal(phase.erode(binary, 2, metric), expected)


def test_distance_to_letters(phase):
    letters = np.zeros((30, 30), bool)
    letters[15, 15] = True
    far = phase.distance_to(letters, "euclidean") >= 12
    assert not far[15, 26] and far[15, 27] and far[0, 0]
    assert phase.erode(np.ones((5, 5), bool), 2, "euclidean")[2, 2]  # Image edges count as background.
    assert not phase.erode(np.ones((5, 5), bool), 2, "euclidean")[1, 2]


def synthetic_fragment(seed=0, shape=(900, 800)):
    rng = np.random.default_rng(seed)
    mask = np.zeros(shape, bool)
    mask[40:-40, 50:-50] = True
    labels = np.zeros(shape, bool)
    for r, c in rng.integers(150, 600, (10, 2)):
        labels[r:r + 40, c:c + 90] = True
    labels &= mask
    luma = rng.normal(100, 10, shape).astype(np.float32) - 40 * labels
    covered = np.ones(shape, bool)
    return labels, luma, mask, covered


def test_support_e_search_recovers_the_generating_interpretation(phase):
    protocol = phase.read_protocol()
    combos = phase.combinations(protocol)
    builders = {"A": phase.SupportE(*synthetic_fragment(0), 0.2564),
                "B": phase.SupportE(*synthetic_fragment(1, (860, 940)), 0.2564)}
    target = 101
    published = {"A": builders["A"].build(combos[target])["counts"],
                 "B": {k: v for k, v in builders["B"].build(combos[target])["counts"].items() if k != "valid"}}
    protocol["support_E"]["published_counts"] = published
    selection = phase.select_combination(protocol, builders)
    assert selection["status"] == "reconstructed"
    assert len(selection["combinations"]) == 216
    best = selection["combinations"][selection["selected"]]
    assert best["max_relative_error"] == 0 and selection["selected"] <= target
    support = builders["A"].build(combos[target])
    assert not (support["ink"] & support["clean"]).any()
    assert (support["clean"] <= support["clean_no_ir"]).all() and (support["ink"] <= support["region"]).all()


def test_quantisation_between_percentiles(phase):
    score = np.linspace(0, 1, 10001).reshape(1, -1)
    q = phase.quantize(score, np.ones_like(score, bool))
    assert q.min() == 0 and q.max() == 255 and q.dtype == np.int16
    assert (np.diff(q[0]) >= 0).all()


def test_paired_component_bootstrap(phase):
    rng = np.random.default_rng(2)
    labels, *_ = synthetic_fragment(3)
    evaluated = np.ones_like(labels)
    negatives = evaluated & ~ndimage.binary_dilation(labels, iterations=5)
    positives = labels
    perfect = np.where(labels, 0.9, 0.1) + rng.normal(0, 0.01, labels.shape)
    noise = rng.random(labels.shape)
    maps = {"Z_out_s128": phase.binned(perfect), "Z_in_s128": phase.binned(noise),
            "B1": phase.binned(noise), "B2": phase.binned(rng.random(labels.shape))}
    units, n_units = phase.attach_units(positives, positives | negatives, step=4)
    assert (units[positives] > 0).all() and (units[negatives] > 0).all()
    components, count = ndimage.label(positives, structure=np.ones((3, 3)))
    assert n_units == count and (units[positives] == components[positives]).all()
    estimate, per_draw = phase.bootstrap(maps, positives, negatives, units, n_units, phase.BINS, 99, 218)
    np.testing.assert_array_equal(per_draw["Z_in_s128"], per_draw["B1"])  # Same draws for every score.
    assert estimate["Z_out_s128"][1] == pytest.approx(1.0)
    verdict = phase.hypotheses(estimate, per_draw)
    assert verdict["H1"]["supported"] and verdict["H2"]["supported"] and verdict["H3"]["supported"]


def test_tiling_interaction_uses_the_same_draw_for_all_four_conditions(phase):
    roc = {"Z_out_s128": 0.9, "Z_in_s128": 0.6, "Z_out_s256": 0.8, "Z_in_s256": 0.6}
    estimate = {name: (0.5, value) for name, value in roc.items()}
    common_variations = np.array([-0.1, 0.0, 0.05])
    per_draw = {name: np.column_stack(([0.5] * 3, value + common_variations)) for name, value in roc.items()}
    interaction = phase.tiling_interaction(estimate, per_draw)
    assert interaction["estimate"] == pytest.approx(0.1)
    assert interaction["interval_95"] == pytest.approx([0.1, 0.1])


def test_placement_test_ranks_true_letters_first(phase):
    labels, luma, mask, covered = synthetic_fragment(4)
    protocol = phase.read_protocol()
    combo = phase.combinations(protocol)[0]
    support = phase.SupportE(labels, luma, mask, covered, 0.2564).build(combo)
    region = support["region"]
    score = np.where(phase.erode(support["letters"], 2, "euclidean"), 0.9, 0.1)
    maps = {"Z_out_s128": phase.quantize(score, region), "Z_in_s128": phase.quantize(1 - score, region)}
    result = phase.placement_test(maps, support, 50, 1802, 8, "euclidean")
    defined = result["Z_out_s128"]["defined_rolls"]
    assert defined >= 25 and result["Z_out_s128"]["true_beats"] >= defined - 2
    assert result["Z_in_s128"]["true_ROC_AUC"] < 0.5


def test_maps_must_match_their_frozen_hashes(phase, tmp_path, monkeypatch):
    protocol = {"work_dir": str(tmp_path), "inputs": {"maps": {"Z_out_s128": {}}}}
    for name in ("Z_out_s128", "B1", "B2", "weight_s128"):
        np.save(tmp_path / f"{name}.npy", np.zeros(3, np.float32))
    scores = tmp_path / "scores.json"
    monkeypatch.setattr(phase, "SCORES_JSON", scores)
    with pytest.raises(ValueError, match="missing"):
        phase.check_maps(protocol)
    frozen = {n: {"sha256": phase.sha(tmp_path / f"{n}.npy")} for n in ("Z_out_s128", "B1", "B2", "weight_s128")}
    scores.write_text(json.dumps({"maps": frozen}))
    phase.check_maps(protocol)
    np.save(tmp_path / "B1.npy", np.ones(3, np.float32))
    with pytest.raises(ValueError, match="B1"):
        phase.check_maps(protocol)


def test_large_published_images_open(phase, tmp_path, monkeypatch):
    from PIL import Image

    labels = np.zeros((40, 50), np.uint8)
    labels[5:9, 5:20] = 255
    Image.fromarray(labels).save(tmp_path / "labels.png")
    rgba = np.zeros((40, 50, 4), np.uint8)
    rgba[..., :3], rgba[10:30, 10:40, 3] = 255, 255
    Image.fromarray(rgba, "RGBA").save(tmp_path / "mask.png")
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 10)  # Every image above is a "bomb" for PIL now.
    assert phase.load_grey(tmp_path / "labels.png").sum() == 60
    assert phase.load_luma(tmp_path / "labels.png").dtype == np.float32
    assert phase.load_mask(tmp_path / "mask.png").sum() == 600
