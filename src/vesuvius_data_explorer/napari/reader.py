"""Lazy Image layer data shared by the local reader and asynchronous widget."""

from pathlib import Path

from vesuvius_data_explorer.core.volume import (
    estimate_contrast,
    open_levels,
    volume_summary,
)


def napari_get_reader(path):
    """Claim existing local .zarr directories only; remote URIs use the widget."""
    if (
        isinstance(path, str)
        and "://" not in path
        and Path(path).suffix == ".zarr"
        and Path(path).is_dir()
    ):
        return _read_local_volume
    return None


def _read_local_volume(path: str) -> list[tuple]:
    # The user's napari preferences (including experimental.async_) are left untouched.
    return read_volume(path)


def read_volume(path: str) -> list[tuple]:
    """Open metadata and sample contrast before giving lazy arrays to napari."""
    source = path.strip().rstrip("/")
    # Zarr arrays, not Dask graphs: concurrent chunk reads and the local cache (T6).
    arrays, levels = open_levels(source)
    return [
        (
            arrays,
            {
                "multiscale": True,
                "rgb": False,
                "scale": levels[0].scale,
                "contrast_limits": estimate_contrast(arrays),
                "name": source.rsplit("/", 1)[-1],
                "metadata": {"source": source, "volume_summary": volume_summary(levels)},
            },
            "image",
        )
    ]
