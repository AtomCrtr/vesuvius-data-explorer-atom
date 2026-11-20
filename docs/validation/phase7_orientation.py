"""Check signed rendered depth against independent raw CT on four TIFXYZ witnesses."""

import argparse
import json
from hashlib import sha256
from pathlib import Path

import numpy as np
from phase6_cuda import digest
from phase7_experiment import CHUNK, read_tile
from scipy.ndimage import map_coordinates

from vesuvius_data_explorer.core.ink_disagreement import correlations
from vesuvius_data_explorer.core.tifxyz import load_tifxyz
from vesuvius_data_explorer.core.volume import open_levels

WITNESSES = ((24, 30), (26, 32), (30, 37), (32, 40))
DEPTHS = (43, 51, 59, 67, 75)


def uv_geometry(mesh, v, u, radius=6):
    local = np.arange(-radius, radius+1)

    def points(dv, du):
        axes = np.meshgrid((v+local+dv)/mesh.step_voxels, (u+local+du)/mesh.step_voxels,
                           indexing="ij")
        return np.stack([map_coordinates(mesh.points[..., i], axes, order=1, prefilter=False)
                         for i in range(3)], axis=-1)

    position = points(0, 0)
    tang_u, tang_v = points(0, 1)-points(0, -1), points(1, 0)-points(-1, 0)
    normal_xyz = np.cross(tang_u[..., ::-1], tang_v[..., ::-1])
    normal_zyx = normal_xyz[..., ::-1] / np.linalg.norm(normal_xyz, axis=2, keepdims=True)
    if not np.isfinite(normal_zyx).all():
        raise ValueError("Invalid geometry at a fixed physical witness")
    return position, normal_zyx


def test_witness(raw_ct, mesh, crop, crop_origin, knot):
    v, u = (20*n for n in knot)
    pos, normal = uv_geometry(mesh, v, u)
    rows, cols = pos.shape[:2]
    radius = rows//2
    v0, u0 = v-crop_origin[0], u-crop_origin[1]
    depth_offset = np.array(DEPTHS)-58.5
    candidates = {sign: pos + sign*depth_offset[:, None, None, None]*normal
                  for sign in (-1, 1)}
    all_values = np.concatenate(list(candidates.values()), axis=0)
    lo = np.floor(all_values.min(axis=(0, 1, 2))).astype(int)-1
    hi = np.ceil(all_values.max(axis=(0, 1, 2))).astype(int)+2
    pixels = raw_ct[tuple(slice(a, b) for a, b in zip(lo, hi))]
    expected = crop[np.array(DEPTHS)-28, v0-radius:v0+radius+1, u0-radius:u0+radius+1]
    if expected.shape != (len(DEPTHS), rows, cols):
        raise ValueError("Witness falls outside its render tile")
    scores = {}
    for sign, positions in candidates.items():
        sampled = map_coordinates(pixels.astype(float), (positions-lo).reshape(-1, 3).T,
                                  order=1, mode="nearest").reshape(expected.shape)
        scores[str(sign)] = correlations(sampled, expected)
        scores[str(sign)]["pearson_by_depth"] = [correlations(a, b)["pearson"]
                                                for a, b in zip(sampled, expected)]
        scores[str(sign)]["mae_ct"] = float(np.abs(sampled-expected).mean())
    return {"uv_vu": [v, u], "raw_voxel_zyx": pos[radius, radius].tolist(),
            "geometric_normal_xyz": normal[radius, radius, ::-1].tolist(),
            "depths": DEPTHS, "raw_byte_sha256": sha256(pixels.tobytes()).hexdigest(),
            "raw_bounds_zyx": [lo.tolist(), hi.tolist()], "signs_for_depth_increase": scores}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("phase6", type=Path)
    parser.add_argument("phase4_report", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source = json.loads(args.phase4_report.read_bytes())
    ct, _ = open_levels(source["volume"], cache=True)
    mesh_folder = args.phase6/"historical.tifxyz"
    mesh = load_tifxyz(str(mesh_folder.resolve()))
    meta = json.loads((args.work/"input-plan.json").read_bytes())
    chunks = {tuple(record["key"]): np.memmap(
        args.work/"chunks"/f"{record['key'][0]}-{record['key'][1]}.raw", "u1", "r", shape=CHUNK)
        for record in meta["chunks"]}
    rows = []
    for v, u in WITNESSES:
        rc = (v*20-120, u*20-120)
        rows.append(test_witness(ct[0], mesh, read_tile(chunks, *rc), rc, (v, u)))
    report = {"raw_volume": source["volume"], "render": meta["uri"],
              "mesh_sha256": {p.name: digest(p) for p in mesh_folder.iterdir() if p.is_file()},
              "basis": "XYZ right-handed dP/dU cross dP/dV", "center_layer_coordinate": 58.5,
              "declared_flip_normals": True, "anatomical_face": "unknown", "witnesses": rows}
    args.output.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
