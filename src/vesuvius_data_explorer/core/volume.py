"""Bounded reads from 3D numpy arrays and local/S3 OME-Zarr multiscales.

Only the requested 2D window is materialized. Coordinate order is Z, Y, X.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, prod
from typing import Any
from warnings import warn

import dask.array as da
import numpy as np


@dataclass(frozen=True)
class Level:
    key: str
    shape: tuple[int, int, int]
    dtype: str
    chunks: tuple[int, int, int]
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)


def open_volume_store(path: str) -> Any:
    """Open a local or anonymous public S3 Zarr root, read-only.

    Use a complete `.zarr` URL, not the bucket root or a sample directory.
    HTTPS directory listings aren't reliable; use the documented S3 URI.
    """
    import zarr

    path = path.strip()
    if not path:
        raise ValueError("Indiquer le chemin d'un volume .zarr.")
    if path.startswith("s3://"):
        # Supported Zarr 3 remote store API. Anonymous access to the public bucket.
        store = zarr.storage.FsspecStore.from_url(
            path.rstrip("/"), storage_options={"anon": True}, read_only=True
        )
        return zarr.open(store=store, mode="r")
    if path.startswith(("https://", "http://")):
        raise ValueError(
            "Utiliser l'URI s3:// publique ou un chemin local ; HTTPS non pris en charge."
        )
    return zarr.open(path, mode="r")


def _is_3d_array(value: Any) -> bool:
    return len(getattr(value, "shape", ())) == 3


class _AxisOrderError(ValueError):
    """Explicit non-ZYX axes must never silently fall back to ZYX."""


def _level(node: Any, key: str, scale: tuple[float, float, float]) -> Level:
    shape = tuple(int(n) for n in node.shape)
    # NumPy arrays and the legacy array-like API have no storage chunk grid.
    chunks = tuple(int(n) for n in getattr(node, "chunks", shape))
    return Level(key, shape, str(node.dtype), chunks, scale)


def _dataset_scale(dataset: dict) -> tuple[float, float, float]:
    transformations = dataset.get("coordinateTransformations", [])
    if not isinstance(transformations, list):
        raise ValueError("coordinateTransformations doit être une liste.")
    scale = (1.0, 1.0, 1.0)
    for transform in transformations:
        if not isinstance(transform, dict):
            raise ValueError("Transformation de coordonnées invalide.")
        if transform.get("type") == "scale":
            values = transform.get("scale")
            if not isinstance(values, list) or len(values) != 3:
                raise ValueError("L'échelle doit contenir trois valeurs (z, y, x).")
            factors = tuple(float(value) for value in values)
            if not all(isfinite(value) and value > 0 for value in factors):
                raise ValueError("L'échelle doit contenir des valeurs finies positives.")
            scale = tuple(a * b for a, b in zip(scale, factors))
    return scale


def _metadata_levels(root: Any, metadata: Any) -> list[Level]:
    if not isinstance(metadata, list) or not metadata or not isinstance(metadata[0], dict):
        raise ValueError("multiscales doit contenir une pyramide.")
    # One image/pyramid per open call, consistent with the prototype.
    pyramid = metadata[0]
    if "axes" in pyramid:
        axes = pyramid["axes"]
        if not isinstance(axes, list):
            raise ValueError("Les axes doivent être une liste.")
        names = [axis.get("name") if isinstance(axis, dict) else axis for axis in axes]
        if names != ["z", "y", "x"]:
            raise _AxisOrderError("Ordre des axes non pris en charge : attendu (z, y, x).")
    datasets = pyramid.get("datasets")
    if not isinstance(datasets, list) or not datasets:
        raise ValueError("datasets doit contenir des niveaux.")
    levels = []
    seen = set()
    for dataset in datasets:
        if not isinstance(dataset, dict):
            raise ValueError("Description de niveau invalide.")
        key = dataset.get("path")
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Chemin de niveau invalide.")
        node = root[key]
        if not _is_3d_array(node):
            raise ValueError("Le tableau doit être 3D (z, y, x).")
        scale = _dataset_scale(dataset)
        if key not in seen:
            levels.append(_level(node, key, scale))
            seen.add(key)
    return levels


def list_levels(root: Any) -> list[Level]:
    """Read metadata only, returning levels from finest to coarsest.

    Malformed OME metadata emits a French warning and falls back to group
    arrays with unit scales. Missing axes assume the legacy (z, y, x) order;
    explicitly different axes are rejected rather than silently relabelled.
    """
    if _is_3d_array(root):
        return [_level(root, "__root__", (1.0, 1.0, 1.0))]
    if hasattr(root, "shape"):
        raise ValueError("Le tableau doit être 3D (z, y, x).")
    attrs = dict(getattr(root, "attrs", {}))
    levels: list[Level] = []
    if "multiscales" in attrs:
        try:
            levels = _metadata_levels(root, attrs["multiscales"])
        except _AxisOrderError:
            raise
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            warn(
                f"Métadonnées multiscales mal formées : {exc} ; "
                "repli sur les tableaux du groupe avec une échelle unitaire.",
                UserWarning,
                stacklevel=2,
            )
    if not levels:
        candidates = sorted(
            root.array_keys(), key=lambda s: (not s.isdigit(), int(s) if s.isdigit() else s)
        )
        for key in candidates:
            node = root[key]
            if _is_3d_array(node):
                levels.append(_level(node, key, (1.0, 1.0, 1.0)))
    if not levels:
        raise ValueError("Aucun tableau 3D détecté ; vérifier le chemin de la racine .zarr.")
    return sorted(levels, key=lambda level: prod(level.shape), reverse=True)


def volume_summary(levels: list[Level]) -> dict:
    """JSON-ready metadata; estimated_bytes excludes compression and overhead."""
    return {
        "level_count": len(levels),
        "levels": [
            {
                "key": level.key,
                "shape": list(level.shape),
                "dtype": level.dtype,
                "chunks": list(level.chunks),
                "scale": list(level.scale),
                "estimated_bytes": prod(level.shape) * np.dtype(level.dtype).itemsize,
            }
            for level in levels
        ],
    }


def open_multiscale(path: str) -> tuple[list[da.Array], list[Level]]:
    """Open local/public S3 levels as Dask graphs, without reading voxel chunks.

    Metadata I/O is necessary. Call read_slice for a bounded materialized ROI;
    computing an entire returned Dask array explicitly loads the entire level.
    """
    root = open_volume_store(path)
    levels = list_levels(root)
    arrays = [da.from_zarr(get_array(root, level.key)) for level in levels]
    return arrays, levels


def get_array(root: Any, key: str) -> Any:
    return root if key == "__root__" else root[key]


def read_slice(
    volume: Any,
    axis: str,
    index: int,
    start_a: int,
    start_b: int,
    width: int = 256,
) -> np.ndarray:
    """Read only one 2D ROI; at most 512×512 voxels per request.

    axis='z': (y, x), axis='y': (z, x), axis='x': (z, y).
    """
    if len(getattr(volume, "shape", ())) != 3:
        raise ValueError("Le tableau doit être 3D (z, y, x).")
    if axis not in ("z", "y", "x"):
        raise ValueError("Axe attendu : z, y ou x.")
    if not 1 <= width <= 512:
        raise ValueError("Largeur de fenêtre autorisée : 1 à 512 pixels.")
    z, y, x = (int(n) for n in volume.shape)
    axis_size, a_size, b_size = {"z": (z, y, x), "y": (y, z, x), "x": (x, z, y)}[axis]
    if not 0 <= index < axis_size:
        raise IndexError("Indice de coupe hors volume.")
    if not 0 <= start_a < a_size or not 0 <= start_b < b_size:
        raise IndexError("Origine de la fenêtre hors volume.")
    a = slice(start_a, min(start_a + width, a_size))
    b = slice(start_b, min(start_b + width, b_size))
    selection = {"z": (index, a, b), "y": (a, index, b), "x": (a, b, index)}[axis]
    result = np.asarray(volume[selection])
    if result.ndim != 2:
        raise ValueError("Lecture inattendue : le résultat n'est pas une coupe 2D.")
    return result


def slice_stats(data: np.ndarray) -> dict[str, float]:
    """Basic image diagnostics; they are not ink detection or research QA."""
    if data.ndim != 2 or data.size == 0:
        raise ValueError("Une image 2D non vide est requise.")
    finite = data[np.isfinite(data)]
    if finite.size == 0:
        return {"finite_pct": 0.0, "p1": float("nan"), "p99": float("nan"), "std": float("nan")}
    return {
        "finite_pct": float(finite.size * 100 / data.size),
        "p1": float(np.percentile(finite, 1)),
        "p99": float(np.percentile(finite, 99)),
        "std": float(np.std(finite)),
    }


def normalized_preview(data: np.ndarray) -> np.ndarray:
    """Robust grayscale preview, leaving non-finite pixels black."""
    arr = np.asarray(data, dtype=np.float32)
    out = np.zeros_like(arr, dtype=np.float32)
    ok = np.isfinite(arr)
    if not ok.any():
        return out
    low, high = np.percentile(arr[ok], (1, 99))
    if high > low:
        out[ok] = np.clip((arr[ok] - low) / (high - low), 0, 1)
    return out
