"""Export registered spatial review sessions and a separate unscored CT packet."""

import argparse
import io
import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import numpy as np
import tifffile
from phase6_cuda import digest
from phase7_compare import load_previous
from phase8_spatial import surface_cube

from vesuvius_data_explorer.core.comparison import (
    Candidate,
    ComparisonView,
    load_comparison,
    roi_coordinates,
    save_comparison_session,
)
from vesuvius_data_explorer.core.ink_exam import candidate_id, export_examination
from vesuvius_data_explorer.core.ink_spatial import effect


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")


def _tif_bytes(array, axes):
    out = io.BytesIO()
    tifffile.imwrite(out, array, photometric="minisblack", metadata={"axes": axes})
    return out.getvalue()


def export_blind(path, stimuli, stack_uri):
    """Write only CT observations, coordinates and rendered support under neutral IDs."""
    index = {"version": 1, "source": stack_uri, "pixel_size_um": 2.215, "axes": ["z", "v", "u"],
             "slices_half_open": [28, 90], "central_slice": 59, "regions": []}
    with NamedTemporaryFile(dir=path.parent, prefix=f".{path.stem}-", delete=False) as file:
        stage = Path(file.name)
    try:
        with ZipFile(stage, "w") as archive:
            for label, origin, cube in stimuli:
                if (not label.isascii() or not label.isalnum() or len(cube.shape) != 3 or cube.shape[0] != 62
                        or cube.dtype != np.uint8 or min(cube.shape) < 1):
                    raise ValueError("Neutral IDs and registered uint8 CT cubes are required")
                files = {f"{label}/ct-ZVU.tif": _tif_bytes(cube, "ZYX"),
                         f"{label}/ct-59.tif": _tif_bytes(cube[31], "YX"),
                         f"{label}/valid-mask.tif": _tif_bytes(np.any(cube, axis=0).astype("u1"), "YX")}
                for name, raw in files.items():
                    archive.writestr(ZipInfo(name), raw, compress_type=ZIP_DEFLATED)
                index["regions"].append({"id": label, "start_vu": origin,
                                         "stop_vu": [p+s for p, s in zip(origin, cube.shape[1:])],
                                         "sha256": {n: sha256(raw).hexdigest() for n, raw in files.items()}})
            notes = ("Examen du rendu CT historique PHerc0500P2 · pas 2,215 µm.\n"
                     "Relever les bords, fibres, vides et continuités entre coupes. "
                     "Consigner les observations et incertitudes par identifiant de fenêtre.\n"
                     "Source Vesuvius Challenge Open Data, CC BY-NC 4.0. "
                     "Attribution : https://github.com/ScrollPrize/open-data#support-and-citation\n")
            archive.writestr(ZipInfo("LIRE.txt"), notes.encode("utf-8"), compress_type=ZIP_DEFLATED)
            archive.writestr(ZipInfo("ct-provenance.json"), json.dumps(index, indent=2),
                             compress_type=ZIP_DEFLATED)
        stage.replace(path)
    finally:
        stage.unlink(missing_ok=True)


def full_surface(work, source, maps, cube, report, metadata):
    folder = work/"surface"
    folder.mkdir(exist_ok=True)
    doc = json.loads(source.manifest.read_bytes())
    doc["origin_vu"] = [0, 0]
    doc["predictions"] = [p for p in doc["predictions"]
                          if p.get("provenance", {}).get("factorial_condition") in ("A+", "A-")]
    if len(doc["predictions"]) != 2:
        raise ValueError("One verified pair is required for the surface session")
    for entry, array in zip(doc["predictions"], maps):
        entry["provenance"].update({"experiment": metadata["fingerprints"],
                                    "raw_tiles_sha256": metadata["sha256_raw_tiles"],
                                    "geometry_revision": doc["surface_revision"]})
        tifffile.imwrite(folder/entry["path"], array, photometric="minisblack")
    tifffile.imwrite(folder/doc["ct"], cube[31], photometric="minisblack")
    tifffile.imwrite(folder/doc["surface"], cube[29:34].mean(axis=0).astype("f4"), photometric="minisblack")
    manifest = folder/"comparison.json"
    write_json(manifest, doc)
    full = load_comparison(manifest)
    controlled = []
    first = max((r for r in report["regions"] if r["status"] == "compared"),
                key=lambda x: x["valid_fraction"])["roi_vuhw"]
    for row in report["regions"]:
        if row["status"] == "compared":
            metric = row["statistics"]["absolute_Z_effect_block32"]
            label = f"{row['id']} · |ΔZ| {metric['estimate']:.3f} · {row['valid_fraction']*100:.0f} %"
            controlled.append(Candidate(label, tuple(row["roi_vuhw"]), models=(1, 2),
                                        selection="Grille fixe et support CT/Hann phase 8"))
    outcome = folder/"session.json"
    save_comparison_session(outcome, full, ComparisonView(0, (1, 2), 50, 100, False, tuple(first),
                                                          tuple(controlled), "z_sensitivity"))
    return outcome


def run(work, previous, report_path):
    phase7_file = previous/"examen-PHerc0500P2-phase7.zip"
    manifest_7 = json.loads(Path("docs/validation/phase7-model-comparison.json").read_bytes())
    if digest(phase7_file) != manifest_7["archive_sha256"]:
        raise ValueError("Phase 7 archive does not match its audited digest")
    plan = json.loads((work/"input-plan.json").read_bytes())
    run_info = json.loads((work/"cuda"/"run.json").read_bytes())
    report = json.loads(report_path.read_bytes())
    cube = surface_cube(plan, work, previous)
    assembled = work/"surface.npz"
    if digest(assembled) != report["surface_sha256"]:
        raise ValueError("Assembled scores do not match the audited report")
    with np.load(assembled, allow_pickle=False) as raster:
        maps, valid = raster["scores"], raster["valid"]
    with TemporaryDirectory(dir=work) as temp:
        pair, old_view = load_previous(Path(temp), phase7_file)
        full_session = full_surface(work, pair, maps, cube, report, run_info)
        records, annotated, stimuli = [], [], []
        # Preserve a deterministic ordering independent of candidate category names.
        items = sorted(old_view.candidates, key=lambda c: sha256(
            ("phase8-neutral-"+candidate_id(pair, c)).encode()).digest())
        for i, cand in enumerate(items, 1):
            coords = roi_coordinates(pair, cand.roi)
            v, u = coords["start_vu"]
            ve, ue = coords["stop_vu"]
            sl = np.s_[v:ve, u:ue]
            r, c, h, w = cand.roi
            near = np.s_[r:r+h, c:c+w]
            np.testing.assert_array_equal(pair.ct.pixels[near], cube[31][sl])
            for recorded, local in zip(pair.predictions[2:], maps):
                np.testing.assert_array_equal(recorded.image.pixels[near], local[sl])
            label = f"R{i:02d}"
            outcome = effect(maps[0][sl], maps[1][sl], valid[sl])
            old_id = candidate_id(pair, cand)
            annotated.append(replace(cand, models=(3, 4)))
            records.append({"neutral_id": label, "phase7_review_id": old_id, "original_label": cand.label,
                            "start_vu": coords["start_vu"], "stop_vu": coords["stop_vu"],
                            "ct_slice": 59, "surface_revision": pair.surface_revision,
                            "prior_observation": cand.observation, "prior_hypotheses": cand.comment,
                            "validation": "no_independent_ink_reference", "statistics": outcome})
            stimuli.append((label, coords["start_vu"], cube[:, sl[0], sl[1]]))
        destination = work/"examen-Z-phase8.zip"
        export_examination(destination, pair, replace(old_view, models=(3, 4), candidates=tuple(annotated),
                                                      mode="z_sensitivity", disagreement=False))
    blind = work/"CT-relecture-neutre-phase8.zip"
    export_blind(blind, stimuli, plan["uri"])
    return {"phase7_archive_sha256": digest(phase7_file), "with_scores_sha256": digest(destination),
            "neutral_ct_sha256": digest(blind), "full_surface_session_sha256": digest(full_session),
            "surface_png_source": report["surface_sha256"], "regions": records}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=Path)
    p.add_argument("spatial_report", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--phase7", type=Path, default=Path("data/phase7"))
    args = p.parse_args()
    write_json(args.output, run(args.work, args.phase7, args.spatial_report))
