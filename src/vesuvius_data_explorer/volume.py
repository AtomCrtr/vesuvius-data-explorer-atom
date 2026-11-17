"""Bounded reads from 3D numpy arrays and local/S3 OME-Zarr multiscales.

Only the requested 2D window is materialized. Coordinate order is Z, Y, X.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class Level:
    key: str
    shape: tuple[int, int, int]
    dtype: str


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
    if path.startswith("https://") or path.startswith("http://"):
        raise ValueError("Utiliser l'URI s3:// publique ou un chemin local ; HTTPS non pris en charge.")
    return zarr.open(path, mode="r")


def _is_3d_array(value: Any) -> bool:
    return len(getattr(value, "shape", ())) == 3


def list_levels(root: Any) -> list[Level]:
    """Return OME multiscale array paths (fallback to numeric group members)."""
    if _is_3d_array(root):
        return [Level("__root__", tuple(int(x) for x in root.shape), str(root.dtype))]
    attrs = dict(getattr(root, "attrs", {}))
    candidates: list[str] = []
    for pyramid in attrs.get("multiscales", []):
        for dataset in pyramid.get("datasets", []):
            name = dataset.get("path")
            if isinstance(name, str) and name not in candidates:
                candidates.append(name)
        if candidates:
            break
    if not candidates:
        candidates = sorted(list(root.array_keys()), key=lambda s: (not s.isdigit(), int(s) if s.isdigit() else s))
    levels: list[Level] = []
    for key in candidates:
        try:
            node = root[key]
            if _is_3d_array(node):
                levels.append(Level(key, tuple(int(n) for n in node.shape), str(node.dtype)))
        except (KeyError, TypeError, ValueError):
            continue
    if not levels:
        raise ValueError("Aucun tableau 3D détecté ; vérifier le chemin de la racine .zarr.")
    return levels


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
    axis_size, a_size, b_size = {
        "z": (z, y, x), "y": (y, z, x), "x": (x, z, y)
    }[axis]
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
