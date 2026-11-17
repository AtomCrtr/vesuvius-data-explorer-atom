"""Small synthetic examples; never presented as original papyrus CT data."""

import numpy as np


def demo_volume(shape: tuple[int, int, int] = (80, 288, 288), seed: int = 42) -> np.ndarray:
    """Generate a layered 3D image resembling, but not reproducing, CT structures."""
    z, y, x = np.ogrid[: shape[0], : shape[1], : shape[2]]
    r = np.sqrt(((x - shape[2] / 2) / 1.08) ** 2 + (y - shape[1] / 2) ** 2)
    folds = 10 * np.cos((r / 6) + (z / 20))
    layers = np.exp(-(((np.mod(r + folds, 17) - 8.5) / 2.2) ** 2))
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, 0.08, size=shape)
    return np.uint8(np.clip((0.13 + 0.65 * layers + noise) * 255, 0, 255))


def demo_surface(size: int = 180) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """A synthetic TIFXYZ-like coordinate grid with an intentionally missing patch."""
    yy, xx = np.mgrid[:size, :size].astype(float)
    zz = 6 * np.sin(xx / 20) + 4 * np.cos(yy / 19)
    xx[60:75, 50:70] = np.nan
    yy[60:75, 50:70] = np.nan
    zz[60:75, 50:70] = np.nan
    return xx, yy, zz
