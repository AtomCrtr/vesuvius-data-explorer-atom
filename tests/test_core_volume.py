"""Real local Zarr stores exercise metadata discovery and bounded lazy reads."""

import json
from dataclasses import FrozenInstanceError

import dask.array as da
import numpy as np
import pytest
import zarr

from vesuvius_data_explorer import volume


@pytest.fixture(params=[2, 3], ids=["zarr-v2", "zarr-v3"])
def pyramid(tmp_path, request):
    path = tmp_path / "synthetic.zarr"
    root = zarr.open_group(str(path), mode="w", zarr_format=request.param)
    for key, shape, chunks in [
        ("fine", (8, 12, 16), (2, 3, 4)),
        ("medium", (4, 6, 8), (1, 2, 4)),
        ("coarse", (2, 3, 4), (1, 1, 2)),
    ]:
        data = np.arange(np.prod(shape), dtype=np.uint16).reshape(shape) + 1
        array = root.create_array(key, shape=shape, dtype=data.dtype, chunks=chunks)
        array[:] = data
    root.attrs["multiscales"] = [
        {
            "version": "0.4",
            "axes": [{"name": name, "type": "space"} for name in ("z", "y", "x")],
            "datasets": [
                {
                    "path": "coarse",
                    "coordinateTransformations": [{"type": "scale", "scale": [2, 4, 8]}],
                },
                {
                    "path": "fine",
                    "coordinateTransformations": [{"type": "scale", "scale": [0.5, 1, 2]}],
                },
                {
                    "path": "medium",
                    "coordinateTransformations": [{"type": "scale", "scale": [1, 2, 4]}],
                },
            ],
        }
    ]
    return path, root


def test_multiscale_metadata_and_json_summary(pyramid):
    path, _ = pyramid
    levels = volume.list_levels(volume.open_volume_store(str(path)))
    assert [level.key for level in levels] == ["fine", "medium", "coarse"]
    assert [level.scale for level in levels] == [(0.5, 1, 2), (1, 2, 4), (2, 4, 8)]
    assert [level.chunks for level in levels] == [(2, 3, 4), (1, 2, 4), (1, 1, 2)]
    assert levels[0].shape == (8, 12, 16)
    assert levels[0].dtype == "uint16"
    with pytest.raises(FrozenInstanceError):
        levels[0].key = "changed"
    summary = volume.volume_summary(levels)
    assert summary == {
        "level_count": 3,
        "levels": [
            {
                "key": "fine",
                "shape": [8, 12, 16],
                "dtype": "uint16",
                "chunks": [2, 3, 4],
                "scale": [0.5, 1.0, 2.0],
                "estimated_bytes": 3072,
            },
            {
                "key": "medium",
                "shape": [4, 6, 8],
                "dtype": "uint16",
                "chunks": [1, 2, 4],
                "scale": [1.0, 2.0, 4.0],
                "estimated_bytes": 384,
            },
            {
                "key": "coarse",
                "shape": [2, 3, 4],
                "dtype": "uint16",
                "chunks": [1, 1, 2],
                "scale": [2.0, 4.0, 8.0],
                "estimated_bytes": 48,
            },
        ],
    }
    assert json.loads(json.dumps(summary, allow_nan=False)) == summary


def test_numeric_fallback(tmp_path):
    root = zarr.open_group(str(tmp_path / "fallback.zarr"), mode="w")
    for key, shape in [("2", (2, 3, 4)), ("0", (8, 12, 16)), ("1", (4, 6, 8))]:
        root.create_array(key, shape=shape, chunks=(1, 2, 2), dtype="uint8")
    levels = volume.list_levels(root)
    assert [level.key for level in levels] == ["0", "1", "2"]
    assert all(level.scale == (1.0, 1.0, 1.0) for level in levels)


def test_pyramid_scale_composes_with_dataset_scale(pyramid):
    _, root = pyramid
    metadata = root.attrs["multiscales"]
    metadata[0]["coordinateTransformations"] = [{"type": "scale", "scale": [5, 10, 20]}]
    root.attrs["multiscales"] = metadata
    levels = volume.list_levels(root)
    assert [level.scale for level in levels] == [(2.5, 10, 40), (5, 20, 80), (10, 40, 160)]


@pytest.mark.parametrize("transformations", [None, [{"type": "scale", "scale": [1, 2]}]])
def test_malformed_pyramid_scale_falls_back(pyramid, transformations):
    _, root = pyramid
    metadata = root.attrs["multiscales"]
    metadata[0]["coordinateTransformations"] = transformations
    root.attrs["multiscales"] = metadata
    with pytest.warns(UserWarning, match="multiscales.*mal formées.*repli"):
        levels = volume.list_levels(root)
    assert [level.key for level in levels] == ["fine", "medium", "coarse"]
    assert all(level.scale == (1.0, 1.0, 1.0) for level in levels)


@pytest.mark.parametrize("axes", [None, [{}, {}, {}], ["z", "y"]])
def test_malformed_axes_fall_back(pyramid, axes):
    _, root = pyramid
    metadata = root.attrs["multiscales"]
    metadata[0]["axes"] = axes
    root.attrs["multiscales"] = metadata
    with pytest.warns(UserWarning, match="multiscales.*mal formées.*repli"):
        levels = volume.list_levels(root)
    assert levels[0].scale == (1.0, 1.0, 1.0)


@pytest.mark.parametrize(
    "metadata",
    [
        None,
        1,
        {},
        [None],
        [{}],
        [{"datasets": None}],
        [{"datasets": [{"path": 4}]}],
        [{"datasets": [{"path": "missing"}]}],
        [{"datasets": [{"path": "0", "coordinateTransformations": None}]}],
        [
            {
                "datasets": [
                    {"path": "0", "coordinateTransformations": [{"type": "scale", "scale": [1, 2]}]}
                ]
            }
        ],
        [
            {
                "datasets": [
                    {
                        "path": "0",
                        "coordinateTransformations": [{"type": "scale", "scale": [1, 0, 2]}],
                    }
                ]
            }
        ],
    ],
)
def test_malformed_metadata_falls_back_with_french_warning(tmp_path, metadata):
    root = zarr.open_group(str(tmp_path / "malformed.zarr"), mode="w")
    root.create_array("0", shape=(2, 3, 4), chunks=(1, 2, 2), dtype="uint8")
    root.attrs["multiscales"] = metadata
    with pytest.warns(UserWarning, match="multiscales.*mal formées.*repli"):
        levels = volume.list_levels(root)
    assert len(levels) == 1
    assert levels[0].key == "0"
    assert levels[0].scale == (1.0, 1.0, 1.0)


@pytest.mark.parametrize("materialize", ["compute", "read_slice"])
def test_open_multiscale_reads_no_chunks(pyramid, monkeypatch, materialize):
    path, _ = pyramid
    from zarr.storage import LocalStore

    original_get = LocalStore.get
    reads = []
    metadata_keys = {".zarray", ".zattrs", ".zgroup", ".zmetadata", "zarr.json"}

    async def tracking_get(self, key, *args, **kwargs):
        if key.rsplit("/", 1)[-1] not in metadata_keys:
            reads.append(key)
        return await original_get(self, key, *args, **kwargs)

    monkeypatch.setattr(LocalStore, "get", tracking_get)
    arrays, levels = volume.open_multiscale(str(path))
    volume.volume_summary(levels)
    assert len(arrays) == 3
    assert all(isinstance(array, da.Array) for array in arrays)
    assert [array.shape for array in arrays] == [level.shape for level in levels]
    assert arrays[0].chunksize == (2, 3, 4)
    assert reads == []
    if materialize == "compute":
        result = arrays[0][1, 1:3, 2:4].compute()
    else:
        result = volume.read_slice(arrays[0], "z", 1, 1, 2, width=2)
    np.testing.assert_array_equal(result, [[211, 212], [227, 228]])
    # This ROI intersects exactly one chunk of the finest level.
    assert reads in (["fine/0.0.0"], ["fine/c/0/0/0"])


def test_root_array_and_numpy_metadata(tmp_path):
    root = zarr.open_array(
        str(tmp_path / "array.zarr"), mode="w", shape=(4, 5, 6), chunks=(2, 3, 3), dtype="uint8"
    )
    level = volume.list_levels(root)[0]
    assert level.key == "__root__"
    assert level.chunks == (2, 3, 3)
    assert level.scale == (1.0, 1.0, 1.0)
    assert volume.list_levels(np.zeros((2, 3, 4)))[0].chunks == (2, 3, 4)


@pytest.mark.parametrize(
    "path, message",
    [
        (" ", "chemin"),
        ("https://example.org/volume.zarr", "HTTPS"),
    ],
)
def test_open_errors_are_explicit(path, message):
    with pytest.raises(ValueError, match=message):
        volume.open_volume_store(path)


def test_non_3d_and_empty_roots_are_explicit(tmp_path):
    with pytest.raises(ValueError, match="3D.*z, y, x"):
        volume.list_levels(np.zeros((3, 4)))
    root = zarr.open_group(str(tmp_path / "empty.zarr"), mode="w")
    root.create_array("0", shape=(3, 4), dtype="uint8")
    with pytest.raises(ValueError, match="Aucun tableau 3D"):
        volume.list_levels(root)


def test_explicit_non_zyx_axes_are_rejected(pyramid):
    _, root = pyramid
    metadata = root.attrs["multiscales"]
    metadata[0]["axes"] = ["x", "y", "z"]
    root.attrs["multiscales"] = metadata
    with pytest.raises(ValueError, match="axes.*z, y, x"):
        volume.list_levels(root)
