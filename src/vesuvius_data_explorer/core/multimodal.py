"""Open and export verified, local multimodal review bundles."""

import json
from hashlib import file_digest
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
import tifffile

from .optical_registration import Grid, landmarks_fit, spatial_uncertainty, warp_optical

LAYER_ROLES = ("ct", "surface", "a_plus", "a_minus", "height", "brightfield", "ink_mask")


def _paths(path, data):
    files = data["files"]
    if set(files) != set(LAYER_ROLES):
        raise ValueError("Le dossier doit décrire les sept couches CT et optiques.")
    for role, source in files.items():
        name = Path(source["path"])
        candidate = (path.parent / name).resolve()
        if name.is_absolute() or not candidate.is_relative_to(path.parent.resolve()):
            raise ValueError("Les couches doivent appartenir au dossier local.")
        with candidate.open("rb") as stream:
            if file_digest(stream, "sha256").hexdigest() != source["sha256"]:
                raise ValueError(f"Empreinte incorrecte pour {role}.")
        yield role, candidate


def _grid(raster, spec):
    return Grid(raster.shape[:2], tuple(spec["pitch_um"]), tuple(spec["origin_um"]))


def load_multimodal(path):
    path = Path(path).resolve()
    data = json.loads(path.read_bytes())
    if data["version"] != 1:
        raise ValueError("Version de dossier multimodal inconnue.")
    images = {role: tifffile.imread(file) for role, file in _paths(path, data)}
    ct, optical = _grid(images["ct"], data["ct"]), _grid(images["height"], data["optical"])
    for role in ("ct", "surface", "a_plus", "a_minus", "height", "ink_mask"):
        if images[role].shape != (ct.shape if role in LAYER_ROLES[:4] else optical.shape):
            raise ValueError(f"Dimensions inattendues pour {role}.")
    if images["brightfield"].shape != (*optical.shape, 3):
        raise ValueError("La photographie doit être RGB sur la grille du relief.")
    if not np.isin(images["ink_mask"], (0, 1)).all():
        raise ValueError("Le masque d’encre doit être binaire.")
    identity = data["identity"]
    report = None
    if data.get("landmarks"):
        options = data["geometry"]
        report = landmarks_fit(data["landmarks"], optical, ct, feature_um=options["feature_um"],
                               kind=options["kind"], parity=options["parity"])
    linked = (report is not None and report["quality_gate"] and
              identity["location"] == "confirmed" and identity["scale"] == "confirmed")
    if linked:
        support = np.isfinite(images["height"])
        for role in ("height", "brightfield", "ink_mask"):
            pixels, valid = warp_optical(images[role], optical, ct, report, support=support,
                                         discrete=(role == "ink_mask"))
            images["registered_"+role] = pixels
            if role == "height":
                images["uncertainty"] = spatial_uncertainty(ct, report, valid)
    return data, ct, optical, images, report


def export_multimodal(path, destination):
    path, destination = Path(path).resolve(), Path(destination).resolve()
    data = json.loads(path.read_bytes())
    verified = dict(_paths(path, data))
    if destination in (path, *verified.values()):
        raise ValueError("Préserver le manifeste et les images sources.")
    with NamedTemporaryFile(dir=destination.parent, suffix=".zip", delete=False) as tmp:
        stage = Path(tmp.name)
    try:
        with ZipFile(stage, "w", ZIP_DEFLATED) as archive:
            archive.write(path, path.name)
            for entry in sorted(set(verified.values())):
                archive.write(entry, entry.relative_to(path.parent).as_posix())
        stage.replace(destination)
    finally:
        stage.unlink(missing_ok=True)
