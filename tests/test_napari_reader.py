"""The reader prepares lazy data with explicit contrast before napari sees it."""

import dask.array as da
import pytest
from zarr.storage import LocalStore

from vesuvius_data_explorer.napari.reader import napari_get_reader, read_volume


def test_reader_only_accepts_local_zarr_directories(napari_pyramid, tmp_path):
    assert callable(napari_get_reader(str(napari_pyramid)))
    plain_file = tmp_path / "image.tif"
    plain_file.touch()
    misleading_file = tmp_path / "file.zarr"
    misleading_file.touch()
    for source in [
        str(plain_file),
        str(misleading_file),
        "s3://bucket/scan.zarr",
        "https://x/a.zarr",
        [str(napari_pyramid)],
    ]:
        assert napari_get_reader(source) is None


def test_reader_reads_only_chunks_intersecting_the_coarse_central_slice(
    napari_pyramid, monkeypatch
):
    original = LocalStore.get
    reads = []

    async def tracking_get(self, key, *args, **kwargs):
        if key.rsplit("/", 1)[-1] not in {
            ".zarray",
            ".zattrs",
            ".zgroup",
            ".zmetadata",
            "zarr.json",
        }:
            reads.append(key)
        return await original(self, key, *args, **kwargs)

    monkeypatch.setattr(LocalStore, "get", tracking_get)
    [(arrays, options, layer_type)] = read_volume(str(napari_pyramid))
    assert layer_type == "image"
    assert len(arrays) == 3 and all(isinstance(array, da.Array) for array in arrays)
    assert options["multiscale"] is True
    assert options["scale"] == (0.5, 1, 2)
    assert options["contrast_limits"] == pytest.approx((192.95, 286.05))
    assert options["name"] == "scan.zarr"
    assert options["metadata"]["source"] == str(napari_pyramid)
    assert options["metadata"]["volume_summary"]["level_count"] == 3
    assert sorted(reads) == [f"coarse/2.{y}.{x}" for y in range(2) for x in range(3)]
