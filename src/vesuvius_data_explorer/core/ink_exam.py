"""Select auditable review regions and export a portable local examination."""

import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import numpy as np

from .comparison import (
    Candidate,
    _output_file,
    _provenance,
    _roi,
    export_comparison_png,
    load_comparison,
    roi_coordinates,
    save_comparison_session,
)
from .ink_disagreement import top_masks


def review_stage(candidate):
    if candidate.character_confirmed:
        return "caractere_valide_par_expertise"
    if candidate.hypothesis:
        return "caractere_hypothetique"
    if candidate.ink_candidate:
        return "encre_candidate"
    if candidate.observation:
        return "trace_observee"
    return "a_examiner"


def candidate_id(comparison, candidate):
    """Identify a selected window and its models independently of mutable review notes."""
    key = json.dumps([comparison.manifest_sha256, candidate.roi, candidate.models,
                      candidate.label], ensure_ascii=False).encode()
    return sha256(key).hexdigest()[:20]


def propose_candidates(comparison, models, roi, side=128):
    """Take distinct score-ranked blocks on a fixed grid, without looking for letter shapes."""
    v, u, h, w = _roi(roi, comparison.ct.pixels.shape)
    if not 1 <= side <= 128 or len(models) != 2 or len(set(models)) != 2 or not all(
            type(index) is int and 1 <= index <= len(comparison.predictions) for index in models):
        raise ValueError("Deux modèles distincts et une taille de bloc valide sont requis.")
    a, b = (comparison.predictions[i-1].image.pixels[v:v+h, u:u+w] for i in models)
    finite = np.isfinite(a) & np.isfinite(b)
    ad, bd = top_masks(a, b, finite, 0.05)
    categories = (("A seule", ad & ~bd), ("B seule", bd & ~ad), ("A et B", ad & bd),
                  ("Témoin bas", (a < comparison.predictions[models[0]-1].score_scale*0.2)
                                 & (b < comparison.predictions[models[1]-1].score_scale*0.2)))
    rows = []
    for y in range(0, h-side+1, side):
        for x in range(0, w-side+1, side):
            box = np.s_[y:y+side, x:x+side]
            n = int(finite[box].sum())
            if n >= 0.75*side**2:
                rows.append((y, x, n, [int((mask[box] & finite[box]).sum()) for _, mask in categories]))
    selected = []
    for i, (category, _) in enumerate(categories):
        eligible = (row for row in rows if row[3][i] > 0)
        best = min(eligible, key=lambda r: (-r[3][i]/r[2], r[0], r[1]), default=None)
        if best is None:
            continue
        rows.remove(best)
        y, x, n, counts = best
        criterion = "scores <20 % A et B" if i == 3 else "top 5 % par carte, ex æquo inclus"
        selection = f"{category} · {criterion} · {counts[i]}/{n} · grille {side} · ROI {tuple(roi)}"
        selected.append(Candidate(f"{category} · V{v+y} U{u+x}", (v+y, u+x, side, side),
                                  models=tuple(models), ink_candidate=i != 3, selection=selection))
    return tuple(selected)


def export_examination(path, comparison, view):
    """Atomically archive review metadata, original TIFFs and a reopenable session."""
    path = Path(path).resolve()
    provenance = _provenance(comparison)
    files = {comparison.ct.path, comparison.surface.path, *(p.image.path for p in comparison.predictions)}
    files.add(comparison.manifest)
    with _output_file(path, comparison) as temporary, TemporaryDirectory(dir=path.parent) as folder:
        staging = Path(folder)
        source = staging / "sources"
        for original in files:
            target = source / original.relative_to(comparison.manifest.parent)
            target.parent.mkdir(parents=True, exist_ok=True)
            with original.open("rb") as stream:
                raw = stream.read((16 << 20) + 1)
            if len(raw) > (16 << 20):
                raise ValueError("Un fichier source dépasse la limite de 16 Mio.")
            target.write_bytes(raw)
        archived = load_comparison(source / comparison.manifest.name)
        if _provenance(archived) != provenance:
            raise ValueError("Le manifeste ou les pixels sources ont changé depuis l’ouverture.")
        save_comparison_session(staging/"session.json", archived, view)
        export_comparison_png(staging/"apercu.png", archived, view)
        files = sorted(item for item in staging.rglob("*") if item.is_file())
        index = {"format": "vesuvius-ink-examination", "version": 1, "selection_stage": "descriptive",
                 "samples": [{"id": candidate_id(archived, c), "stage": review_stage(c),
                              "coordinates": roi_coordinates(archived, c.roi), "selection": c.selection,
                              "label": c.label, "models": [archived.predictions[i-1].model for i in c.models]}
                             for c in view.candidates],
                 "sha256": {f.relative_to(staging).as_posix(): sha256(f.read_bytes()).hexdigest()
                            for f in files}}
        with ZipFile(temporary, "w") as archive:
            for item in files:
                name = item.relative_to(staging).as_posix()
                archive.writestr(ZipInfo(name), item.read_bytes(), compress_type=ZIP_DEFLATED)
            archive.writestr(ZipInfo("examen.json"), json.dumps(index, ensure_ascii=False, indent=2)+"\n",
                             compress_type=ZIP_DEFLATED)
