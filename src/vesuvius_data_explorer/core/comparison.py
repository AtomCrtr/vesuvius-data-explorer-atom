"""Load explicitly registered CT, surface and Reader planes in a shared (v, u) frame."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from os import replace
from os.path import relpath
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np
import tifffile
from PIL import Image, PngImagePlugin

# The complete historical PHerc0500P2 raster contains 1,624,000 pixels.
MAX_COMPARISON_PIXELS = 2**21
MAX_PREDICTIONS = 4
MAX_MANIFEST_BYTES = 64 * 2**10
MAX_CANDIDATES = 256
MAX_SESSION_BYTES = 256 * 2**10
PREDICTION_COLORS = ((1.0, 0.32, 0.12), (0.15, 0.72, 1.0))
CONSENSUS_COLOR = (0.4, 0.9, 0.48)
UNCERTAIN_COLORS = ((0.95, 0.72, 0.18), (0.7, 0.45, 0.85))
Z_SENSITIVITY_COLOR = (1.0, 0.30, 0.10)
UNCERTAINTY_MARGIN = 5
CANDIDATE_STATUS = "candidat_non_valide"
REVIEWED_STATUS = "validation_externe_documentee"
CONFIDENCE_LEVELS = ("non_evaluee", "faible", "moyenne", "haute")


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
    provenance: dict | None = None
    calibration: dict | None = None
    registration: dict | None = None


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
    manifest: Path
    manifest_sha256: str


@dataclass(frozen=True)
class Candidate:
    label: str
    roi: tuple[int, int, int, int]
    observation: str = ""
    hypothesis: str = ""
    confidence: str = "non_evaluee"
    comment: str = ""
    reviewer: str = ""
    evidence: str = ""
    models: tuple[int, ...] = ()
    ink_candidate: bool = False
    palaeography_reference: str = ""
    character_confirmed: bool = False
    selection: str = ""


@dataclass(frozen=True)
class ComparisonView:
    reference: int
    models: tuple[int, int]  # 0 = none, then 1-based indices into predictions
    threshold: int
    opacity: int
    disagreement: bool
    roi: tuple[int, int, int, int]  # local [v, u, height, width]
    candidates: tuple[Candidate, ...] = ()
    mode: str = "overlay"


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
            if tif.pages[0].tags.valueof("Orientation", 1) != 1:
                raise ValueError(f"Orientation TIFF incompatible avec la grille [v, u] : {field}.")
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
    if not all(isfinite((n + length) * step)
               for n, length, step in zip(origin, ct.pixels.shape, scale)):
        raise ValueError("Étendue physique hors limites.")
    surface = _plane(path.parent, payload.get("surface"), "surface déroulée")
    if surface.pixels.shape != ct.pixels.shape:
        raise ValueError("CT et surface doivent partager la même grille UV.")
    predictions = {}
    face = None
    expected_grid = {"axes": ["v", "u"], "orientation_vu": ["+v", "+u"], "origin_vu": origin,
                     "pixel_size_um_vu": list(scale), "surface_revision": ids[2]}
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
        provenance = entry.get("provenance")
        if provenance is not None and not isinstance(provenance, dict):
            raise ValueError(f"Objet de provenance requis : {name}.")
        calibration = entry.get("calibration")
        if calibration is not None:
            if not isinstance(calibration, dict):
                raise ValueError(f"Objet de calibration requis : {name}.")
            for field in ("method", "reference", "event"):
                _text(calibration.get(field), f"calibration.{field}")
        registration = entry.get("registration")
        if registration is not None:
            if (not isinstance(registration, dict)
                    or any(registration.get(key) != value for key, value in expected_grid.items())):
                raise ValueError(f"Recalage déclaré incompatible avec la grille du manifeste : {name}.")
            declared_face = _text(registration.get("face"), "registration.face")
            _text(registration.get("evidence"), "registration.evidence")
            if face is not None and declared_face != face:
                raise ValueError("Les cartes déclarent des faces différentes.")
            face = declared_face
        predictions[name] = PredictionPlane(name, model, image, divisor, provenance, calibration,
                                            registration)
    return SurfaceComparison(*ids, tuple(origin), scale, ct, surface, tuple(predictions.values()),
                             path, sha256(encoded).hexdigest())


def _above(plane: PredictionPlane, threshold: int) -> np.ndarray:
    return plane.image.pixels >= plane.score_scale * (threshold / 100)


def near_threshold(pixels, scale, threshold):
    low = scale * ((threshold - UNCERTAINTY_MARGIN) / 100)
    high = scale * ((threshold + UNCERTAINTY_MARGIN) / 100)
    return (pixels >= low) & (pixels <= high)


def disagreement_codes(a: PredictionPlane, b: PredictionPlane, threshold: int) -> np.ndarray:
    """0 = agreement or missing, 1 = A alone, 2 = B alone at the shared threshold."""
    a_positive, b_positive = _above(a, threshold), _above(b, threshold)
    valid = np.isfinite(a.image.pixels) & np.isfinite(b.image.pixels)
    out = np.zeros(valid.shape, dtype=np.uint8)
    out[valid & a_positive & ~b_positive] = 1
    out[valid & b_positive & ~a_positive] = 2
    return out


def calibrated_pair(a: PredictionPlane, b: PredictionPlane) -> bool:
    return (a.calibration is not None and b.calibration is not None
            and a.calibration["event"] == b.calibration["event"])


def comparable_probabilities(a: PredictionPlane, b: PredictionPlane) -> bool:
    return (calibrated_pair(a, b) and a.registration is not None and b.registration is not None
            and all(a.registration[key] == b.registration[key] for key in (
                "axes", "orientation_vu", "origin_vu", "pixel_size_um_vu", "surface_revision", "face")))


def orientation_pair(a, b):
    """Require the same registered experiment and opposite declared Z conditions."""
    x, y = (item.provenance or {} for item in (a, b))
    cells = (x.get("factorial_condition"), y.get("factorial_condition"))
    if cells not in (("A+", "A-"), ("A-", "A+"), ("B+", "B-"), ("B-", "B+")):
        return False
    train = x.get("experiment")
    return (isinstance(train, dict) and isinstance(train.get("weights_sha256"), str)
            and len(train["weights_sha256"]) == 64 and train == y.get("experiment")
            and a.score_scale == b.score_scale)


def comparison_values(a: PredictionPlane, b: PredictionPlane, threshold: int, mode: str):
    """Use raw source scores. Missing pixels stay missing in continuous differences."""
    if mode in ("difference", "z_sensitivity"):
        if mode == "z_sensitivity" and not orientation_pair(a, b):
            raise ValueError("La sensibilité Z exige deux ordres du même checkpoint et de la même expérience.")
        a_score = np.divide(a.image.pixels, a.score_scale, dtype=np.float64)
        b_score = np.divide(b.image.pixels, b.score_scale, dtype=np.float64)
        delta = a_score - b_score
        return (np.abs(delta) if mode == "z_sensitivity" else delta).astype(np.float32)
    if mode == "consensus":
        return (_above(a, threshold) & _above(b, threshold)).astype(np.uint8)
    if mode == "disagreement":
        return disagreement_codes(a, b, threshold)
    if mode == "uncertainty":
        valid = np.isfinite(a.image.pixels) & np.isfinite(b.image.pixels)
        near = np.zeros(valid.shape, dtype=bool)
        for plane in (a, b):
            near |= near_threshold(plane.image.pixels, plane.score_scale, threshold)
        result = np.zeros(valid.shape, dtype=np.uint8)
        result[valid & near] = 1
        result[~valid] = 2
        return result
    raise ValueError("Analyse de comparaison inconnue.")


def _roi(value, shape):
    if (not isinstance(value, (list, tuple)) or len(value) != 4
            or any(type(n) is not int for n in value)):
        raise ValueError("Région UV invalide.")
    v, u, height, width = value
    if not (0 <= v < v + height <= shape[0] and 0 <= u < u + width <= shape[1]):
        raise ValueError("Région UV hors de la grille.")
    return v, u, height, width


def _state(payload, comparison):
    if not isinstance(payload, dict):
        raise ValueError("Paramètres de comparaison invalides.")
    reference, threshold, opacity = (payload.get(name) for name in (
        "reference", "threshold", "opacity"))
    models, disagreement = payload.get("models"), payload.get("disagreement")
    mode = payload.get("mode", "overlay")
    if (type(reference) is not int or reference not in (0, 1)
            or type(threshold) is not int or not 1 <= threshold <= 99
            or type(opacity) is not int or not 0 <= opacity <= 100
            or type(disagreement) is not bool
            or mode not in ("overlay", "consensus", "difference", "uncertainty", "z_sensitivity")
            or not isinstance(models, (list, tuple)) or len(models) != 2
            or any(type(n) is not int or not 0 <= n <= len(comparison.predictions) for n in models)
            or (models[0] == models[1] != 0)):
        raise ValueError("Paramètres de comparaison invalides.")
    if mode == "z_sensitivity" and (not all(models) or not orientation_pair(
            *(comparison.predictions[i-1] for i in models))):
        raise ValueError("La sensibilité Z exige une paire d’ordres vérifiée.")
    shape = comparison.ct.pixels.shape
    roi = _roi(payload.get("roi"), shape)
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or len(candidates) > MAX_CANDIDATES:
        raise ValueError("Liste de caractères candidats invalide.")
    annotations = []
    for candidate in candidates:
        if not isinstance(candidate, dict) or candidate.get("status") not in (CANDIDATE_STATUS,
                                                                                REVIEWED_STATUS):
            raise ValueError("Statut de caractère candidat non pris en charge.")
        label = _text(candidate.get("label"), "caractère candidat")
        if len(label) > 80:
            raise ValueError("Libellé de caractère candidat trop long.")
        fields = {key: candidate.get(key, "") for key in (
            "observation", "hypothesis", "comment", "reviewer", "evidence",
            "palaeography_reference", "selection")}
        if any(not isinstance(value, str) or len(value) > 240 for value in fields.values()):
            raise ValueError("Les notes d'une observation sont limitées à 240 caractères par champ.")
        fields = {key: value.strip() for key, value in fields.items()}
        reviewed = candidate["status"] == REVIEWED_STATUS
        if (bool(fields["reviewer"]) != reviewed or bool(fields["evidence"]) != reviewed):
            raise ValueError("La validation externe requiert une référence et une personne.")
        ink_candidate = candidate.get("ink_candidate", False)
        character_confirmed = candidate.get("character_confirmed", False)
        if type(ink_candidate) is not bool or type(character_confirmed) is not bool:
            raise ValueError("Étapes de relecture invalides.")
        if character_confirmed and not (reviewed and ink_candidate and all(
                fields[key] for key in ("observation", "hypothesis", "palaeography_reference"))):
            raise ValueError("La validation de caractère exige une observation, une hypothèse et ses références.")
        confidence = candidate.get("confidence", "non_evaluee")
        if confidence not in CONFIDENCE_LEVELS:
            raise ValueError("Niveau de confiance invalide.")
        indices = candidate.get("models", ())
        if (not isinstance(indices, (list, tuple)) or len(indices) > 2
                or any(type(n) is not int or not 1 <= n <= len(comparison.predictions) for n in indices)
                or len(set(indices)) != len(indices)):
            raise ValueError("Cartes sources de l'observation invalides.")
        annotations.append(Candidate(label, _roi(candidate.get("roi"), shape),
                                     **fields, confidence=confidence, models=tuple(indices),
                                     ink_candidate=ink_candidate, character_confirmed=character_confirmed))
    return ComparisonView(reference, tuple(models), threshold, opacity, disagreement, roi,
                          tuple(annotations), mode)


def _plane_provenance(plane: ComparisonPlane, folder: Path) -> dict:
    pixels = plane.pixels
    return {"path": plane.path.relative_to(folder).as_posix(), "dtype": pixels.dtype.str,
            "sha256_pixels": sha256(np.ascontiguousarray(pixels).view("u1")).hexdigest()}


def _provenance(comparison):
    folder = comparison.manifest.parent
    return {
        "manifest_sha256": comparison.manifest_sha256,
        "volume_id": comparison.volume_id,
        "segment_id": comparison.segment_id,
        "surface_revision": comparison.surface_revision,
        "axes": ["v", "u"],
        "origin_vu": list(comparison.origin_vu),
        "pixel_size_um_vu": list(comparison.pixel_size_um_vu),
        "shape_vu": list(comparison.ct.pixels.shape),
        "ct": _plane_provenance(comparison.ct, folder),
        "surface": _plane_provenance(comparison.surface, folder),
        "predictions": [{**_plane_provenance(item.image, folder), "name": item.name,
                         "model": item.model, "score_scale": item.score_scale,
                         "provenance": item.provenance,
                         **({"calibration": item.calibration} if item.calibration else {}),
                         **({"registration": item.registration} if item.registration else {})}
                        for item in comparison.predictions],
    }


def roi_coordinates(comparison, roi):
    """Half-open bounds in source pixels and micrometres, in V/U order."""
    v, u, height, width = roi
    start = [i + j for i, j in zip(comparison.origin_vu, (v, u))]
    stop = [start[0] + height, start[1] + width]
    return {"start_vu": start, "stop_vu": stop,
            "start_um_vu": [i * s for i, s in zip(start, comparison.pixel_size_um_vu)],
            "stop_um_vu": [i * s for i, s in zip(stop, comparison.pixel_size_um_vu)]}


def _session(path, comparison, view):
    try:
        manifest = Path(relpath(comparison.manifest, path.parent)).as_posix()
    except ValueError:  # Two Windows drive letters.
        manifest = comparison.manifest.as_posix()
    settings = {"reference": view.reference, "models": view.models, "threshold": view.threshold,
                "opacity": view.opacity, "disagreement": view.disagreement, "roi": view.roi,
                "mode": view.mode,
                "candidates": [
                    {"label": item.label, "roi": item.roi,
                     "status": REVIEWED_STATUS if item.evidence or item.reviewer else CANDIDATE_STATUS,
                     "observation": item.observation, "hypothesis": item.hypothesis,
                     "confidence": item.confidence, "comment": item.comment,
                     "reviewer": item.reviewer, "evidence": item.evidence, "models": item.models,
                     "ink_candidate": item.ink_candidate, "character_confirmed": item.character_confirmed,
                     "palaeography_reference": item.palaeography_reference, "selection": item.selection,
                     "coordinates": roi_coordinates(comparison, item.roi)}
                    for item in view.candidates]}
    _state(settings, comparison)
    return {"version": 1, "type": "vesuvius_comparison", "manifest": manifest,
            "sources": _provenance(comparison), "settings": settings,
            "roi_coordinates": roi_coordinates(comparison, view.roi),
            "interpretation": "Scores de modèles et caractères candidats à valider."}


def load_comparison_session(path: str | Path) -> tuple[SurfaceComparison, ComparisonView]:
    path = Path(path).resolve()
    with path.open("rb") as stream:
        encoded = stream.read(MAX_SESSION_BYTES + 1)
    if len(encoded) > MAX_SESSION_BYTES:
        raise ValueError("Session de comparaison trop volumineuse.")
    payload = json.loads(encoded)
    if (not isinstance(payload, dict) or payload.get("type") != "vesuvius_comparison"
            or type(payload.get("version")) is not int or payload["version"] != 1):
        raise ValueError("Format de session de comparaison invalide.")
    comparison = load_comparison(path.parent / _text(payload.get("manifest"), "manifest"))
    if _provenance(comparison) != payload.get("sources"):
        raise ValueError("Le manifeste ou les pixels sources ont changé depuis l’enregistrement.")
    return comparison, _state(payload.get("settings"), comparison)


@contextmanager
def _output_file(path, comparison):
    if path in (comparison.manifest, comparison.ct.path, comparison.surface.path,
                *(item.image.path for item in comparison.predictions)):
        raise ValueError("Choisir un chemin de sortie distinct des fichiers sources.")
    with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        yield temporary
        replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def save_comparison_session(path: str | Path, comparison: SurfaceComparison, view: ComparisonView):
    path = Path(path).resolve()
    encoded = json.dumps(_session(path, comparison, view), ensure_ascii=False, allow_nan=False)
    if len(encoded.encode("utf-8")) + 1 > MAX_SESSION_BYTES:
        raise ValueError("Session de comparaison trop volumineuse.")
    with _output_file(path, comparison) as temporary:
        temporary.write_text(encoded + "\n", encoding="utf-8")


def export_comparison_png(path: str | Path, comparison: SurfaceComparison, view: ComparisonView):
    """Compose a native-resolution ROI with the shared UV display settings."""
    path = Path(path).resolve()
    metadata = _session(path, comparison, view)
    v, u, height, width = view.roi
    window = np.s_[v:v+height, u:u+width]
    base = (comparison.ct, comparison.surface)[view.reference].pixels
    low, high = float(np.nanmin(base)), float(np.nanmax(base))
    gray = np.zeros((height, width), dtype=np.float32)
    if high > low:
        gray = np.nan_to_num((base[window].astype(np.float64) - low) / (high - low), nan=0)
    rgb = np.repeat(gray[..., None], 3, axis=-1)
    models = [comparison.predictions[i - 1] if i else None for i in view.models]
    mode = "disagreement" if view.mode == "overlay" and view.disagreement else view.mode
    weights = (None, None)
    colors = PREDICTION_COLORS
    if mode != "overlay":
        if all(models):
            values = comparison_values(*models, view.threshold, mode)[window]
            if mode == "difference":
                weights = (np.maximum(values, 0), np.maximum(-values, 0))
            elif mode == "z_sensitivity":
                weights, colors = (values, None), (Z_SENSITIVITY_COLOR, Z_SENSITIVITY_COLOR)
            elif mode == "consensus":
                weights, colors = (values, None), (CONSENSUS_COLOR, CONSENSUS_COLOR)
            elif mode == "uncertainty":
                weights, colors = (values == 1, values == 2), UNCERTAIN_COLORS
            else:
                weights = (values == 1, values == 2)
        else:
            weights = (None, None)
    else:
        weights = (_above(model, view.threshold)[window] if model else None for model in models)
    opacity = view.opacity / 100 * (0.8 if mode == "overlay" else 1)
    for weight, color in zip(weights, colors):
        if weight is not None:
            alpha = np.nan_to_num(weight, nan=0)[..., None] * opacity
            rgb = (1 - alpha) * rgb + alpha * np.asarray(color)
    image = Image.fromarray(np.rint(255 * rgb).astype(np.uint8))
    info = PngImagePlugin.PngInfo()
    info.add_itxt("vesuvius_comparison", json.dumps(metadata, ensure_ascii=False, allow_nan=False))
    with _output_file(path, comparison) as temporary:
        image.save(temporary, format="PNG", pnginfo=info)
