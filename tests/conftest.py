"""Small on-disk OME pyramid, shared by reader and GUI integration tests."""

import os
import tempfile

# Keep napari's persisted preferences away from the developer's real settings file:
# the singleton reads NAPARI_CONFIG the first time napari.settings is used.
os.environ["NAPARI_CONFIG"] = os.path.join(
    tempfile.mkdtemp(prefix="napari-test-settings-"), "settings.yaml"
)

import numpy as np  # noqa: E402
import pytest  # noqa: E402
import zarr  # noqa: E402


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


@pytest.fixture
def async_loading(make_napari_viewer):
    """Enable napari async loading after make_napari_viewer has reset the settings."""
    from napari.settings import get_settings

    get_settings().experimental.async_ = True
