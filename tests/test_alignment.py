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


def test_qc_check_is_informational_until_enabled(volume, tmp_path):
    report = run_surface("plan", surface=shift_surface(plane(), 10), volume=volume,
                         pixel_size_um=None)
    validate_report(report)
    result = {r["check_id"]: r for r in report["results"]}["surface.alignment"]
    assert result["status"] == "pass" and result["value"] == pytest.approx(-10, abs=1)
    assert "non notée" in result["message"]
    assert report["parameters"]["alignment"]["patches"] == 25  # all usable patches (36 asked)
    assert report["parameters"]["volume_shape"] == [96, 64, 64]
    config = tmp_path / "on.toml"
    config.write_text('["surface.alignment"]\nenabled = 1\n')
    enabled = run_surface("plan", surface=shift_surface(plane(), 10), volume=volume,
                          thresholds=load_thresholds(config))
    result = {r["check_id"]: r for r in enabled["results"]}["surface.alignment"]
    assert result["status"] == "warn"  # |offset| 10 > 8 voxels
    config.write_text('["surface.alignment"]\nenabled = 2\n')
    with pytest.raises(ValueError, match="enabled vaut 0 ou 1"):
        load_thresholds(config)


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
