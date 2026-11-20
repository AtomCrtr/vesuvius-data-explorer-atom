"""Compute fixed-grid robustness and CT/mesh covariates for the full A intervention."""

import argparse
import json
from pathlib import Path
from time import perf_counter

import numpy as np
import tifffile
from phase6_cuda import digest
from phase7_compare import assemble
from phase7_experiment import CHUNK, working_set_peak
from phase8_cuda import open_chunks
from scipy.ndimage import distance_transform_edt, map_coordinates
from scipy.stats import spearmanr

from vesuvius_data_explorer.core.ink_disagreement import correlations
from vesuvius_data_explorer.core.ink_spatial import effect, windows
from vesuvius_data_explorer.core.tifxyz import load_tifxyz

BLOCK = 128


def surface_cube(metadata, work, previous):
    _, h, w = metadata["shape_zvu"]
    stack = np.zeros((62, h, w), "u1")
    chunks = open_chunks(metadata, work, previous)
    for (v, u), data in chunks.items():
        height, width = min(h-v*128, CHUNK[1]), min(w-u*128, CHUNK[2])
        stack[:, v*128:v*128+height, u*128:u*128+width] = data[28:90, :height, :width]
    return stack


def mesh_features(mesh, shape):
    """Use dense knot-support interpolation and an approximate knot-scale bend."""
    basis = mesh.points[..., ::-1]
    tangent_v, tangent_u = np.gradient(basis, axis=(0, 1))
    cross = np.cross(tangent_u, tangent_v)
    norm = np.linalg.norm(cross, axis=-1, keepdims=True)
    normals = np.divide(cross, norm, where=norm > 0, out=np.full_like(cross, np.nan))
    bend = np.full(mesh.valid.shape, np.nan)
    v_dot = (normals[2:, 1:-1] * normals[:-2, 1:-1]).sum(axis=-1)
    u_dot = (normals[1:-1, 2:] * normals[1:-1, :-2]).sum(axis=-1)
    bend[1:-1, 1:-1] = np.degrees(np.arccos(np.clip((v_dot+u_dot)/2, -1, 1)))
    shape_k = np.meshgrid(*(np.arange(n)/mesh.step_voxels for n in shape), indexing="ij")
    quality = map_coordinates(mesh.valid.astype(float), shape_k, order=1, mode="constant", cval=0) >= .9999
    # Keep estimates anchored to actual nodes instead of inventing curvature over invalid knots.
    dense_bend = map_coordinates(bend, shape_k, order=0, mode="constant", cval=np.nan)
    return quality, dense_bend


def ct_features(ct, paired, distances, knots, bend):
    if not paired.any():
        return {}
    center = ct[31].astype("f4")
    samples = center[paired]
    differences = np.concatenate((np.abs(np.diff(center, axis=0))[paired[1:] & paired[:-1]],
                                  np.abs(np.diff(center, axis=1))[paired[:, 1:] & paired[:, :-1]]))
    low, high = np.percentile(samples, [10, 90])
    left, right = ct[:31, paired].astype("f4"), ct[:30:-1, paired]
    computed_bend = bend[paired & np.isfinite(bend)]
    return {"ct_p90_minus_p10": float(high-low),
            "ct_neighbor_abs_mean": float(differences.mean()) if differences.size else None,
            "ct_depth_mirror_abs_mean": float(np.abs(left-right).mean()),
            "ct_depth_signed_half_mean": float((left-right).mean()),
            "ct_inside_zeros": float((ct[:, paired] == 0).mean()),
            "support_border_median_px": float(np.median(distances[paired])),
            "support_fraction": float(paired.mean()),
            "tifxyz_bilinear_support_fraction": float(knots[paired].mean()),
            "tifxyz_bend_median_deg": float(np.median(computed_bend)) if computed_bend.size else None,
            "tifxyz_bend_fraction": int(computed_bend.size)/int(paired.sum())}


def regional_table(cube, scores, valid, knots, bend):
    distances = distance_transform_edt(np.pad(valid, 1))[1:-1, 1:-1]
    rows = []
    for v, u, h, w in windows(valid.shape, BLOCK):
        box = np.s_[v:v+h, u:u+w]
        support = valid[box]
        row = {"id": f"V{v}-U{u}", "roi_vuhw": [v, u, h, w], "valid_count": int(support.sum()),
               "valid_fraction": float(support.mean())}
        admitted = min(h, w) >= 64 and support.sum() >= 1024
        row["status"] = "compared" if admitted else "insufficient_registered_support"
        if admitted:
            statistics = effect(scores[0][box], scores[1][box], support)
            interior = support & (distances[box] > 16)
            row.update({"covariates": ct_features(cube[:, box[0], box[1]], support,
                                                  distances[box], knots[box], bend[box]),
                        "statistics": statistics,
                        "interior_16px": effect(scores[0][box], scores[1][box], interior)
                        if interior.sum() >= 1024 else None})
        rows.append(row)
    return rows


def compare_covariates(rows):
    measured = [r for r in rows if r["status"] == "compared"]
    keys = measured[0]["covariates"] if measured else {}
    correlations = {}
    for key in keys:
        pairs = [(r["covariates"][key], r["statistics"]["absolute_Z_effect_block32"]["estimate"])
                 for r in measured if r["covariates"][key] is not None]
        if len(pairs) < 4:
            continue
        x, y = np.array(pairs).T
        correlations[key] = {"windows": len(pairs), "spearman": float(spearmanr(x, y).statistic)
                              if np.ptp(x) > 0 and np.ptp(y) > 0 else None}
    return correlations


def evidence(work, previous, mesh_folder, phase7_manifest):
    t0 = perf_counter()
    plan = json.loads((work/"input-plan.json").read_bytes())
    run = json.loads((work/"cuda"/"run.json").read_bytes())
    repeat = json.loads((work/"cuda-repeat"/"run.json").read_bytes())
    main, check = work/"cuda"/"tiles.npz", work/"cuda-repeat"/"tiles.npz"
    if digest(main) != run["sha256_raw_tiles"] or digest(check) != repeat["sha256_raw_tiles"]:
        raise ValueError("Raw inference arrays do not match their reports")
    if any(run["fingerprints"][key] != value for key, value in repeat["fingerprints"].items()
           if key != "repeat") or digest(work/"input-plan.json") != run["fingerprints"]["input_plan_sha256"]:
        raise ValueError("The run and independent repeat must use the same audited settings")
    cube = surface_cube(plan, work, previous)
    with np.load(main, allow_pickle=False) as archive, np.load(check, allow_pickle=False) as replica:
        origins = [tuple(a) for a in archive["origins"]]
        repeat_ids = [origins.index(tuple(a)) for a in replica["origins"]]
        equality = {key: bool(np.array_equal(archive[key][repeat_ids], replica[key], equal_nan=True))
                    for key in replica.files}
        if not all(equality.values()):
            raise ValueError("The independent repeat changed the raw output")
        matrices = np.stack((archive["A_plus_scores"], archive["A_minus_scores"]))
        scores, valid = assemble(origins, matrices, archive["valid"], (0, 0, *cube.shape[1:]))
    v, u, h, w = json.loads((previous/"input-plan.json").read_bytes())["regions_vuhw"]["review"]
    roi = np.s_[v:v+h, u:u+w]
    old_ct = tifffile.imread(phase7_manifest.parent/"ct.tif")
    np.testing.assert_array_equal(old_ct, cube[31][roi])
    with np.load(previous/"review-assembled.npz", allow_pickle=False) as baseline:
        np.testing.assert_array_equal(baseline["scores"], scores[:, roi[0], roi[1]])
    mesh = load_tifxyz(str(mesh_folder.resolve()))
    knots, bend = mesh_features(mesh, valid.shape)
    rows = regional_table(cube, scores, valid, knots, bend)
    margin = distance_transform_edt(np.pad(valid, 1))[1:-1, 1:-1]
    interior = valid & (margin > 16)
    zero = np.where(valid, scores, 0)
    result = {"input_plan_sha256": digest(work/"input-plan.json"), "raw_tiles_sha256": digest(main),
              "repeat_tiles": len(repeat_ids), "repeat_arrays_equal": equality,
              "phase7_review_and_CT59_exactly_reproduced": True, "shape_vu": valid.shape,
              "window_policy": {"side": BLOCK, "min_side": 64, "min_valid_pixels": 1024},
              "surface": effect(scores[0], scores[1], valid),
              "surface_interior_16px": effect(scores[0], scores[1], interior),
              "surface_outer_16px": effect(scores[0], scores[1], valid & ~interior),
              "zero_filled_background_diagnostic_only": correlations(*zero),
              "covariate_associations": compare_covariates(rows), "regions": rows}
    path = work/"surface.npz"
    np.savez_compressed(path, scores=scores, valid=valid, ct59=cube[31])
    for name, data in (("Z-signed.tif", scores[0]-scores[1]),
                       ("Z-sensitivity.tif", np.abs(scores[0]-scores[1]))):
        tifffile.imwrite(work/name, data, photometric="minisblack")
    result.update({"surface_sha256": digest(path), "analysis_seconds": perf_counter()-t0,
                   "analysis_peak_ram_bytes": working_set_peak()})
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--phase7", type=Path, default=Path("data/phase7"))
    parser.add_argument("--mesh", type=Path, default=Path("data/phase6/historical.tifxyz"))
    args = parser.parse_args()
    r = evidence(args.work, args.phase7, args.mesh, args.phase7/"review"/"comparison.json")
    args.output.write_text(json.dumps(r, indent=2, allow_nan=False)+"\n", encoding="utf-8")
