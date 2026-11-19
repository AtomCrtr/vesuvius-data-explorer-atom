"""Alignment map (T10) on synthetic volumes of parallel sheets."""

from dataclasses import replace

import numpy as np
import pytest
from test_alignment import SPACING, plane, pyramid, sheets

from vesuvius_data_explorer.core.alignment import grid_normals
from vesuvius_data_explorer.core.alignment_map import (
    alignment_map,
    field_on_grid,
    nearest_peak,
    peak_uncertainty,
    refine_peak,
    review_zones,
    sheet_spacing,
    snap_field,
    snap_points,
)
from vesuvius_data_explorer.core.flatten import flatten, sharpness, upsample_grid
from vesuvius_data_explorer.core.tifxyz import load_tifxyz, write_tifxyz


@pytest.fixture(scope="module")
def volume():
    return pyramid(sheets((96, 160, 160)))


def big_plane():
    return plane(rows=64, cols=64, x0=4.0)


def ramp(surface, amplitude):
    """Moved along its normals by 0 ... ``amplitude`` voxels across the columns."""
    cols = surface.points.shape[1]
    shift = amplitude * np.arange(cols)[None, :, None] / (cols - 1)
    return replace(surface, points=surface.points + shift * grid_normals(surface.points))


def test_nearest_peak_does_not_jump_to_a_brighter_neighbour():
    offsets = np.arange(-10, 11, dtype=float)
    values = np.exp(-((offsets - 2) ** 2) / 2) + 1.5 * np.exp(-((offsets + 6) ** 2) / 2)
    assert offsets[np.argmax(values)] == -6  # The brightest point is the neighbour...
    assert offsets[nearest_peak(offsets, values)] == 2  # ...the nearest sheet is at +2.
    assert nearest_peak(offsets, values, window=1) is None
    assert nearest_peak(offsets, np.ones_like(offsets)) is None  # Flat: no sheet.
    assert nearest_peak(offsets, offsets.copy()) is None  # Maximum on the edge only.


def test_parabolic_refinement_and_its_uncertainty():
    offsets = np.arange(-5, 6, dtype=float)
    values = -((offsets - 0.3) ** 2)
    index = int(np.argmax(values))
    assert refine_peak(offsets, values, index) == pytest.approx(0.3)
    small = peak_uncertainty(offsets, values, np.full(11, 0.01), index)
    large = peak_uncertainty(offsets, values, np.full(11, 0.04), index)
    assert 0 < small < large and large == pytest.approx(2 * small)  # Falls as 1/sqrt(N).


def test_sheet_spacing_from_periodic_profiles():
    offsets = np.arange(-40, 41, dtype=float)
    profiles = [np.cos(2 * np.pi * (offsets - shift) / 24) for shift in (0, 5, 11)]
    assert sheet_spacing(offsets, profiles) == pytest.approx(24, abs=0.5)
    single = np.exp(-(offsets**2) / 8)  # One sheet, no period.
    assert sheet_spacing(offsets, [single]) is None


def test_aligned_segment_gives_a_flat_reliable_map(volume):
    amap = alignment_map(big_plane(), *volume)
    assert amap.offset.shape == (8, 8) and np.isfinite(amap.offset).all()
    assert np.nanmax(np.abs(amap.offset)) < 0.2 and abs(amap.reference) < 0.1
    assert amap.spacing == pytest.approx(SPACING, rel=0.05)
    assert np.nanmin(amap.reliability) > 10 and np.nanmax(amap.uncertainty) < 0.5
    assert not amap.wraps and not amap.residues.any()
    assert review_zones(amap) == []


def test_slow_drift_is_measured_relative_to_the_usual_offset(volume):
    amap = alignment_map(ramp(big_plane(), 10), *volume)
    columns = np.nanmedian(amap.drift, axis=0)
    # Moving the surface by +s along its normal puts the sheet at -s; tile centres span 7/8.
    assert columns[0] - columns[-1] == pytest.approx(10 * 7 / 8, abs=1.0)
    assert abs(np.nanmedian(amap.drift)) < 0.5
    zones = review_zones(amap, max_drift_um=4)  # Voxels: no voxel size given.
    assert {z["type"] for z in zones} == {"derive"} and len(zones) == 2


def test_drift_beyond_one_sheet_is_unwrapped_and_flagged(volume):
    amap = alignment_map(ramp(big_plane(), 30), *volume)
    unwrapped = np.nanmedian(amap.unwrapped, axis=0)
    assert unwrapped[0] - unwrapped[-1] == pytest.approx(30 * 7 / 8, abs=2.0)
    assert np.all(np.diff(unwrapped) < 0)
    assert len(amap.wraps) == 8  # One wrap per tile row, where the drift passes Δ/2.
    assert set(np.unique(amap.sheet)) in ({0, 1}, {-1, 0})
    zones = review_zones(amap)
    assert zones[0]["type"] == "saut_de_feuille" and zones[0]["tuiles"] == 16
    assert zones[0]["lignes"] == [0, 64]


def test_snapping_brings_the_drift_back(volume):
    drifted = ramp(big_plane(), 10)
    before = alignment_map(drifted, *volume)
    grid = field_on_grid(snap_field(before), before, drifted.points.shape[:2])
    after = alignment_map(replace(drifted, points=snap_points(drifted.points, grid)), *volume)
    assert np.nanmedian(np.abs(after.drift)) < 0.25 * np.nanmedian(np.abs(before.drift))
    assert np.nanmedian(np.abs(after.drift)) < 1  # Less than one sampling step.


def test_unreliable_and_switch_tiles_are_not_moved(volume):
    surface = ramp(big_plane(), 30)
    amap = alignment_map(surface, *volume)
    reliability = amap.reliability.copy()
    reliability[:, 0] = 0
    amap = replace(amap, reliability=reliability)
    field = snap_field(amap)
    grid = field_on_grid(field, amap, surface.points.shape[:2])
    snapped = snap_points(surface.points, grid)
    for columns in (slice(0, 8), slice(24, 40)):
        np.testing.assert_array_equal(snapped[:, columns], surface.points[:, columns])
    assert np.any(grid[:, 8:24])


def test_snap_tapers_inside_movable_tiles_on_the_original_grid(volume):
    amap = replace(alignment_map(plane(rows=13, cols=15), *volume), stride=2)
    field = np.array([[4.0, 0.0], [4.0, 4.0]])
    grid = field_on_grid(field, amap, (26, 29))
    # The excluded tile is partial and has movable neighbours along both edges and the corner.
    np.testing.assert_array_equal(grid[:16, 16:], 0)
    assert grid[7, 7] == pytest.approx(4)
    assert 0 < grid[7, 15] < grid[7, 14] < grid[7, 7]
    assert 0 < grid[16, 16] < grid[17, 17] < grid[24, 24]


def test_tifxyz_writer_round_trip_and_refuses_to_overwrite(tmp_path):
    points = np.random.default_rng(0).uniform(0, 100, (5, 6, 3))
    points[0, 0] = np.nan
    folder = write_tifxyz(tmp_path / "seg", points, {"scale": [0.05, 0.05]})
    surface = load_tifxyz(str(folder))
    assert np.allclose(surface.points[1:], points[1:].astype(np.float32))
    assert np.isnan(surface.points[0, 0]).all() and surface.step_voxels == 20
    with pytest.raises(ValueError, match="déjà un segment"):
        write_tifxyz(folder, points, {})


def test_flattened_render_is_brighter_on_the_sheet(volume):
    arrays, shapes = volume
    on = flatten(big_plane().points[:10, :10], arrays, shapes, level=0, step_voxels=2)
    off = flatten(plane(z=60.0, rows=64, cols=64, x0=4.0).points[:10, :10], arrays, shapes,
                  level=0, step_voxels=2)
    assert on.shape == (19, 19) and np.isfinite(on).all()
    assert sharpness(on)["moyenne"] > sharpness(off)["moyenne"] + 50
    grid = np.zeros((3, 3, 3))
    grid[0, 0] = np.nan
    up = upsample_grid(grid, 2)
    assert up.shape == (5, 5, 3) and np.isnan(up[0, 0]).all() and np.isfinite(up[4, 4]).all()


def test_cli_map_writes_maps_zones_report_and_a_snapped_copy(volume, tmp_path):
    import json

    import tifffile
    import zarr

    from vesuvius_data_explorer.cli import main

    root = zarr.open_group(str(tmp_path / "sheets.zarr"), mode="w", zarr_format=2)
    datasets = []
    for index, array in enumerate(volume[0]):
        root.create_array(str(index), shape=array.shape, dtype="float32", chunks=(16, 32, 32))
        root[str(index)][:] = array
        datasets.append({"path": str(index), "coordinateTransformations": [
            {"type": "scale", "scale": [2.0**index] * 3}]})
    root.attrs["multiscales"] = [{"axes": ["z", "y", "x"], "datasets": datasets}]
    segment = write_tifxyz(tmp_path / "seg", ramp(big_plane(), 10).points, {"scale": [0.5, 0.5]})
    output = tmp_path / "carte"
    assert main(["carte", str(segment), "--volume", str(tmp_path / "sheets.zarr"),
                 "--recaler", "--derive-max", "4", "-o", str(output)]) == 0
    summary = json.loads((output / "carte.json").read_text())
    assert summary["unite"] == "voxels" and summary["tiles"]["measured"] == 64
    assert summary["zones"]["derive"] == 2 and summary["snap"]["abs_median"] > 1
    assert tifffile.imread(output / "decalage.tif").shape == (8, 8)
    assert len(json.loads((output / "zones.json").read_text())) == 2
    html = (output / "rapport.html").read_text(encoding="utf-8")
    assert "Carte de dérive" in html and "Après recalage" in html
    snapped = load_tifxyz(str(output / "recale"))
    assert "recalage" in snapped.meta and snapped.points.shape == (64, 64, 3)
    # The original is untouched and a second run cannot overwrite the snapped copy.
    assert np.allclose(load_tifxyz(str(segment)).points, ramp(big_plane(), 10).points)
    assert main(["carte", str(segment), "--volume", str(tmp_path / "sheets.zarr"),
                 "--recaler", "-o", str(output)]) == 2

    capped = tmp_path / "carte-plafonnee"
    assert main(["carte", str(segment), "--volume", str(tmp_path / "sheets.zarr"),
                 "--recaler", "--deplacement-max", "3", "--sans-rendu", "-o", str(capped)]) == 0
    original = load_tifxyz(str(segment)).points
    capped_points = load_tifxyz(str(capped / "recale")).points
    np.testing.assert_array_equal(capped_points[:, :8], original[:, :8])
    np.testing.assert_array_equal(capped_points[:, -8:], original[:, -8:])
    assert np.any(capped_points[:, 8:-8] != original[:, 8:-8])


def test_decoded_chunk_cache_serves_boxes_and_decodes_each_chunk_once():
    import zarr

    from vesuvius_data_explorer.core.chunkcache import DecodedChunks

    data = np.arange(40 * 50 * 60, dtype=np.float32).reshape(40, 50, 60)
    array = zarr.create_array(store={}, shape=data.shape, chunks=(16, 16, 16), dtype="float32")
    array[:] = data
    cached = DecodedChunks(array)
    for box in [(slice(3, 37), slice(0, 50), slice(17, 59)), (slice(0, 1), slice(5, 6),
                                                              slice(0, 60))]:
        assert np.array_equal(cached[box], data[box])
    first = cached.decoded
    cached[3:37, 0:50, 17:59]
    assert cached.decoded == first  # Served from memory.
    small = DecodedChunks(array, max_bytes=16**3 * 4)  # Room for one chunk only.
    assert np.array_equal(small[0:40, 0:50, 0:60], data)


def test_chunked_sampling_matches_scipy_and_the_map_on_zarr(volume):
    import zarr
    from scipy import ndimage

    from vesuvius_data_explorer.core.chunkcache import DecodedChunks, sample_trilinear

    data = volume[0][0]
    array = zarr.create_array(store={}, shape=data.shape, chunks=(16, 32, 32), dtype="float32")
    array[:] = data
    coords = np.random.default_rng(1).uniform(-2, 170, (500, 3))
    expected = ndimage.map_coordinates(data, coords.T, order=1, mode="nearest")
    assert np.allclose(sample_trilinear(DecodedChunks(array), coords), expected, atol=1e-3)
    arrays = [array] + list(volume[0][1:])
    on_zarr = alignment_map(ramp(big_plane(), 10), arrays, volume[1])
    in_memory = alignment_map(ramp(big_plane(), 10), *volume)
    assert np.allclose(on_zarr.offset, in_memory.offset, atol=1e-3, equal_nan=True)
    assert on_zarr.voxels_read <= data.size
