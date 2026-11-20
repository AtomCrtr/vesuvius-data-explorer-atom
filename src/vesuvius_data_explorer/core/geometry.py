"""Sampling conventions verified against the values of published CT pyramids."""

from dataclasses import dataclass

import numpy as np

# Exact source identities covered by the adjacent-level comparisons in phase4_geometry.py.
# Extent ratios are still used when a source or its metadata lies outside that evidence.
_PARIS45 = ((4071, 2264, 2264), (2036, 1132, 1132), (1018, 566, 566), (509, 283, 283))
_VERIFIED = {
    "s3://vesuvius-challenge-open-data/PHercParis4/volumes/"
    "20260310170716-45.532um-11.0m-74keV-masked.zarr": _PARIS45,
    "s3://vesuvius-challenge-open-data/PHercParis4/volumes/"
    "20260310170716-45.532um-11.0m-74keV-masked-fast-q1-c64-v0.3.2.vcd3d.zarr": _PARIS45,
    "https://data.aws.ash2txt.org/samples/PHercParis4/volumes/"
    "20230205180739-7.910um-54keV-masked.zarr": (
        (14258, 7888, 8096), (7129, 3944, 4048), (3565, 1972, 2024), (1783, 986, 1012)),
    "s3://vesuvius-challenge-open-data/PHerc0800/volumes/"
    "20250521135224-8.640um-1.2m-116keV-masked.zarr": (
        (24298, 9867, 9867), (12149, 4934, 4934), (6075, 2467, 2467), (3038, 1234, 1234)),
}


@dataclass(frozen=True)
class VerifiedSampling:
    source: str
    factors: tuple[tuple[float, float, float], ...]


def verified_sampling(source: str, levels) -> VerifiedSampling | None:
    """Select box-centre sampling only for the checked source, shapes and metadata."""
    source = source.strip().rstrip("/")
    shapes = _VERIFIED.get(source)
    if shapes is None or tuple(level.shape for level in levels[:len(shapes)]) != shapes:
        return None
    factors = tuple((float(2**i),) * 3 for i in range(len(shapes)))
    for i, (level, factor) in enumerate(zip(levels, factors)):
        if (level.key != str(i) or not level.scale_from_metadata or level.scale != factor
                or level.translation != (0, 0, 0)):
            return None
    return VerifiedSampling(source, factors)


def to_level(points, factor):
    """Map L0 voxel centres into a coarser grid with coincident outer voxel edges."""
    return (points + 0.5) / factor - 0.5


def level_factors(shapes, sampling=None) -> np.ndarray:
    """Return level-0 voxels per sample on each axis."""
    base = np.asarray(shapes[0], dtype=float)
    factors = np.array([base / np.asarray(shape, dtype=float) for shape in shapes])
    if sampling is not None:
        count = min(len(factors), len(sampling.factors))
        factors[:count] = sampling.factors[:count]
    return factors


def sampling_details(shapes, level, sampling=None) -> dict:
    factor = level_factors(shapes, sampling)[level]
    verified = sampling is not None and level < len(sampling.factors)
    return {"convention": "verified_box_centres" if verified else "historical_extent_ratio",
            "factor_zyx": factor.tolist(), "l0_origin_zyx": ((factor - 1) / 2).tolist(),
            "verified_source": sampling.source if verified else None}
