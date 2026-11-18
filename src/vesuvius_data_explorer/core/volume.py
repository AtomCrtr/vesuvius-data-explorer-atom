"""Bounded reads from 3D numpy arrays and local/S3 OME-Zarr multiscales.

Only the requested 2D window is materialized. Coordinate order is Z, Y, X.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from math import isfinite, prod
from typing import Any
from urllib.parse import urlsplit
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
    # False when scale is the unit fallback (no usable OME metadata), not a measurement.
    scale_from_metadata: bool = True


# HTTPS hosts serving official Vesuvius Challenge volumes outside the open-data S3 bucket
# (catalogue access root, see docs/investigations/I1-ecosysteme-donnees.md).
ALLOWED_HTTPS_HOSTS = frozenset({"data.aws.ash2txt.org"})
CODEC_EXTRAS = {"vc-delta3d": "vcdelta3d"}


def _not_found_errors() -> tuple[type[BaseException], ...]:
    import zarr.errors

    names = ("NodeNotFoundError", "GroupNotFoundError", "ArrayNotFoundError")
    return (FileNotFoundError,) + tuple(
        getattr(zarr.errors, name) for name in names if hasattr(zarr.errors, name)
    )


def _is_unknown_codec(exc: BaseException) -> bool:
    return type(exc).__name__ == "UnknownCodecError"


def _codec_error(exc: BaseException) -> ValueError:
    """French, actionable message for a codec zarr-python cannot decode."""
    # zarr 3.1: "Unknown codec: 'name'"; zarr 3.4: "An implementation for codec 'name' ..."
    match = re.search(r"codec:?\s*['\"]([^'\"]+)['\"]", str(exc), re.IGNORECASE)
    codec = match.group(1) if match else "inconnu"
    extra = CODEC_EXTRAS.get(codec)
    hint = (f"installer l'extra : pip install 'vesuvius-data-explorer[{extra}]'" if extra else
            "installer le paquet Python qui fournit ce codec à zarr")
    return ValueError(f"Codec de compression « {codec} » non pris en charge : {hint}.")


DEFAULT_CONCURRENCY = 64


def set_remote_concurrency() -> int:
    """Concurrent chunk requests of Zarr (process-wide setting, T6).

    S3 answers a 2 MiB chunk in about 0.27 s but serves many in parallel: 64 concurrent
    requests halve the time of a 27-chunk read compared with Zarr's default of 10.
    ``VESUVIUS_ZARR_CONCURRENCY`` overrides the value.
    """
    import os

    import zarr

    raw = os.environ.get("VESUVIUS_ZARR_CONCURRENCY", str(DEFAULT_CONCURRENCY))
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value < 1:
        warn(f"VESUVIUS_ZARR_CONCURRENCY invalide ({raw!r}) : {DEFAULT_CONCURRENCY} utilisé.",
             stacklevel=2)
        value = DEFAULT_CONCURRENCY
    zarr.config.set({"async.concurrency": value})
    return value


def open_volume_store(path: str, *, cache: bool = False) -> Any:
    """Open a local, anonymous public S3 or allowed HTTPS Zarr root, read-only.

    Use a complete `.zarr` URL, not the bucket root or a sample directory. HTTPS is
    accepted only for the official hosts in ``ALLOWED_HTTPS_HOSTS``; it needs no
    directory listing because levels come from the OME metadata. With ``cache``, a remote
    store is wrapped in the persistent local chunk cache (``core.cache``); local volumes are
    never cached. Opening a remote volume sets Zarr's concurrency (``set_remote_concurrency``).
    """
    import zarr

    from .cache import cached_store

    path = path.strip()
    if not path:
        raise ValueError("Indiquer le chemin d'un volume .zarr.")
    try:
        if path.startswith("s3://"):
            set_remote_concurrency()
            # Supported Zarr 3 remote store API. Anonymous access to the public bucket.
            store = zarr.storage.FsspecStore.from_url(
                path.rstrip("/"), storage_options={"anon": True}, read_only=True
            )
            if cache:
                store = cached_store(store, path)
            return zarr.open(store=store, mode="r")
        if path.startswith(("https://", "http://")):
            host = urlsplit(path).hostname or ""
            if not path.startswith("https://") or host not in ALLOWED_HTTPS_HOSTS:
                allowed = ", ".join(sorted(ALLOWED_HTTPS_HOSTS))
                raise ValueError(
                    "Utiliser l'URI s3:// publique, un chemin local ou une URL HTTPS officielle "
                    f"({allowed}) ; cette URL n'est pas prise en charge."
                )
            set_remote_concurrency()
            store = zarr.storage.FsspecStore.from_url(path.rstrip("/"), read_only=True)
            if cache:
                store = cached_store(store, path)
            return zarr.open(store=store, mode="r")
        return zarr.open(path, mode="r")
    except _not_found_errors():
        raise FileNotFoundError(f"Volume introuvable : {path}") from None
    except ValueError as exc:
        if _is_unknown_codec(exc):
            raise _codec_error(exc) from None
        raise


def _is_3d_array(value: Any) -> bool:
    return len(getattr(value, "shape", ())) == 3


class _AxisOrderError(ValueError):
    """Explicit non-ZYX axes must never silently fall back to ZYX."""


def _level(
    node: Any, key: str, scale: tuple[float, float, float], from_metadata: bool = True
) -> Level:
    shape = tuple(int(n) for n in node.shape)
    # NumPy arrays and the legacy array-like API have no storage chunk grid.
    chunks = tuple(int(n) for n in getattr(node, "chunks", shape))
    return Level(key, shape, str(node.dtype), chunks, scale, from_metadata)


def _dataset_scale(dataset: dict) -> tuple[tuple[float, float, float], bool]:
    """(combined scale, whether any scale transform was declared)."""
    transformations = dataset.get("coordinateTransformations", [])
    if not isinstance(transformations, list):
        raise ValueError("coordinateTransformations doit être une liste.")
    scale = (1.0, 1.0, 1.0)
    declared = False
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
            declared = True
    return scale, declared


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
        if len(names) != 3 or not all(isinstance(name, str) and name for name in names):
            raise ValueError("Les axes doivent nommer trois dimensions.")
        if names != ["z", "y", "x"]:
            raise _AxisOrderError("Ordre des axes non pris en charge : attendu (z, y, x).")
    datasets = pyramid.get("datasets")
    if not isinstance(datasets, list) or not datasets:
        raise ValueError("datasets doit contenir des niveaux.")
    levels = []
    seen = set()
    pyramid_scale, _ = _dataset_scale(pyramid)
    for dataset in datasets:
        if not isinstance(dataset, dict):
            raise ValueError("Description de niveau invalide.")
        key = dataset.get("path")
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Chemin de niveau invalide.")
        node = root[key]
        if not _is_3d_array(node):
            raise ValueError("Le tableau doit être 3D (z, y, x).")
        scale, declared = _dataset_scale(dataset)
        scale = tuple(a * b for a, b in zip(scale, pyramid_scale))
        if key not in seen:
            # Without a per-level scale transform the unit scale is a default, not a
            # measurement: checks comparing scales across levels must not use it.
            levels.append(_level(node, key, scale, from_metadata=declared))
            seen.add(key)
    return levels


def list_levels(root: Any) -> list[Level]:
    """Read metadata only, returning levels from finest to coarsest.

    NGFF 0.5 (ome.multiscales) takes precedence over NGFF 0.4 (multiscales).
    Malformed OME metadata emits a French warning and falls back to group
    arrays with unit scales. Numeric fallback without OME metadata warns that
    unit scales are not physical measurements. Missing axes assume the legacy
    (z, y, x) order; explicitly different axes are rejected.
    """
    if _is_3d_array(root):
        return [_level(root, "__root__", (1.0, 1.0, 1.0), False)]
    if hasattr(root, "shape"):
        raise ValueError("Le tableau doit être 3D (z, y, x).")
    attrs = dict(getattr(root, "attrs", {}))
    levels: list[Level] = []
    has_metadata = "ome" in attrs or "multiscales" in attrs
    if has_metadata:
        try:
            if "ome" in attrs:
                ome = attrs["ome"]
                if not isinstance(ome, dict):
                    raise ValueError("Le champ ome doit être un objet contenant multiscales.")
                metadata = ome.get("multiscales")
            else:
                metadata = attrs["multiscales"]
            levels = _metadata_levels(root, metadata)
        except _AxisOrderError:
            raise
        except ValueError as exc:
            if _is_unknown_codec(exc):
                raise _codec_error(exc) from None
            warn(
                f"Métadonnées multiscales mal formées : {exc} ; "
                "repli sur les tableaux du groupe avec une échelle unitaire.",
                UserWarning,
                stacklevel=2,
            )
        except (KeyError, TypeError, OverflowError) as exc:
            warn(
                f"Métadonnées multiscales mal formées : {exc} ; "
                "repli sur les tableaux du groupe avec une échelle unitaire.",
                UserWarning,
                stacklevel=2,
            )
    if not levels:
        try:
            keys = list(root.array_keys())
        except ValueError as exc:
            if _is_unknown_codec(exc):
                raise _codec_error(exc) from None
            raise
        candidates = sorted(keys, key=lambda s: (not s.isdigit(), int(s) if s.isdigit() else s))
        for key in candidates:
            node = root[key]
            if _is_3d_array(node):
                levels.append(_level(node, key, (1.0, 1.0, 1.0), False))
    if not levels:
        raise ValueError("Aucun tableau 3D détecté ; vérifier le chemin de la racine .zarr.")
    if not has_metadata and any(level.key.isdigit() for level in levels):
        warn(
            "Métadonnées multiscales absentes : repli numérique avec des échelles unitaires ; "
            "ce ne sont pas des mesures physiques.",
            UserWarning,
            stacklevel=2,
        )
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


def open_levels(path: str, *, cache: bool = True) -> tuple[list[Any], list[Level]]:
    """Open the levels as **Zarr arrays** (T6), through the local chunk cache if remote.

    Zarr reads every chunk of a selection concurrently; a Dask graph (``open_multiscale``)
    reads them as synchronous tasks, at most one per core: 5x slower on the measured S3
    workloads. Nothing is read until an array is indexed.
    """
    root = open_volume_store(path, cache=cache)
    levels = list_levels(root)
    return [get_array(root, level.key) for level in levels], levels


def get_array(root: Any, key: str) -> Any:
    return root if key == "__root__" else root[key]


def read_slice(
    volume: Any,
    axis: str,
    index: int,
    start_a: int,
    start_b: int,
    width: int = 256,
    width_b: int | None = None,
) -> np.ndarray:
    """Read only one 2D ROI; at most 512×512 voxels per request.

    axis='z': (y, x), axis='y': (z, x), axis='x': (z, y). ``width`` is the extent on the first
    in-plane axis and, unless ``width_b`` is given, on the second one too (square window).
    """
    if len(getattr(volume, "shape", ())) != 3:
        raise ValueError("Le tableau doit être 3D (z, y, x).")
    if axis not in ("z", "y", "x"):
        raise ValueError("Axe attendu : z, y ou x.")
    width_b = width if width_b is None else width_b
    if not 1 <= width <= 512 or not 1 <= width_b <= 512:
        raise ValueError("Largeur de fenêtre autorisée : 1 à 512 pixels.")
    z, y, x = (int(n) for n in volume.shape)
    axis_size, a_size, b_size = {"z": (z, y, x), "y": (y, z, x), "x": (x, z, y)}[axis]
    if not 0 <= index < axis_size:
        raise IndexError("Indice de coupe hors volume.")
    if not 0 <= start_a < a_size or not 0 <= start_b < b_size:
        raise IndexError("Origine de la fenêtre hors volume.")
    a = slice(start_a, min(start_a + width, a_size))
    b = slice(start_b, min(start_b + width_b, b_size))
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


BACKGROUND_MIN_FRACTION = 0.05
FOREGROUND_MIN_FRACTION = 0.01


def estimate_contrast(levels_arrays: list[Any], max_side: int = 512,
                      background: float | None = 0.0) -> tuple[float, float]:
    """Estimate finite 1/99 percentiles from one central coarse Z slice.

    The returned sample is bounded to max_side² pixels (at most 512²), although
    intersecting storage chunks may be larger. Empty, non-finite or degenerate
    samples use dtype bounds, clamped to finite Python floats when necessary.

    Masked volumes set everything outside the scroll to ``background`` (0, the QC default):
    when it is at least 5 % of the sample and at least 1 % remains, those voxels are left out,
    so the papyrus keeps its contrast (T6). ``background=None`` disables the exclusion.
    """
    if not isinstance(max_side, int) or not 1 <= max_side <= 512:
        raise ValueError("Largeur de fenêtre autorisée : 1 à 512 pixels.")
    if not levels_arrays:
        raise ValueError("Au moins un niveau est requis pour estimer le contraste.")
    coarse = levels_arrays[-1]
    if len(getattr(coarse, "shape", ())) != 3:
        raise ValueError("Le tableau doit être 3D (z, y, x).")
    dtype = np.dtype(coarse.dtype)
    if dtype.kind == "b":
        fallback = (0.0, 1.0)
    elif dtype.kind in "iu":
        bounds = np.iinfo(dtype)
        fallback = (float(bounds.min), float(bounds.max))
    elif dtype.kind == "f":
        bound = min(np.finfo(dtype).max, np.finfo(float).max)
        fallback = (-float(bound), float(bound))
    else:
        raise ValueError("Le contraste nécessite un tableau numérique réel.")
    z, y, x = (int(n) for n in coarse.shape)
    if min(z, y, x) == 0:
        return fallback
    sample = read_slice(
        coarse, "z", z // 2, max(0, (y - max_side) // 2), max(0, (x - max_side) // 2),
        width=max_side,
    )
    finite = sample[np.isfinite(sample)]
    if not finite.size:
        return fallback
    if background is not None:
        foreground = finite[finite != background]
        share = 1 - foreground.size / finite.size
        if share >= BACKGROUND_MIN_FRACTION and foreground.size >= FOREGROUND_MIN_FRACTION * finite.size:
            finite = foreground
    low, high = (float(value) for value in np.percentile(finite.astype(np.float64), (1, 99)))
    return (low, high) if isfinite(low) and isfinite(high) and low < high else fallback
