"""Alignment profile (T5.1) on a synthetic volume of parallel sheets."""

import json

import numpy as np
import pytest
import zarr

from vesuvius_data_explorer.core.alignment import (
    alignment_metrics,
    choose_level,
    half_range_voxels,
    normal_profiles,
    shift_surface,
)
from vesuvius_data_explorer.core.tifxyz import TifxyzSurface
from vesuvius_data_explorer.qc import run_surface
from vesuvius_data_explorer.qc.report import validate_report
from vesuvius_data_explorer.qc.thresholds import load_thresholds

SPACING = 24  # Bright sheets at z = 0, 24, 48, 72.


def sheets(shape=(96, 64, 64), seed=0):
    z = np.arange(shape[0])[:, None, None]
    distance = (z + SPACING // 2) % SPACING - SPACING // 2
    volume = 50 + 100 * np.exp(-(distance**2) / (2 * 2.0**2)) + np.zeros(shape)
    volume += np.random.default_rng(seed).normal(0, 5, shape)
    return volume.astype(np.float32)


def pyramid(volume, levels=3):
    arrays = [volume]
    for _ in range(levels - 1):
        a = arrays[-1]
        z, y, x = (n // 2 * 2 for n in a.shape)
        arrays.append(a[:z, :y, :x].reshape(z // 2, 2, y // 2, 2, x // 2, 2).mean(axis=(1, 3, 5)))
    return arrays, [a.shape for a in arrays]


def plane(z=48.0, rows=30, cols=30, x0=2.0):
    """Flat segment on the sheet at z = 48; its grid normal points towards -z."""
    row, col = np.mgrid[:rows, :cols].astype(float)
    points = np.stack([np.full_like(row, z), 2 * row + 2, 2 * col + x0], axis=-1)
    return TifxyzSurface(points, {}, (rows, cols), 1, "plan", 0)


@pytest.fixture(scope="module")
def volume():
    return pyramid(sheets())


def test_default_draws_36_patches_or_all_usable_ones(volume):
    profile = normal_profiles(plane(rows=60, cols=60), *pyramid(sheets((96, 128, 128))))
    assert len(profile.patch_profiles) == 36 and not profile.warnings
    small = normal_profiles(plane(), *volume)  # 30 x 30 grid: 25 patches of 6 x 6
    assert len(small.patch_profiles) == 25
    assert "25 patch(s) utilisable(s) sur 36" in small.warnings[0]


def test_level_and_range_follow_the_voxel_size(volume):
    _, shapes = volume
    assert choose_level(shapes, None) == 0
    assert choose_level(shapes, 5.0) == 1  # 5 and 10 µm fit, 20 µm does not
    assert choose_level(shapes, 2.0) == 2
    assert choose_level(shapes, 20.0) == 0
    assert half_range_voxels(None) == 24
    assert half_range_voxels(5.0) == 40


def test_aligned_segment_peaks_at_zero(volume):
    profile = normal_profiles(plane(), *volume, patches=12)
    metrics = alignment_metrics(profile)
    assert profile.level == 0 and len(profile.patch_profiles) == 12 and profile.points == 432
    assert metrics["peak_offset"] == 0
    assert metrics["bootstrap_iqr"] == [0, 0]
    assert metrics["peak_prominence"] > 3
    assert not profile.warnings


@pytest.mark.parametrize("shift", [-8, -5, 5, 8])
def test_peak_follows_an_imposed_shift(volume, shift):
    # Moving the segment by +k along its normal (-z) puts the sheet at offset -k.
    metrics = alignment_metrics(normal_profiles(shift_surface(plane(), shift), *volume))
    assert metrics["peak_offset"] == pytest.approx(-shift, abs=1)


def test_coarser_level_with_known_voxel_size(volume):
    profile = normal_profiles(plane(), *volume, pixel_size_um=5.0)
    metrics = alignment_metrics(profile)
    assert profile.level == 1 and profile.half_range == 40
    assert np.diff(profile.offsets) == pytest.approx(2)
    assert metrics["peak_offset"] == pytest.approx(0, abs=2)


def test_incoherent_patches_flatten_the_profile(volume):
    aligned = alignment_metrics(normal_profiles(plane(), *volume, patches=12))
    shifts = np.random.default_rng(1).uniform(-12, 12, 12)
    scrambled = alignment_metrics(normal_profiles(plane(), *volume, patches=12,
                                                  patch_shifts=shifts))
    assert scrambled["peak_prominence"] < aligned["peak_prominence"] / 2
    assert scrambled["bootstrap_width"] > aligned["bootstrap_width"]


def test_budget_reduces_patches_then_refuses(volume):
    full = normal_profiles(plane(), *volume, patches=12)
    per_patch = full.voxels_read // len(full.patch_profiles)
    reduced = normal_profiles(plane(), *volume, patches=12,
                              max_voxels=3 * per_patch + per_patch // 2)
    assert len(reduced.patch_profiles) == 3 and reduced.voxels_read <= 3.5 * per_patch
    assert "Budget : 3 patch(s)" in reduced.warnings[-1]
    with pytest.raises(ValueError, match="insuffisant"):
        normal_profiles(plane(), *volume, max_voxels=10)


def test_patches_outside_the_volume_are_excluded(volume):
    # x from 40 to 98: only the first 12 columns (two patch columns) are inside x < 64.
    profile = normal_profiles(plane(x0=40.0), *volume, patches=12)
    assert (profile.patch_centers[:, 2] < 64).all()
    assert len(profile.patch_profiles) == 10
    assert "10 patch(s) utilisable(s) sur 12" in profile.warnings[0]
    with pytest.raises(ValueError, match="Aucun patch"):
        normal_profiles(plane(x0=70.0), *volume)


def alignment_result(report):
    validate_report(report)
    return {r["check_id"]: r for r in report["results"]}["surface.alignment"]


def test_qc_check_warns_beyond_30_um_on_reliable_measures(volume):
    """T5.3 (PO decision): warn when prominence >= 1.0 and the sheet is more than 30 µm away."""
    shifted = shift_surface(plane(), 10)  # 10 voxels of 5 µm = 50 µm
    report = run_surface("plan", surface=shifted, volume=volume, pixel_size_um=5.0)
    result = alignment_result(report)
    assert result["status"] == "warn" and result["value"] == pytest.approx(-10, abs=1)
    assert "au-delà de 30 µm" in result["message"]
    assert report["parameters"]["alignment"]["patches"] == 25  # all usable patches (36 asked)
    assert report["parameters"]["volume_shape"] == [96, 64, 64]
    close = alignment_result(run_surface("plan", surface=shift_surface(plane(), 4),
                                         volume=volume, pixel_size_um=5.0))  # 20 µm
    assert close["status"] == "pass" and "dans les 30 µm" in close["message"]


def test_qc_check_is_not_graded_without_voxel_size_or_when_disabled(volume, tmp_path):
    shifted = shift_surface(plane(), 10)
    unknown = alignment_result(run_surface("plan", surface=shifted, volume=volume))
    assert unknown["status"] == "pass" and "taille de voxel inconnue" in unknown["message"]
    config = tmp_path / "off.toml"
    config.write_text('["surface.alignment"]\nenabled = 0\n')
    disabled = alignment_result(run_surface("plan", surface=shifted, volume=volume,
                                            pixel_size_um=5.0, thresholds=load_thresholds(config)))
    assert disabled["status"] == "pass" and "enabled = 0" in disabled["message"]
    config.write_text('["surface.alignment"]\nenabled = 2\n')
    with pytest.raises(ValueError, match="enabled vaut 0 ou 1"):
        load_thresholds(config)
    config.write_text('["surface.alignment"]\nmax_offset_um = 60\n')
    relaxed = alignment_result(run_surface("plan", surface=shifted, volume=volume,
                                           pixel_size_um=5.0, thresholds=load_thresholds(config)))
    assert relaxed["status"] == "pass"


@pytest.mark.parametrize("metrics, pixel, status, note", [
    ({"peak_offset": None, "peak_prominence": None}, 5.0, "skipped", "indéterminé"),
    ({"peak_offset": -10.0, "peak_prominence": 0.6}, 5.0, "pass", "peu fiable"),
    ({"peak_offset": -10.0, "peak_prominence": None}, 5.0, "pass", "peu fiable"),
    ({"peak_offset": -10.0, "peak_prominence": 1.0}, 5.0, "warn", "50 µm"),
    ({"peak_offset": 6.0, "peak_prominence": 2.0}, 5.0, "pass", "30 µm"),
    ({"peak_offset": -10.0, "peak_prominence": 2.0}, None, "pass", "inconnue"),
])
def test_grade_alignment_rule(metrics, pixel, status, note):
    from vesuvius_data_explorer.qc.checks import grade_alignment

    threshold = load_thresholds()["surface.alignment"]
    assert dict(threshold) == {"enabled": 1.0, "max_offset_um": 30.0, "min_prominence": 1.0}
    got_status, got_note = grade_alignment(metrics, pixel, threshold)
    assert got_status == status and note in got_note


def test_qc_reports_why_the_profile_is_impossible(volume):
    report = run_surface("plan", surface=plane(x0=70.0), volume=volume)
    result = {r["check_id"]: r for r in report["results"]}["surface.alignment"]
    assert result["status"] == "skipped" and "Aucun patch" in result["message"]


def test_cli_volume_option(volume, tmp_path):
    from vesuvius_data_explorer.cli import main

    root = zarr.open_group(str(tmp_path / "sheets.zarr"), mode="w", zarr_format=2)
    datasets = []
    for index, array in enumerate(volume[0]):
        root.create_array(str(index), shape=array.shape, dtype="float32", chunks=(16, 32, 32))
        root[str(index)][:] = array
        datasets.append({"path": str(index), "coordinateTransformations": [
            {"type": "scale", "scale": [2.0**index] * 3}]})
    root.attrs["multiscales"] = [{"axes": ["z", "y", "x"], "datasets": datasets}]
    segment = tmp_path / "seg"
    segment.mkdir()
    for axis, name in enumerate("zyx"):
        np.save(segment / f"{name}.npy", plane().points[..., axis])
    output = tmp_path / "report.json"
    assert main(["surface", str(segment), "--volume", str(tmp_path / "sheets.zarr"),
                 "--pixel-size-um", "5", "-o", str(output)]) == 0
    report = json.loads(output.read_text())
    result = {r["check_id"]: r for r in report["results"]}["surface.alignment"]
    assert result["status"] == "pass" and abs(result["value"]) <= 2
    assert "µm" in result["message"] and report["parameters"]["alignment"]["level"] == 1


@pytest.mark.network
def test_real_segment_sits_close_to_its_sheet():
    from vesuvius_data_explorer.core.tifxyz import load_tifxyz
    from vesuvius_data_explorer.core.volume import open_multiscale

    surface = load_tifxyz(
        "s3://vesuvius-challenge-open-data/PHerc0800/segments/20251029010146-auto_grown_"
        "20251029010146642/mesh/20251029010146-on-20250521135224-8.64um.tifxyz")
    arrays, levels = open_multiscale(
        "s3://vesuvius-challenge-open-data/PHerc0800/volumes/"
        "20250521135224-8.640um-1.2m-116keV-masked.zarr")
    profile = normal_profiles(surface, arrays, [level.shape for level in levels],
                              pixel_size_um=8.64)
    metrics = alignment_metrics(profile)
    assert len(profile.patch_profiles) == 22 and profile.level == 0  # every usable patch
    assert abs(metrics["peak_offset"]) <= 6


def test_flat_profile_is_undetermined_not_an_offset():
    """Audit case: a perfectly flat profile returned -12 voxels with a bootstrap of [-12, -12]."""
    flat = pyramid(np.full((96, 64, 64), 80.0, dtype=np.float32))
    metrics = alignment_metrics(normal_profiles(plane(), *flat, patches=12))
    assert metrics["peak_offset"] is None
    assert metrics["peak_prominence"] is None
    assert metrics["bootstrap_iqr"] is None and metrics["bootstrap_width"] is None
    assert metrics["edge_offset"] is None
    report = run_surface("plan", surface=plane(), volume=flat)
    validate_report(report)
    result = {r["check_id"]: r for r in report["results"]}["surface.alignment"]
    assert result["status"] == "skipped" and result["value"] is None
    assert "indéterminé" in result["message"]


def test_maximum_on_the_window_edge_is_undetermined():
    # Intensity rising along -z (the normal direction): the brightest point of the ±12 window
    # is its edge, i.e. the slope towards some sheet further away, not a sheet.
    z = np.arange(96, dtype=np.float32)[:, None, None]
    ramp = pyramid((200 - z + np.zeros((96, 64, 64))).astype(np.float32))
    metrics = alignment_metrics(normal_profiles(plane(), *ramp, patches=12))
    assert metrics["peak_offset"] is None


def test_identical_patches_give_an_infinite_not_undefined_prominence():
    clean = pyramid(sheets(seed=0) * 0 + 50 + 100 * np.exp(
        -(((np.arange(96)[:, None, None] + 12) % 24 - 12) ** 2) / 8.0))  # noise-free sheets
    metrics = alignment_metrics(normal_profiles(plane(), *clean, patches=12))
    assert metrics["peak_offset"] == 0 and metrics["peak_prominence"] == float("inf")
    report = run_surface("plan", surface=shift_surface(plane(), 10), volume=clean,
                         pixel_size_um=5.0)
    result = alignment_result(report)
    assert result["status"] == "warn" and "très élevée" in result["message"]


def test_core_normal_is_opposite_to_the_vc3d_xyz_normal():
    # Pins the sign convention documented in grid_normals (phase 11 review): orientation reports
    # use the right-handed XYZ normal dP/dcol x dP/drow, the core uses the (z, y, x) cross product.
    from vesuvius_data_explorer.core.alignment import grid_normals

    rng = np.random.default_rng(3)
    rows, cols = np.mgrid[0:6, 0:7].astype(float)
    points = np.stack([0.3 * rows + 0.1 * cols**2, rows + 0.2 * cols, cols + 0.05 * rows**2], axis=-1)
    points += rng.normal(scale=0.01, size=points.shape)
    xyz = points[..., ::-1]
    vc3d = np.cross(np.gradient(xyz, axis=1), np.gradient(xyz, axis=0))
    vc3d /= np.linalg.norm(vc3d, axis=2, keepdims=True)
    np.testing.assert_allclose(grid_normals(points), -vc3d[..., ::-1], atol=1e-12)
