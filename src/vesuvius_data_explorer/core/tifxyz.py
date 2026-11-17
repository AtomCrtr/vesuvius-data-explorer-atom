"""VC3D ``tifxyz`` segments: three float32 coordinate grids plus ``meta.json``.

Facts this reader relies on (docs/tasks/T5-surfaces-vc3d.md):

- ``x.tif``, ``y.tif``, ``z.tif`` hold level-0 voxel coordinates of the target volume, in
  [x, y, z] order; this module returns (z, y, x) like the rest of the core;
- invalid points are (-1, -1, -1); other negative values are valid points outside the volume;
- most files are uncompressed, a few are tiled LZW with a floating-point predictor, which
  ``tifffile`` only decodes with ``imagecodecs``: Pillow is the fallback;
- the largest files (up to 443 MiB per grid) are uncompressed strips, so rows can be fetched
  with range requests: beyond the byte budget, one row and one column out of ``stride`` are read.
"""

from __future__ import annotations

import io
import json
import math
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import numpy as np

from .volume import ALLOWED_HTTPS_HOSTS

DEFAULT_MAX_BYTES = 64 * 2**20
AXES_FILES = ("z", "y", "x")  # Read in this order so the stack is directly (z, y, x).
GRID_STEP_VOXELS = 20  # scale = 0.05 for every catalogued segment.


@dataclass(frozen=True)
class TifxyzSurface:
    points: np.ndarray  # (rows, cols, 3) float64, (z, y, x) level-0 voxels, NaN where invalid
    meta: dict[str, Any]
    grid_shape: tuple[int, int]  # Full grid in the files, before any decimation.
    stride: int
    source: str
    bytes_read: int
    warnings: tuple[str, ...] = field(default=())

    @property
    def valid(self) -> np.ndarray:
        return np.isfinite(self.points).all(axis=2)

    @property
    def step_voxels(self) -> float:
        """Distance between displayed grid points, from ``meta.json`` when available."""
        scale = self.meta.get("scale")
        base = GRID_STEP_VOXELS
        if isinstance(scale, list) and scale and isinstance(scale[0], (int, float)) and scale[0] > 0:
            base = 1.0 / float(scale[0])
        return base * self.stride


def _filesystem(source: str):
    """(fsspec filesystem, root path) under the same access rules as volumes."""
    import fsspec

    source = source.strip().rstrip("/")
    if not source:
        raise ValueError("Indiquer le dossier ou l'URI d'un segment tifxyz.")
    if "://" not in source:
        return fsspec.filesystem("file"), source
    scheme = source.split("://", 1)[0].lower()
    if scheme == "s3":
        return fsspec.filesystem("s3", anon=True), source.split("://", 1)[1]
    if scheme == "https" and urlsplit(source).hostname in ALLOWED_HTTPS_HOSTS:
        return fsspec.filesystem("https"), source
    raise ValueError(
        "Utiliser un dossier local, une URI s3:// publique ou une URL HTTPS officielle "
        "(data.aws.ash2txt.org) ; cette adresse de segment n'est pas prise en charge."
    )


@dataclass(frozen=True)
class _Header:
    shape: tuple[int, int]
    dtype: np.dtype
    compressed: bool
    tiled: bool
    rows_per_strip: int
    offsets: tuple[int, ...]

    @property
    def nbytes(self) -> int:
        return self.shape[0] * self.shape[1] * self.dtype.itemsize


def _header(fs, path: str) -> _Header:
    import tifffile

    try:
        with fs.open(path, "rb", block_size=1 << 16) as handle:
            tif = tifffile.TiffFile(handle)
            page = tif.pages[0]
            dtype = np.dtype(page.dtype).newbyteorder(tif.byteorder)
            header = _Header(
                shape=tuple(int(n) for n in page.shape),
                dtype=dtype,
                compressed=page.compression.value != 1,
                tiled=bool(page.is_tiled),
                rows_per_strip=int(page.rowsperstrip or page.shape[0]) if not page.is_tiled else 0,
                offsets=tuple(int(n) for n in page.dataoffsets),
            )
    except FileNotFoundError as error:
        raise FileNotFoundError(f"Grille introuvable : {path}") from error
    except tifffile.TiffFileError as error:
        raise ValueError(f"{path.rsplit('/', 1)[-1]} n'est pas un TIFF lisible.") from error
    if len(header.shape) != 2:
        raise ValueError(f"{path.rsplit('/', 1)[-1]} doit être une grille 2D.")
    if header.dtype.kind != "f":
        raise ValueError(f"{path.rsplit('/', 1)[-1]} doit contenir des coordonnées flottantes.")
    return header


def _decode(raw: bytes, name: str) -> np.ndarray:
    import tifffile

    try:
        return tifffile.imread(io.BytesIO(raw))
    except ValueError as error:
        if "imagecodecs" not in str(error):
            raise ValueError(f"{name} : TIFF illisible.") from error
    # LZW with a floating-point predictor needs imagecodecs in tifffile; Pillow decodes it.
    try:
        from PIL import Image
    except ImportError as error:  # pragma: no cover - Pillow is a core dependency
        raise ValueError(
            f"{name} est compressé : installer Pillow ou imagecodecs pour le décoder."
        ) from error
    with Image.open(io.BytesIO(raw)) as image:
        return np.asarray(image, dtype=np.float32)


def _strided_rows(fs, path: str, header: _Header, stride: int) -> tuple[np.ndarray, int]:
    """One row out of ``stride`` from an uncompressed strip TIFF, by range requests."""
    rows, cols = header.shape
    row_bytes = cols * header.dtype.itemsize
    starts = []
    for row in range(0, rows, stride):
        strip, within = divmod(row, header.rows_per_strip)
        starts.append(header.offsets[strip] + within * row_bytes)
    chunks = fs.cat_ranges([path] * len(starts), starts, [s + row_bytes for s in starts])
    data = np.frombuffer(b"".join(chunks), dtype=header.dtype).reshape(len(starts), cols)
    return data[:, ::stride], len(starts) * row_bytes


def choose_stride(shape: tuple[int, int], itemsize: int, max_bytes: int) -> int:
    """Smallest row stride so that one grid's fetched rows fit in ``max_bytes``."""
    rows, cols = shape
    if rows * cols * itemsize <= max_bytes:
        return 1
    row_bytes = cols * itemsize
    if row_bytes > max_bytes:
        raise ValueError("Budget inférieur à une seule ligne de la grille.")
    return max(2, math.ceil(rows / (max_bytes // row_bytes)))


def _meta(fs, root: str) -> tuple[dict[str, Any], tuple[str, ...]]:
    try:
        meta = json.loads(fs.cat(f"{root}/meta.json"))
        if isinstance(meta, dict):
            return meta, ()
    except (OSError, ValueError):
        pass
    return {}, ("meta.json absent ou illisible : pas de bbox ni d'échelle de grille.",)


def load_tifxyz(source: str, *, max_bytes: int = DEFAULT_MAX_BYTES) -> TifxyzSurface:
    """Read a tifxyz segment within a per-grid byte budget (see module docstring)."""
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
        raise ValueError("Le budget en octets doit être un entier strictement positif.")
    fs, root = _filesystem(source)
    if "://" not in source and all(fs.exists(f"{root}/{axis}.npy") for axis in AXES_FILES):
        return _load_npy(fs, root, source, max_bytes)
    headers = {axis: _header(fs, f"{root}/{axis}.tif") for axis in AXES_FILES}
    shapes = {header.shape for header in headers.values()}
    if len(shapes) != 1:
        raise ValueError("Les grilles x, y et z n'ont pas la même forme.")
    shape = shapes.pop()
    if min(shape) < 2:
        raise ValueError("La grille doit contenir au moins 2 × 2 points.")
    itemsize = max(header.dtype.itemsize for header in headers.values())
    stride = choose_stride(shape, itemsize, max_bytes)
    grids, bytes_read = [], 0
    for axis in AXES_FILES:
        header, path = headers[axis], f"{root}/{axis}.tif"
        if stride == 1:
            raw = fs.cat(path)
            grid = _decode(raw, f"{axis}.tif")
            bytes_read += len(raw)
        elif header.compressed or header.tiled:
            raise ValueError(
                f"{axis}.tif : grille compressée de {header.nbytes / 2**20:.0f} Mio, au-delà du "
                f"budget de {max_bytes / 2**20:.0f} Mio ; lecture décimée impossible. Augmenter "
                "le budget."
            )
        else:
            grid, fetched = _strided_rows(fs, path, header, stride)
            bytes_read += fetched
        if grid.ndim != 2:
            raise ValueError(f"{axis}.tif doit être une grille 2D.")
        grids.append(np.asarray(grid, dtype=np.float64))
    return _surface(fs, root, source, grids, shape, stride, bytes_read)


def _surface(fs, root, source, grids, shape, stride, bytes_read) -> TifxyzSurface:
    points = np.stack(grids, axis=-1)
    invalid = (points == -1).all(axis=2) | ~np.isfinite(points).all(axis=2)
    points[invalid] = np.nan
    meta, warnings = _meta(fs, root)
    if stride > 1:
        warnings += (
            f"Budget : grille {shape[0]} × {shape[1]} lue une ligne et une colonne sur {stride}.",
        )
    return TifxyzSurface(points, meta, shape, stride, source.strip().rstrip("/"), bytes_read,
                         warnings)


def _load_npy(fs, root, source, max_bytes) -> TifxyzSurface:
    """Local ``x/y/z.npy`` grids (synthetic demo, extracts): memory-mapped, same budget rule."""
    arrays = [np.load(f"{root}/{axis}.npy", mmap_mode="r", allow_pickle=False)
              for axis in AXES_FILES]
    if any(array.ndim != 2 for array in arrays):
        raise ValueError("Les grilles x, y et z doivent être 2D.")
    if len({array.shape for array in arrays}) != 1:
        raise ValueError("Les grilles x, y et z n'ont pas la même forme.")
    shape = tuple(int(n) for n in arrays[0].shape)
    if min(shape) < 2:
        raise ValueError("La grille doit contenir au moins 2 × 2 points.")
    stride = choose_stride(shape, max(array.dtype.itemsize for array in arrays), max_bytes)
    grids = [np.asarray(array[::stride, ::stride], dtype=np.float64) for array in arrays]
    bytes_read = sum(grid.size * array.dtype.itemsize for grid, array in zip(grids, arrays))
    return _surface(fs, root, source, grids, shape, stride, bytes_read)


MAX_HOLES = 20


def _holes(valid: np.ndarray) -> tuple[np.ndarray, np.ndarray, int]:
    """Invalid regions not connected to the grid border (4-connectivity).

    Invalid points touching the border are the irregular outline of the segment, not defects.
    Returns (hole mask, label image, number of labels).
    """
    from scipy import ndimage

    labels, count = ndimage.label(~valid)  # Default structure: 4-connectivity in 2D.
    border = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    outside = np.isin(labels, border[border > 0])
    holes = (labels > 0) & ~outside
    labels = np.where(holes, labels, 0)
    return holes, labels, count


def hole_locations(surface: TifxyzSurface, labels: np.ndarray, count: int) -> list[dict]:
    """The largest holes: grid box (in full-grid rows/columns) and volume (z, y, x) centre."""
    from scipy import ndimage

    if count == 0 or not labels.any():
        return []
    sizes = np.bincount(labels.ravel(), minlength=count + 1)
    sizes[0] = 0
    order = [int(i) for i in np.argsort(sizes)[::-1] if sizes[i] > 0][:MAX_HOLES]
    boxes = ndimage.find_objects(labels)
    valid = surface.valid
    holes = []
    for label in order:
        rows, cols = boxes[label - 1]
        mask = labels == label
        # The ring of valid neighbours encloses the hole: its mean position is the centre.
        ring = ndimage.binary_dilation(mask) & valid
        center = surface.points[ring].mean(axis=0) if ring.any() else None
        holes.append({
            "size_points": int(sizes[label]),
            "origin": (rows.start * surface.stride, cols.start * surface.stride),
            "size": ((rows.stop - rows.start) * surface.stride,
                     (cols.stop - cols.start) * surface.stride),
            "center": None if center is None else tuple(float(c) for c in center),
        })
    return holes


def tifxyz_metrics(surface: TifxyzSurface, volume_shape=None) -> dict[str, Any]:
    """Quality indicators of a tifxyz segment; see docs/tasks/T5-surfaces-vc3d.md."""
    from .surface import surface_metrics

    valid = surface.valid
    holes, labels, count = _holes(valid)
    enclosed = int(valid.sum() + holes.sum())
    z, y, x = (surface.points[..., axis] for axis in range(3))
    metrics = surface_metrics(z, y, x)  # Lengths and flip ratios ignore the axis order.
    metrics["hole_pct"] = float(100 * holes.sum() / enclosed) if enclosed else 0.0
    metrics["holes"] = hole_locations(surface, labels, count)
    metrics["out_of_bounds_pct"] = None
    if volume_shape is not None:
        inside = in_volume(surface.points, volume_shape)
        total = int(valid.sum())
        metrics["out_of_bounds_pct"] = (
            float(100 * (total - inside.sum()) / total) if total else 0.0
        )
    return metrics


def in_volume(points: np.ndarray, volume_shape) -> np.ndarray:
    """Mask of finite points inside [0, size) on every axis; ``points`` is (..., 3) zyx."""
    mask = np.isfinite(points).all(axis=-1)
    for axis, size in enumerate(volume_shape):
        mask &= (points[..., axis] >= 0) & (points[..., axis] < size)
    return mask
