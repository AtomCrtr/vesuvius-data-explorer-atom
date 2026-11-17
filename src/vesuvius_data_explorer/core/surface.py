"""Exploratory geometry checks for small coordinate patches (TIFXYZ-like)."""

from pathlib import Path

import numpy as np


def load_surface_patch(folder: str | Path, limit: int = 256) -> tuple[np.ndarray, ...]:
    """Read a TOP-LEFT subset of three local TIFF/NPY coordinate grids.

    TIFF requires memory-mappable/uncompressed pages to avoid accidentally
    decoding multi-gigabyte files. Never load full large TIFF files here.
    """
    import tifffile

    if not 8 <= limit <= 512:
        raise ValueError("Fenêtre autorisée : 8 à 512 pixels.")
    folder = Path(folder)
    coords = []
    for axis in ("x", "y", "z"):
        npy, tif = folder / f"{axis}.npy", folder / f"{axis}.tif"
        if npy.exists():
            data = np.load(npy, mmap_mode="r", allow_pickle=False)
        elif tif.exists():
            try:
                data = tifffile.memmap(tif)
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"{tif.name} n'est pas directement mappable ; convertir un extrait en .npy "
                    "avant analyse (ne pas charger la TIFF complète)."
                ) from exc
        else:
            raise FileNotFoundError(f"Fichier x/y/z manquant : {npy.name} ou {tif.name}")
        if data.ndim != 2:
            raise ValueError(f"La grille {axis} doit être 2D.")
        coords.append(np.asarray(data[:limit, :limit], dtype=np.float64))
    if len({v.shape for v in coords}) != 1:
        raise ValueError("Les trois grilles de coordonnées n'ont pas la même taille.")
    return tuple(coords)


def local_flip_pct(points: np.ndarray, valid: np.ndarray) -> float:
    """Percentage of adjacent grid cells whose normals point in opposite directions.

    A papyrus sheet winds around the scroll, so its normals legitimately cover every direction:
    comparing them with one global reference (the pre-T5 heuristic) flags about half of a healthy
    segment. A fold or a flipped patch shows instead as neighbouring cells with opposite normals.
    Heuristic, not a topology proof.
    """
    horizontal = points[:-1, 1:] - points[:-1, :-1]
    vertical = points[1:, :-1] - points[:-1, :-1]
    cells_ok = valid[:-1, :-1] & valid[1:, :-1] & valid[:-1, 1:]
    normals = np.cross(horizontal, vertical)
    norms = np.linalg.norm(normals, axis=-1)
    good = cells_ok & (norms > 1e-9)
    unit = np.zeros_like(normals)
    unit[good] = normals[good] / norms[good, None]
    pairs = flips = 0
    for a, b, ok in ((unit[:, :-1], unit[:, 1:], good[:, :-1] & good[:, 1:]),
                     (unit[:-1], unit[1:], good[:-1] & good[1:])):
        dots = np.einsum("...k,...k->...", a, b)[ok]
        pairs += dots.size
        flips += int(np.count_nonzero(dots < 0))
    return float(100 * flips / pairs) if pairs else float("nan")


def surface_metrics(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> dict[str, float]:
    """Patch diagnostics; normal flips are a local heuristic, not a full topology proof."""
    if x.shape != y.shape or x.shape != z.shape or x.ndim != 2:
        raise ValueError("Trois grilles de coordonnées 2D identiques requises.")
    if min(x.shape) < 2:
        raise ValueError("La grille doit contenir au moins 2×2 points.")
    points = np.stack([x, y, z], axis=-1).astype(np.float64)
    valid = np.isfinite(points).all(axis=2)
    h = points[:, 1:] - points[:, :-1]
    v = points[1:, :] - points[:-1, :]
    h_ok = valid[:, 1:] & valid[:, :-1]
    v_ok = valid[1:, :] & valid[:-1, :]
    h_lengths = np.linalg.norm(h[h_ok], axis=-1)
    v_lengths = np.linalg.norm(v[v_ok], axis=-1)
    steps = np.concatenate([h_lengths, v_lengths])

    flip_pct = local_flip_pct(points, valid)
    return {
        "valid_pct": float(100 * np.mean(valid)),
        "median_step": float(np.median(steps)) if steps.size else float("nan"),
        "p95_step": float(np.percentile(steps, 95)) if steps.size else float("nan"),
        "normal_flip_pct": flip_pct,
    }
