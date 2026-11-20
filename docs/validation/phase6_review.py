"""Verify EduceLab records, summarize the CUDA order test and export an examination."""

import argparse
import json
from pathlib import Path

import numpy as np
import tifffile
from phase4_ink import dump, sha
from phase5_reference import decode, select

from vesuvius_data_explorer.core.comparison import ComparisonView, load_comparison, roi_coordinates
from vesuvius_data_explorer.core.consensus import rank_agreement
from vesuvius_data_explorer.core.ink_disagreement import correlations
from vesuvius_data_explorer.core.ink_exam import (
    candidate_id,
    export_examination,
    propose_candidates,
)


def audit_references(index, folder):
    source = json.loads(index.read_bytes())
    rows = []
    for fragment in source["fragments"]:
        root = folder / fragment["regions"][0]["id"].split("/")[0]
        for filename, metadata in fragment["sources"].items():
            if filename != "ct" and sha((root/filename).read_bytes()) != metadata["sha256"]:
                raise ValueError(f"Unexpected EduceLab source bytes: {filename}")
        mask = decode((root/"mask.png").read_bytes(), binary=True)
        ink = decode((root/"inklabels.png").read_bytes(), binary=True) & mask
        ir = decode((root/"ir.png").read_bytes())
        selected = select(mask, ink)
        for record in fragment["regions"]:
            v, u, h, w = selected[record["kind"]]
            assert record["start_vu"] == [v, u] and record["stop_vu"] == [v+h, u+w]
            box = np.s_[v:v+h, u:u+w]
            planes = {name: tifffile.imread(folder/record["id"]/f"{name}.tif")
                      for name in ("ct", "ir", "labels")}
            if any(sha(data.tobytes()) != record["pixels_sha256"][name] for name, data in planes.items()):
                raise ValueError(f"Reference pixels changed: {record['id']}")
            np.testing.assert_array_equal(planes["labels"], np.where(mask[box], ink[box], 255))
            np.testing.assert_array_equal(planes["ir"], ir[box])
            artifact = record["kind"] == "mask_edge_artifact"
            rows.append({"id": record["id"], "parent_scroll": fragment["parent_scroll"],
                         "start_vu": record["start_vu"], "stop_vu": record["stop_vu"],
                         "pixels_sha256": record["pixels_sha256"], "label_counts": record["labels"],
                         "ct_zeros_in_mask": int(np.count_nonzero((planes["ct"] == 0) & mask[box])),
                         "ct_zeros_outside_mask": int(np.count_nonzero((planes["ct"] == 0) & ~mask[box])),
                         "use": "geometry_and_mask_QA" if artifact else "exploratory_reference_and_QA",
                         "independent_of_ink_tiffs": True, "training_exclusion_proven": False,
                         "eligible_for_generalization_metrics": False})
    return rows


def summarize_cuda(directory, metadata_file, manifest, repeat=None):
    metadata = json.loads(metadata_file.read_bytes())
    precision = metadata["settings"]["autocast"]
    scores = []
    for order in ("normal", "reversed_z"):
        run = metadata["runs"][order]
        raw = np.load(directory/f"{precision}-{order}-logits.npy", allow_pickle=False)
        score = np.load(directory/f"{precision}-{order}-scores.npy", allow_pickle=False)
        if sha(raw.tobytes()) != run["logits_sha256"] or sha(score.tobytes()) != run["scores_sha256"]:
            raise ValueError("CUDA output digest mismatch")
        scores.append(score)
    a, b = scores
    a_interior, b_interior = a[64:192, 64:192], b[64:192, 64:192]
    comparison = load_comparison(manifest)
    v, u = (position - origin for position, origin in
            zip(metadata["data"]["origin_vu"], comparison.origin_vu))
    ct = np.load(directory/"ct-v512-u512.npy", allow_pickle=False)
    midpoint = ct[59 - metadata["data"]["layer_slice"][0]]
    window = np.s_[v:v+a.shape[0], u:u+a.shape[1]]
    aligned = np.array_equal(midpoint, comparison.ct.pixels[window], equal_nan=False)
    if not aligned:
        raise ValueError("The CUDA tile is misaligned with the phase 4 CT raster")
    replication = None
    if repeat is not None:
        rerun = json.loads(repeat.read_bytes())
        assert all(metadata[k] == rerun[k] for k in ("data", "code", "weights", "settings"))
        replication = {}
        for order, data in rerun["runs"].items():
            assert all(data[k] == metadata["runs"][order][k] for k in ("logits_sha256", "scores_sha256"))
            replication[order] = {k: data[k] for k in ("logits_sha256", "scores_sha256", "times_ms")}
    return {"scope": "normal vs reversed Z with strictly identical public A weights",
            "raw_stack_plane_59_exactly_matches_phase4_ct": aligned,
            "cross_process_repeat": replication,
            "scores_range": [[float(z.min()), float(z.max())] for z in scores],
            "mean_absolute_score_difference": float(np.abs(a-b).mean()),
            "full_tile": correlations(a, b), "center_128": correlations(a_interior, b_interior),
            "top": rank_agreement(a.ravel(), b.ravel(), (0.01, 0.05, 0.20)),
            "center_top": rank_agreement(a_interior.ravel(), b_interior.ravel(), (0.01, 0.05, 0.20)),
            "input_clip_fraction": float((ct > 200).mean())}


def export_review(manifest, output):
    c = load_comparison(manifest)
    roi = (0, 0, *c.ct.pixels.shape)
    models = (1, 2)
    candidates = propose_candidates(c, models, roi)
    view = ComparisonView(0, models, 50, 100, True, roi, candidates)
    export_examination(output, c, view)
    return {"manifest_sha256": c.manifest_sha256, "archive_sha256": sha(output.read_bytes()),
            "selected_on": roi_coordinates(c, roi), "display": {"threshold": 50, "opacity": 100,
                                                                "mode": "disagreement"},
            "models": [{"id": p.model, "provenance": p.provenance} for p in c.predictions],
            "regions": [{"id": candidate_id(c, item), "label": item.label,
                         "coordinates": roi_coordinates(c, item.roi), "selection": item.selection}
                        for item in candidates]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("reference_dir", type=Path)
    parser.add_argument("reference_index", type=Path)
    parser.add_argument("cuda_report", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cuda-repeat", type=Path)
    args = parser.parse_args()
    report = {
        "educe_lab": audit_references(args.reference_index, args.reference_dir),
        "cuda_order_effect": summarize_cuda(args.work, args.cuda_report, args.manifest, args.cuda_repeat),
        "examination": export_review(args.manifest, args.work/"examen-PHerc0500P2.zip"),
    }
    dump(args.output, report)
