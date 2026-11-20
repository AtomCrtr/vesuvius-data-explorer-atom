"""Assemble both controlled A conditions and compare fixed, physically registered regions."""

import argparse
import json
import shutil
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import tifffile
from phase6_cuda import digest
from phase7_experiment import CHUNK, read_tile

from vesuvius_data_explorer.core.comparison import load_comparison, load_comparison_session
from vesuvius_data_explorer.core.ink_exam import candidate_id, export_examination
from vesuvius_data_explorer.core.ink_factorial import factorial_report, summarize_pair


def assemble(origins, tiles, validity, region):
    """Overlap-add in published UV order with one shared denominator."""
    v, u, h, w = region
    if tiles.ndim != 4 or tiles.shape[1:] != validity.shape or len(origins) != len(validity):
        raise ValueError("Tiles and validity masks do not share the same layout")
    num = np.zeros((len(tiles), h, w), "f4")
    den = np.zeros((h, w), "f4")
    weights = np.outer(*(np.hanning(n).astype("f4") for n in validity.shape[1:]))
    weights /= weights.sum()
    for i, (y, x) in enumerate(origins):
        y0, y1 = max(v, y), min(v+h, y+weights.shape[0])
        x0, x1 = max(u, x), min(u+w, x+weights.shape[1])
        if y0 >= y1 or x0 >= x1:
            continue
        t = np.s_[y0-y:y1-y, x0-x:x1-x]
        r = np.s_[y0-v:y1-v, x0-u:x1-u]
        win = weights[t]*validity[i][t]
        candidates = tiles[:, i, t[0], t[1]]
        if not np.isfinite(candidates[:, win > 0]).all():
            raise ValueError("Non-finite tile output within shared coverage")
        den[r] += win
        num[:, r[0], r[1]] += np.where(win > 0, candidates, 0)*win
    covered = den > 0
    return np.divide(num, den, where=covered, out=np.full_like(num, np.nan)), covered


def describe(original, controlled, support):
    a, b = original
    ap, am = controlled
    common = support & (a > 0) & (b > 0)
    compare = {"public_A/public_B": (a, b, (255, 255)),
               "public_A/A+": (a, ap, (255, 1)), "public_A/A-": (a, am, (255, 1)),
               "public_B/A+": (b, ap, (255, 1)), "public_B/A-": (b, am, (255, 1))}
    rank_effect = (ap-am)[support]
    a_codes = (np.clip(ap[common], 0, 1)*255).astype("u1")
    code_error = np.abs(a_codes.astype("i2")-a[common])
    by_support = {key: factorial_report({"A+": (ap, 1), "A-": (am, 1)}, mask)
                  for key, mask in (("ct_hann_support", support), ("also_public_nonzero", common))}
    return {"factorial": by_support, "published_proximity_descriptive": {
                key: summarize_pair(x, y, common, scales) for key, (x, y, scales) in compare.items()},
            "mean_signed_Aplus_minus_Aminus": float(rank_effect.mean()) if rank_effect.size else None,
            "mean_absolute_Aplus_minus_Aminus": float(np.abs(rank_effect).mean()) if rank_effect.size else None,
            "public_A_quantized_diagnostic": {
                "paired_pixels": int(code_error.size),
                "exact_fraction": float((code_error == 0).mean()) if code_error.size else None,
                "mean_absolute_code_error": float(code_error.mean()) if code_error.size else None,
                "max_absolute_code_error": int(code_error.max()) if code_error.size else None}}


def make_manifest(folder, previous, run, results):
    """Carry original TIFF geometry into a local comparison with the new A conditions."""
    previous_folder = previous.parent
    doc = json.loads(previous.read_bytes())
    folder.mkdir(exist_ok=True, parents=True)
    for name in [doc["ct"], doc["surface"], *(row["path"] for row in doc["predictions"])]:
        shutil.copyfile(previous_folder/name, folder/name)
    for cell, scores in zip(("A+", "A-"), results):
        name = f"canonical_A_{'positive_Z' if cell == 'A+' else 'negative_Z'}.tif"
        tifffile.imwrite(folder/name, scores, photometric="minisblack")
        doc["predictions"].append({"name": cell+" · canonique public",
                                   "model": "ink_canonical_2um · "+cell,
                                   "path": name, "score_scale": 1.0,
                                   "provenance": {"factorial_condition": cell,
                                                  "experiment": run["inputs"],
                                                  "raw_tiles_sha256": run["outputs_sha256"],
                                                  "layers_half_open": [28, 90], "step_uv": 128,
                                                  "blend": "Hann", "clip_divisor": 200,
                                                  "z_order": "ascending" if cell == "A+" else "descending",
                                                  "face": "unknown"}})
    path = folder/"comparison.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return path


def load_previous(work, baseline):
    """Read the locally generated phase 6 archive after checking each named member."""
    folder = work/"phase6-session"
    folder.mkdir(exist_ok=True)
    with ZipFile(baseline) as archive:
        meta = json.loads(archive.read("examen.json"))
        for name, expected in meta["sha256"].items():
            target = (folder/name).resolve()
            if not target.is_relative_to(folder.resolve()):
                raise ValueError("Archive member escapes the local destination")
            data = archive.read(name)
            if sha256(data).hexdigest() != expected:
                raise ValueError(f"Changed phase 6 archive member: {name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    return load_comparison_session(folder/"session.json")


def run(work, phase6, phase4, audit_file, notes_file=None):
    input_plan = json.loads((work/"input-plan.json").read_bytes())
    run_meta = json.loads((work/"cuda"/"run.json").read_bytes())
    raw = work/"cuda"/"tiles.npz"
    if digest(raw) != run_meta["outputs_sha256"]:
        raise ValueError("Raw CUDA data differ from the run report")
    if digest(work/"input-plan.json") != run_meta["inputs"]["plan_sha256"]:
        raise ValueError("Input plan differs from the run report")
    archive = phase6/"examen-PHerc0500P2.zip"
    original_comparison, previous_view = load_previous(work, archive)
    notes = json.loads(notes_file.read_bytes()) if notes_file else {}
    audit = json.loads(audit_file.read_bytes())
    entire = []
    for model in ("20260417190342", "20260709123958"):
        path = phase6/f"{model}.full.tif"
        if digest(path) != audit["production_bindings"][model]["sha256_tiff"]:
            raise ValueError("Published TIFF differs from the audited artifact")
        entire.append(tifffile.imread(path))

    with np.load(raw, allow_pickle=False) as groups:
        origins = [tuple(a) for a in groups["origins"]]
        valid = groups["valid"]
        arrays = np.stack([groups["A_plus_scores"], groups["A_minus_scores"]])
        tile_id = origins.index((512, 512))
        phase6_equal = {order: np.array_equal(
            groups[f"{label}_logits"][tile_id], np.load(phase6/f"fp32-{order}-logits.npy"))
                        for order, label in (("normal", "A_plus"), ("reversed_z", "A_minus"))}
        repeat = work/"cuda-repeat"/"tiles.npz"
        repeat_equal = None
        if repeat.is_file():
            repeat_report = json.loads((repeat.parent/"run.json").read_bytes())
            if repeat_report["inputs"] != run_meta["inputs"] or repeat_report["outputs_sha256"] != digest(repeat):
                raise ValueError("The repeat run has a different fingerprint")
            with np.load(repeat, allow_pickle=False) as replica:
                repeat_equal = {name: bool(np.array_equal(groups[name], replica[name])) for name in groups.files}

    matrix, scores = {}, {}
    for label, roi in input_plan["regions_vuhw"].items():
        v, u, h, w = roi
        uv = np.s_[v:v+h, u:u+w]
        result, support = assemble(origins, arrays, valid, roi)
        scores[label] = result, support
        matrix[label] = {"origin_vu": [v, u], "shape_vu": [h, w],
                         **describe([a[uv] for a in entire], result, support)}
        np.savez_compressed(work/f"{label}-assembled.npz", scores=result, support=support)

    local = load_comparison(phase4)
    all_scores, support = scores["review"]
    v0, u0 = local.origin_vu
    a, b = (p.image.pixels for p in local.predictions)
    h, w = a.shape
    for small, full in zip((a, b), entire):
        np.testing.assert_array_equal(small, full[v0:v0+h, u0:u0+w])
    chunks = {tuple(r["key"]): np.memmap(work/"chunks"/f"{r['key'][0]}-{r['key'][1]}.raw",
                                         "u1", "r", shape=CHUNK) for r in input_plan["chunks"]}
    central = read_tile(chunks, 512, 512)[59-28]
    np.testing.assert_array_equal(central, local.ct.pixels[512-v0:768-v0, 512-u0:768-u0])
    path = make_manifest(work/"review", phase4, run_meta, all_scores)
    new_comparison = load_comparison(path)
    candidates = []
    for item in previous_view.candidates:
        v, u, h, w = item.roi
        box = np.s_[v:v+h, u:u+w]
        old_id = candidate_id(original_comparison, item)
        row = {"origin_vu": [v+v0, u+u0], "shape_vu": [h, w],
               "ct_sha256": sha256(local.ct.pixels[box].tobytes()).hexdigest(),
               **describe([a[box], b[box]], all_scores[:, box[0], box[1]], support[box])}
        annotation = notes.get(old_id, {})
        updated = replace(item, observation=annotation.get("observation", ""),
                          comment=annotation.get("incertitude", ""))
        row["annotation"] = annotation
        row["reopen_id"] = candidate_id(new_comparison, updated)
        matrix[old_id] = row
        candidates.append(updated)
    export = work/"examen-PHerc0500P2-phase7.zip"
    export_examination(export, new_comparison, replace(previous_view, candidates=tuple(candidates)))
    return {"phase6_archive_sha256": digest(archive), "phase6_tile_logit_equal": phase6_equal,
            "independent_process_equal": repeat_equal,
            "raw_ct_at_59_exact_match": True, "scoring": matrix,
            "napari_manifest_sha256": digest(path), "archive_sha256": digest(export)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--phase6", type=Path, default=Path("data/phase6"))
    parser.add_argument("--phase4", type=Path, default=Path("data/phase4-ink/comparison-phase5.json"))
    parser.add_argument("--audit", type=Path, default=Path("docs/validation/phase7-checkpoints.json"))
    parser.add_argument("--notes", type=Path)
    args = parser.parse_args()
    result = run(args.work, args.phase6, args.phase4, args.audit, args.notes)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
