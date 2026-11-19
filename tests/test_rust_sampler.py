"""Scientific equivalence of both implementations through the production dispatcher."""

import sys

import numpy as np
import pytest
import zarr
from test_alignment import plane, sheets

from vesuvius_data_explorer.core import chunkcache
from vesuvius_data_explorer.core.alignment_map import alignment_map, reliable_tiles, switch_tiles
from vesuvius_data_explorer.core.chunkcache import DecodedChunks, sample_trilinear
from vesuvius_data_explorer.core.flatten import flatten
from vesuvius_data_explorer.core.tifxyz import write_tifxyz


class RecordedArray:
    def __init__(self, array, chunks):
        self.array = array
        self.shape = array.shape
        self.dtype = array.dtype
        self.chunks = chunks
        self.reads = set()

    def __getitem__(self, selection):
        self.reads.add(tuple((axis.start, axis.stop) for axis in selection))
        return self.array[selection]


@pytest.fixture
def rust_available():
    pytest.importorskip("vesuvius_explorer_rust")
    assert chunkcache._rust_sampler() is not None


@pytest.mark.parametrize("dtype", [np.uint8, np.uint16])
@pytest.mark.parametrize("chunks", [(2, 3, 4), (1, 2, 3)])
def test_voxel_order_values_and_chunk_footprint(monkeypatch, rust_available, dtype, chunks):
    rng = np.random.default_rng(31)
    # Strided volume and coordinates, ragged trailing chunks, and a singleton Z axis below.
    volume = rng.integers(0, np.iinfo(dtype).max, (6, 7, 22), dtype=dtype)[:, :, ::2]
    coords = rng.uniform(-1, 10, size=(399, 6))[:, ::2]
    coords[:4] = [[0, 0, 0], [5, 6, 10], [-30, 6, 10], [1.5, 2.5, 3.5]]
    ref, native = RecordedArray(volume, chunks), RecordedArray(volume, chunks)
    monkeypatch.setenv("VESUVIUS_RUST_SAMPLER", "0")
    expected = sample_trilinear(DecodedChunks(ref), coords)
    monkeypatch.setenv("VESUVIUS_RUST_SAMPLER", "1")
    monkeypatch.setattr(chunkcache, "RUST_BATCH_POINTS", 73)
    actual = sample_trilinear(DecodedChunks(native), coords)
    np.testing.assert_array_equal(actual[:3], [volume[0, 0, 0], volume[-1, -1, -1],
                                               volume[0, -1, -1]])
    np.testing.assert_allclose(actual, expected, atol=1e-8, rtol=0)
    assert actual.dtype == expected.dtype == np.dtype("float64")
    assert actual.shape == expected.shape == (399,)
    assert native.reads == ref.reads
    singleton = RecordedArray(volume[:1], chunks)
    np.testing.assert_array_equal(sample_trilinear(DecodedChunks(singleton), coords[:3]),
                                  [volume[0, 0, 0], volume[0, -1, -1], volume[0, -1, -1]])
    assert sample_trilinear(DecodedChunks(singleton), np.empty((0, 3))).shape == (0,)


def test_compressed_zarr_renders_same_oriented_surface(monkeypatch, rust_available, tmp_path):
    z, y, x = np.ogrid[:9, :14, :16]
    data = (100 * z + 10 * y + x).astype(np.uint16)
    array = zarr.open_array(str(tmp_path / "tiny.zarr"), mode="w", shape=data.shape,
                           chunks=(3, 4, 5), dtype=data.dtype, zarr_format=2)
    array[:] = data
    r, c = np.mgrid[1:13:2, 1:15:2]
    surface = np.stack([2.1 + r / 7, r, c], axis=-1)
    surface[-2, -2] = np.nan

    def render(backend):
        monkeypatch.setenv("VESUVIUS_RUST_SAMPLER", backend)
        return flatten(surface, [array], [data.shape], level=0, step_voxels=2,
                       normal_offsets=(-0.8, 0, 0.8))

    expected, actual = render("0"), render("1")
    assert actual.shape == (11, 13) and actual.dtype == np.float32
    np.testing.assert_array_equal(np.isnan(actual), np.isnan(expected))
    np.testing.assert_allclose(actual, expected, atol=1e-4, rtol=0)


def test_alignment_map_retains_tile_decisions_with_worker_threads(monkeypatch, rust_available):
    surface = plane(z=49.25, rows=24, cols=24, x0=3.2)
    volume = RecordedArray(sheets().astype(np.uint8), (16, 17, 13))
    monkeypatch.setenv("VESUVIUS_RUST_SAMPLER", "0")
    expected = alignment_map(surface, [volume], [volume.shape], workers=4)
    monkeypatch.setenv("VESUVIUS_RUST_SAMPLER", "1")
    actual = alignment_map(surface, [volume], [volume.shape], workers=4)
    assert actual.level == expected.level and actual.wraps == expected.wraps
    assert actual.voxels_read == expected.voxels_read
    np.testing.assert_array_equal(actual.points, expected.points)
    np.testing.assert_array_equal(actual.residues, expected.residues)
    np.testing.assert_array_equal(reliable_tiles(actual), reliable_tiles(expected))
    np.testing.assert_array_equal(switch_tiles(actual), switch_tiles(expected))
    np.testing.assert_allclose(actual.profiles, expected.profiles, rtol=0, atol=1e-8)
    np.testing.assert_allclose(actual.offset, expected.offset, rtol=0, atol=1e-8)


def test_carte_command_reaches_native_sampler(monkeypatch, rust_available, tmp_path):
    from vesuvius_data_explorer.cli import main

    data = sheets().astype(np.uint8)
    volume = tmp_path / "sheets.zarr"
    root = zarr.open_group(str(volume), mode="w", zarr_format=2)
    root.create_array("0", shape=data.shape, dtype=data.dtype, chunks=(16, 16, 16))[:] = data
    root.attrs["multiscales"] = [{"axes": ["z", "y", "x"], "datasets": [{"path": "0"}]}]
    segment = write_tifxyz(tmp_path / "segment", plane(rows=16, cols=16).points,
                           {"scale": [0.5, 0.5]})
    output = tmp_path / "map"
    plan = chunkcache._rust_sampler()
    batch_sizes = []

    def record_plan(coords, shape, chunks):
        batch_sizes.append(len(coords))
        return plan(coords, shape, chunks)

    monkeypatch.setenv("VESUVIUS_RUST_SAMPLER", "1")
    monkeypatch.setattr(chunkcache, "_rust_sampler", lambda: record_plan)
    assert main(["carte", str(segment), "--volume", str(volume), "-o", str(output)]) == 0
    assert (output / "rapport.html").is_file()
    assert len(batch_sizes) == 5  # Four 8×8 tiles followed by the flattened render.


def test_optional_extension_can_be_missing(monkeypatch, caplog):
    volume = DecodedChunks(np.ones((2, 2, 2), dtype=np.uint8))
    monkeypatch.setenv("VESUVIUS_RUST_SAMPLER", "1")
    monkeypatch.setitem(sys.modules, "vesuvius_explorer_rust", None)
    chunkcache._rust_sampler.cache_clear()
    try:
        np.testing.assert_array_equal(sample_trilinear(volume, [[0, 0, 0]]), [1])
        assert "interpolation Python utilisée" in caplog.text
    finally:
        chunkcache._rust_sampler.cache_clear()


def test_unsupported_dtypes_stay_on_python(monkeypatch):
    def unexpected_native_call():
        pytest.fail("Rust must not be called for float or non-native-endian blocks")

    monkeypatch.setenv("VESUVIUS_RUST_SAMPLER", "1")
    monkeypatch.setattr(chunkcache, "_rust_sampler", unexpected_native_call)
    for dtype in (np.float32, ">u2" if sys.byteorder == "little" else "<u2"):
        volume = DecodedChunks(np.ones((2, 2, 2), dtype=dtype))
        np.testing.assert_array_equal(sample_trilinear(volume, [[0.5, 0.5, 0.5]]), [1])
