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


def surface_metrics(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> dict[str, float]:
    """Patch diagnostics; normal flips are a heuristic, not a full topology proof."""
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

    horizontal = points[:-1, 1:] - points[:-1, :-1]
    vertical = points[1:, :-1] - points[:-1, :-1]
    cells_ok = valid[:-1, :-1] & valid[1:, :-1] & valid[:-1, 1:]
    normals = np.cross(horizontal[cells_ok], vertical[cells_ok])
    norms = np.linalg.norm(normals, axis=-1)
    good = norms > 1e-9
    flip_pct = float("nan")
    if good.any():
        unit = normals[good] / norms[good, None]
        reference = np.median(unit, axis=0)
        reference_norm = np.linalg.norm(reference)
        if reference_norm > 1e-9:
            flip_pct = float(100 * (np.sum(unit @ reference < 0) / len(unit)))

    return {
        "valid_pct": float(100 * np.mean(valid)),
        "median_step": float(np.median(steps)) if steps.size else float("nan"),
        "p95_step": float(np.percentile(steps, 95)) if steps.size else float("nan"),
        "normal_flip_pct": flip_pct,
    }
