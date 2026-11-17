"""tifxyz segments: decoding, (z, y, x) order, invalid points, byte budget, indicators, catalogue."""

import json

import numpy as np
import pytest
import tifffile

from vesuvius_data_explorer.core import tifxyz as tifxyz_module
from vesuvius_data_explorer.core.catalog import parse_catalog
from vesuvius_data_explorer.core.tifxyz import choose_stride, load_tifxyz, tifxyz_metrics
from vesuvius_data_explorer.qc import run_surface
from vesuvius_data_explorer.qc.report import validate_report


def grids(rows=40, cols=30):
    """Flat sheet: x = 20 * col, y = 20 * row, z = 500, with VC3D's (-1, -1, -1) outline."""
    row, col = np.mgrid[:rows, :cols].astype(np.float32)
    x, y, z = 20 * col + 100, 20 * row + 200, np.full_like(row, 500)
    for grid in (x, y, z):
        grid[:3, :5] = -1  # irregular outline, connected to the border
    return x, y, z


def write_segment(folder, x, y, z, *, lzw=False, rowsperstrip=None, meta=True):
    folder.mkdir(parents=True, exist_ok=True)
    for name, grid in zip("xyz", (x, y, z)):
        path = folder / f"{name}.tif"
        if lzw:
            from PIL import Image

            # LZW + floating-point predictor, as in VC3D: tifffile needs imagecodecs for it.
            Image.fromarray(np.asarray(grid, np.float32)).save(
                path, compression="tiff_lzw", tiffinfo={317: 3})
        else:
            tifffile.imwrite(path, np.asarray(grid, np.float32), rowsperstrip=rowsperstrip)
    if meta:
        (folder / "meta.json").write_text(json.dumps({"format": "tifxyz", "scale": [0.05, 0.05]}))
    return folder


def test_uncompressed_segment_is_returned_in_zyx_with_nan_invalid(tmp_path):
    x, y, z = grids()
    surface = load_tifxyz(str(write_segment(tmp_path / "seg", x, y, z)))
    assert surface.points.shape == (40, 30, 3) and surface.stride == 1
    assert surface.grid_shape == (40, 30)
    assert surface.points[10, 7].tolist() == [500, 400, 240]  # (z, y, x)
    assert np.isnan(surface.points[:3, :5]).all() and surface.valid.sum() == 40 * 30 - 15
    assert surface.meta["format"] == "tifxyz" and surface.step_voxels == pytest.approx(20)
    assert surface.bytes_read >= 3 * 40 * 30 * 4 and not surface.warnings


def test_lzw_with_float_predictor_is_decoded_by_pillow(tmp_path, monkeypatch):
    x, y, z = grids()
    folder = write_segment(tmp_path / "seg", x, y, z, lzw=True)
    page = tifffile.TiffFile(folder / "x.tif").pages[0]
    assert page.compression.name == "LZW" and page.predictor == 3
    real = tifffile.imread

    def without_imagecodecs(*args, **kwargs):  # Same error as tifffile without imagecodecs.
        raise ValueError("<COMPRESSION.LZW: 5> requires the 'imagecodecs' package")

    monkeypatch.setattr(tifffile, "imread", without_imagecodecs)
    surface = load_tifxyz(str(folder))
    monkeypatch.setattr(tifffile, "imread", real)
    assert surface.points[10, 7].tolist() == [500, 400, 240]
    assert surface.valid.sum() == 40 * 30 - 15


def test_only_full_minus_one_triples_are_invalid(tmp_path):
    x, y, z = grids()
    x[20, 20] = -1  # a single -1 coordinate: valid, if odd
    z[21, 21] = -7  # negative = outside the volume, not invalid
    x[22, 22] = np.nan
    surface = load_tifxyz(str(write_segment(tmp_path / "seg", x, y, z)))
    assert surface.valid[20, 20] and surface.valid[21, 21] and not surface.valid[22, 22]


def test_missing_meta_json_warns_but_reads(tmp_path):
    surface = load_tifxyz(str(write_segment(tmp_path / "seg", *grids(), meta=False)))
    assert surface.meta == {} and "meta.json" in surface.warnings[0]
    assert surface.step_voxels == 20


def test_grid_errors_are_french(tmp_path):
    x, y, z = grids()
    folder = write_segment(tmp_path / "seg", x, y, z)
    tifffile.imwrite(folder / "z.tif", np.zeros((5, 5), np.float32))
    with pytest.raises(ValueError, match="même forme"):
        load_tifxyz(str(folder))
    with pytest.raises(FileNotFoundError, match="Grille introuvable"):
        load_tifxyz(str(tmp_path / "absent"))
    for source, message in [("", "Indiquer"), ("https://example.org/seg", "pas prise en charge"),
                            ("http://data.aws.ash2txt.org/seg", "pas prise en charge")]:
        with pytest.raises(ValueError, match=message):
            load_tifxyz(source)


def test_choose_stride_is_the_smallest_within_budget():
    assert choose_stride((100, 50), 4, 100 * 50 * 4) == 1
    assert choose_stride((100, 50), 4, 100 * 50 * 4 - 1) == 2
    assert choose_stride((100, 50), 4, 10 * 50 * 4) == 10
    with pytest.raises(ValueError, match="une seule ligne"):
        choose_stride((100, 50), 4, 50 * 4 - 1)


@pytest.mark.parametrize("rowsperstrip", [None, 7])
def test_oversized_uncompressed_grid_is_read_by_row_ranges(tmp_path, monkeypatch, rowsperstrip):
    x, y, z = grids(rows=101, cols=60)
    folder = write_segment(tmp_path / "seg", x, y, z, rowsperstrip=rowsperstrip)
    fetched = []
    real = tifxyz_module._strided_rows

    def spy(fs, path, header, stride):
        data, count = real(fs, path, header, stride)
        fetched.append(count)
        return data, count

    monkeypatch.setattr(tifxyz_module, "_strided_rows", spy)
    budget = 30 * 60 * 4  # 30 rows of 60 float32 per grid
    surface = load_tifxyz(str(folder), max_bytes=budget)
    assert surface.stride == 4 and surface.points.shape == (26, 15, 3)
    assert len(fetched) == 3 and max(fetched) <= budget
    assert surface.bytes_read == sum(fetched)
    expected = np.stack([z, y, x], axis=-1)[::4, ::4].astype(np.float64)
    expected[(expected == -1).all(axis=2)] = np.nan
    np.testing.assert_array_equal(surface.points, expected)
    assert "une ligne et une colonne sur 4" in surface.warnings[-1]
    assert surface.step_voxels == pytest.approx(80)


def test_oversized_compressed_grid_is_refused(tmp_path):
    folder = write_segment(tmp_path / "seg", *grids(), lzw=True)
    with pytest.raises(ValueError, match="compressée.*Augmenter"):
        load_tifxyz(str(folder), max_bytes=10 * 30 * 4)


def test_remote_uri_uses_the_same_reader(tmp_path, monkeypatch):
    import fsspec

    folder = write_segment(tmp_path / "seg", *grids())
    seen = []

    def local(source):
        seen.append(source)
        return fsspec.filesystem("file"), str(folder)

    monkeypatch.setattr(tifxyz_module, "_filesystem", local)
    surface = load_tifxyz("s3://bucket/seg/")
    assert seen == ["s3://bucket/seg/"] and surface.source == "s3://bucket/seg"


def surface_from(points):
    return tifxyz_module.TifxyzSurface(np.asarray(points, float), {}, points.shape[:2], 1,
                                       "test", 0)


def test_outline_is_not_a_hole_but_an_interior_gap_is(tmp_path):
    x, y, z = grids()
    for grid in (x, y, z):
        grid[-4:, -6:] = -1  # more outline: valid_pct drops, no hole
    outline = load_tifxyz(str(write_segment(tmp_path / "a", x, y, z)))
    metrics = tifxyz_metrics(outline)
    assert metrics["valid_pct"] < 97 and metrics["hole_pct"] == 0 and metrics["holes"] == []
    for grid in (x, y, z):
        grid[20:23, 10:13] = -1  # 9 interior points
    holed = load_tifxyz(str(write_segment(tmp_path / "b", x, y, z)))
    metrics = tifxyz_metrics(holed)
    enclosed = holed.valid.sum() + 9
    assert metrics["hole_pct"] == pytest.approx(100 * 9 / enclosed)
    [hole] = metrics["holes"]
    assert hole["origin"] == (20, 10) and hole["size"] == (3, 3) and hole["size_points"] == 9
    # Centre interpolated from the valid ring: row 21, column 11 -> y = 620, x = 320.
    assert hole["center"] == pytest.approx((500, 620, 320))


def test_out_of_bounds_share_uses_the_volume_shape():
    row, col = np.mgrid[:10, :10].astype(float)
    points = np.stack([np.full_like(row, 5), row, col * 2], axis=-1)  # x from 0 to 18
    surface = surface_from(points)
    assert tifxyz_metrics(surface)["out_of_bounds_pct"] is None
    assert tifxyz_metrics(surface, (10, 10, 10))["out_of_bounds_pct"] == pytest.approx(50)


@pytest.mark.parametrize("overlap, status", [(None, "pass"), (0.5, "pass"), (0.51, "pass"),
                                             (0.9, "warn")])
def test_bounds_check_compares_with_catalogue_coverage(tmp_path, overlap, status):
    folder = write_segment(tmp_path / "seg", *grids())
    # x spans 100..680, y 200..980, z = 500: half of the columns lie beyond x = 390.
    report = run_surface(str(folder), volume_shape=(1000, 1000, 390), overlap_ratio=overlap)
    validate_report(report)
    result = {r["check_id"]: r for r in report["results"]}["surface.bounds"]
    assert result["status"] == status
    # Columns 15-29 (x >= 400) of the 40 rows are outside: 600 of 1185 valid points.
    assert result["value"] == pytest.approx(100 * 600 / 1185)
    assert report["parameters"]["volume_shape"] == [1000, 1000, 390]


def test_surface_report_on_a_real_layout_is_schema_valid(tmp_path):
    x, y, z = grids()
    for grid in (x, y, z):
        grid[20:23, 10:13] = -1
    report = run_surface(str(write_segment(tmp_path / "seg", x, y, z)))
    validate_report(report)
    results = {r["check_id"]: r for r in report["results"]}
    assert report["schema_version"] == "1.1"
    assert set(results) == {"surface.valid", "surface.holes", "surface.stretch",
                            "surface.normal_flips", "surface.bounds", "surface.alignment"}
    assert results["surface.alignment"]["status"] == "skipped"  # no volume given
    assert results["surface.holes"]["status"] == "pass"  # 9 / 1185 = 0.76 % < 1 %
    assert results["surface.stretch"]["status"] == "pass"
    assert results["surface.normal_flips"]["status"] == "pass"


def test_cli_surface_reads_tifxyz_with_byte_budget(tmp_path, capsys):
    from vesuvius_data_explorer.cli import main

    folder = write_segment(tmp_path / "seg", *grids(rows=101, cols=60))
    output = tmp_path / "report.json"
    assert main(["surface", str(folder), "--max-bytes", str(30 * 60 * 4), "-o", str(output),
                 "--window", "64"]) == 0
    report = json.loads(output.read_text())
    assert report["parameters"]["stride"] == 4 and report["parameters"]["max_bytes"] == 7200
    err = capsys.readouterr().err
    assert "window ignorée" in err and "une ligne et une colonne sur 4" in err


def catalog_with_segments():
    s3 = {"type": "s3", "url": "s3://vesuvius-challenge-open-data", "usage": "public-read"}

    def entry(kind, path, **parameters):
        return {"type": kind, "origins": [{"path": path, "access_roots": [s3]}],
                "parameters": parameters or None}

    volume = {"properties": {"pixel_size_um": 8.64}, "data": [entry("ome-zarr", "P/v.zarr/")]}
    segment = {
        "long_id": "20251029010146-auto_grown",
        "properties": {"volume_coverage": {"V1": {"overlap_ratio": 0.75}}},
        "data": [
            entry("tifxyz", "P/s/orig/"),
            entry("tifxyz-transformed", "P/s/on-V1.tifxyz/", target_volume="V1"),
            entry("tifxyz-transformed", "P/s/on-V2.tifxyz/", target_volume="V2",
                  transform_revision="2"),
            {**entry("tifxyz-transformed", "P/s/on-V2-old.tifxyz/", target_volume="V2"),
             "properties": {"superseded_by": {"path": "P/s/on-V2.tifxyz/"}}},
            entry("obj", "P/s/mesh.obj"),
        ],
    }
    return parse_catalog({"samples": {"P": {"volumes": {"V1": volume},
                                            "segments": {"20251029010146": segment}}}})


def test_catalogue_keeps_only_transformed_copies_attached_to_their_volume():
    catalog = catalog_with_segments()
    assert len(catalog.segments) == 3
    [on_v1] = catalog.segments_for("V1")
    assert on_v1.uri == "s3://vesuvius-challenge-open-data/P/s/on-V1.tifxyz"
    assert on_v1.overlap_ratio == 0.75 and on_v1.name == "20251029010146-auto_grown"
    assert on_v1.label == "20251029010146 (auto_grown) — couverture 75 %"
    [current] = catalog.segments_for("V2")
    assert current.transform_revision == 2 and current.overlap_ratio is None
    both = catalog.segments_for("V2", include_superseded=True)
    assert [s.superseded for s in both] == [False, True] and both[1].label.endswith("(remplacé)")


@pytest.mark.network
def test_real_transformed_segment():
    surface = load_tifxyz(
        "s3://vesuvius-challenge-open-data/PHerc0800/segments/20251029010146-auto_grown_"
        "20251029010146642/mesh/20251029010146-on-20250521135224-8.64um.tifxyz")
    assert surface.grid_shape == (49, 49) and surface.stride == 1
    assert tifxyz_metrics(surface, (24298, 9867, 9867))["out_of_bounds_pct"] == 0


@pytest.mark.network
def test_real_large_segment_is_decimated_within_budget():
    # x.tif is 73 MiB (uncompressed, one strip): above the default 64 MiB budget.
    surface = load_tifxyz(
        "s3://vesuvius-challenge-open-data/PHercParis4/segments/20260623141924-w010-027/mesh/"
        "20260623141924-on-20260411134726-2.4um.tifxyz")
    assert surface.stride == 2
    assert surface.bytes_read <= 3 * tifxyz_module.DEFAULT_MAX_BYTES
    assert surface.valid.any()
