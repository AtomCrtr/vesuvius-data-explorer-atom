"""Small on-disk OME pyramid, shared by reader and GUI integration tests."""

import numpy as np
import pytest
import zarr


@pytest.fixture
def napari_pyramid(tmp_path):
    path = tmp_path / "scan.zarr"
    root = zarr.open_group(str(path), mode="w", zarr_format=2)
    datasets = []
    for key, shape, scale in [
        ("fine", (16, 32, 48), [0.5, 1, 2]),
        ("medium", (8, 16, 24), [1, 2, 4]),
        ("coarse", (4, 8, 12), [2, 4, 8]),
    ]:
        data = np.arange(np.prod(shape), dtype=np.uint16).reshape(shape)
        array = root.create_array(key, shape=shape, dtype=data.dtype, chunks=(1, 4, 4))
        array[:] = data
        datasets.append(
            {
                "path": key,
                "coordinateTransformations": [{"type": "scale", "scale": scale}],
            }
        )
    root.attrs["multiscales"] = [{"axes": ["z", "y", "x"], "datasets": datasets}]
    return path
