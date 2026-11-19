"""Load explicitly registered CT, surface and Reader planes in a shared (v, u) frame."""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import isfinite
from pathlib import Path

import numpy as np
import tifffile

MAX_COMPARISON_PIXELS = 2**20
MAX_PREDICTIONS = 4
MAX_MANIFEST_BYTES = 64 * 2**10


@dataclass(frozen=True)
class ComparisonPlane:
    path: Path
    pixels: np.ndarray


@dataclass(frozen=True)
class PredictionPlane:
    name: str
    model: str
    image: ComparisonPlane
    score_scale: float


@dataclass(frozen=True)
class SurfaceComparison:
    volume_id: str
    segment_id: str
    surface_revision: str
    origin_vu: tuple[int, int]
    pixel_size_um_vu: tuple[float, float]
    ct: ComparisonPlane
    surface: ComparisonPlane
    predictions: tuple[PredictionPlane, ...]


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Champ texte requis : {field}.")
    return value.strip()


def _positive_number(value: object, field: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"Nombre positif requis : {field}.")
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError(f"Nombre hors limites : {field}.") from exc
    if not isfinite(result) or result <= 0:
        raise ValueError(f"Nombre positif fini requis : {field}.")
    return result


def _plane(folder: Path, raw_path: object, field: str) -> ComparisonPlane:
    relative = Path(_text(raw_path, field))
    path = (folder / relative).resolve()
    if relative.is_absolute() or not path.is_relative_to(folder):
        raise ValueError(f"Chemin TIFF hors du dossier du manifeste : {field}.")
    if path.suffix.lower() not in {".tif", ".tiff"}:
        raise ValueError(f"Plan TIFF requis : {field}.")
    try:
        with tifffile.TiffFile(path) as tif:
            series = tif.series
            if (len(series) != 1 or len(tif.pages) != 1 or series[0].axes != "YX" or
                    len(series[0].shape) != 2 or series[0].size > MAX_COMPARISON_PIXELS or
                    series[0].dtype.kind not in "uif" or series[0].dtype.itemsize > 4):
                raise ValueError(f"Plan TIFF 2D scalaire ≤ {MAX_COMPARISON_PIXELS} pixels requis : {field}.")
            pixels = series[0].asarray()
    except (OSError, tifffile.TiffFileError) as exc:
        raise ValueError(f"Lecture TIFF impossible : {field}.") from exc
    if np.isinf(pixels).any() or not np.isfinite(pixels).any():
        raise ValueError(f"Valeurs TIFF non valides : {field}.")
    pixels.setflags(write=False)
    return ComparisonPlane(path, pixels)


def load_comparison(manifest: str | Path) -> SurfaceComparison:
    """Read a portable manifest and require one shared UV grid for every plane."""
    path = Path(manifest).resolve()
    with path.open("rb") as stream:
        encoded = stream.read(MAX_MANIFEST_BYTES + 1)
    if len(encoded) > MAX_MANIFEST_BYTES:
        raise ValueError("Manifeste de comparaison trop volumineux.")
    payload = json.loads(encoded)
    if (not isinstance(payload, dict) or type(payload.get("version")) is not int or
            payload["version"] != 1 or payload.get("axes") != ["v", "u"]):
        raise ValueError("Manifeste de comparaison v1 avec axes [v, u] requis.")
    ids = tuple(_text(payload.get(field), field)
                for field in ("volume_id", "segment_id", "surface_revision"))
    origin = payload.get("origin_vu")
    if (not isinstance(origin, list) or len(origin) != 2 or
            any(type(n) is not int or not 0 <= n < 2**31 for n in origin)):
        raise ValueError("Origine [v, u] requise, avec deux indices entiers positifs ou nuls.")
    scale = payload.get("pixel_size_um_vu")
    if not isinstance(scale, list) or len(scale) != 2:
        raise ValueError("Deux tailles physiques de pixel [v, u] sont requises.")
    scale = tuple(_positive_number(n, "pixel_size_um_vu") for n in scale)
    if not all(isfinite(n * step) for n, step in zip(origin, scale)):
        raise ValueError("Origine physique hors limites.")
    models = payload.get("predictions")
    if not isinstance(models, list) or not 1 <= len(models) <= MAX_PREDICTIONS:
        raise ValueError(f"De 1 à {MAX_PREDICTIONS} prédictions sont requises.")
    ct = _plane(path.parent, payload.get("ct"), "CT projeté")
    surface = _plane(path.parent, payload.get("surface"), "surface déroulée")
    if surface.pixels.shape != ct.pixels.shape:
        raise ValueError("CT et surface doivent partager la même grille UV.")
    predictions = {}
    for entry in models:
        if not isinstance(entry, dict):
            raise ValueError("Entrée de prédiction JSON invalide.")
        name = _text(entry.get("name"), "predictions.name")
        if name in predictions:
            raise ValueError(f"Nom de prédiction en double : {name}.")
        model = _text(entry.get("model"), "predictions.model")
        divisor = _positive_number(entry.get("score_scale"), "predictions.score_scale")
        image = _plane(path.parent, entry.get("path"), name)
        if image.pixels.shape != ct.pixels.shape:
            raise ValueError(f"Grille UV de {name} différente du CT.")
        if np.nanmin(image.pixels) < 0 or np.nanmax(image.pixels) > divisor:
            raise ValueError(f"Les scores de {name} doivent être compris entre 0 et {divisor:g}.")
        predictions[name] = PredictionPlane(name, model, image, divisor)
    return SurfaceComparison(*ids, tuple(origin), scale, ct, surface, tuple(predictions.values()))
