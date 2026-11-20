"""Check the optical pilot footprint and the front mesh against the phase-8 CT frame."""

import argparse
import gzip
import json
from pathlib import Path

import numpy as np
from phase9_optical import sha
from PIL import Image
from scipy.spatial import ConvexHull, cKDTree, distance

from vesuvius_data_explorer.core.tifxyz import load_tifxyz

PHASE8_MESH = Path("data/phase6/historical.tifxyz")
ATLAS = Path("data/rust2/catalog.json")
PITCH = 2.215


def five(data):
    return np.quantile(data, [0, .1, .5, .9, 1]).tolist()


def mesh_proximity(front, query):
    points = front.points[front.valid]
    source = cKDTree(points)
    dx = np.gradient(front.points, axis=1)
    dy = np.gradient(front.points, axis=0)
    normals = np.cross(dx[..., ::-1], dy[..., ::-1])[..., ::-1][front.valid]
    d, i = source.query(query)
    normals = normals[i]
    magnitude = np.linalg.norm(normals, axis=1)
    usable = np.isfinite(magnitude) & (magnitude > 0)
    normal = normals[usable] / magnitude[usable, None]
    signed = np.sum((query[usable] - points[i[usable]]) * normal, axis=1)
    return {"sample_knots": len(query), "nearest_front_knot_um_min_p10_p50_p90_max": five(d * PITCH),
            "nearest_tangent_pairs": int(usable.sum()),
            "front_signed_tangent_offset_um_min_p10_p50_p90_max": five(signed*PITCH) if len(signed) else None}


def localize(work, optical):
    source = ATLAS.read_bytes()
    atlas = json.loads(gzip.decompress(source) if source.startswith(b"\x1f\x8b") else source)
    specimen = atlas["samples"]["PHerc0500P2"]
    front_id = "20250628074500"
    wrap = load_tifxyz(str(PHASE8_MESH.resolve()))
    front_path = work/"front.tifxyz"
    front = load_tifxyz(str(front_path.resolve()))
    revised_path = work/"front-t2.tifxyz"
    revised = load_tifxyz(str(revised_path.resolve()))
    optical_meta = json.loads(optical.read_bytes())
    opt = optical_meta["axis_y"]["extent_center_to_center_um"], optical_meta["axis_x"]["extent_center_to_center_um"]
    wrap_points = wrap.points[wrap.valid]
    diameter = max(distance.pdist(wrap_points[ConvexHull(wrap_points).vertices])) * PITCH
    with np.load(Path("data/phase8/surface.npz")) as data:
        support = data["valid"]
    with Image.open(work/"PHerc0500P2_photo.jpg") as photo:
        w, h = photo.size
    previews = json.loads(Path("docs/validation/phase8-review-windows.json").read_bytes())
    vv, uu = np.indices(wrap.valid.shape) * wrap.step_voxels
    roi_probes = {}
    for row in previews["regions"]:
        if row["neutral_id"] not in ("R02", "R04"):
            continue
        v1, u1 = row["start_vu"]
        v2, u2 = row["stop_vu"]
        selected = wrap.valid & (vv >= v1) & (vv < v2) & (uu >= u1) & (uu < u2)
        roi_probes[row["neutral_id"]] = {
            "bounds_vu": [row["start_vu"], row["stop_vu"]],
            "valid_render_fraction": float(support[v1:v2,u1:u2].mean()),
            **mesh_proximity(front, wrap.points[selected]),
            "front_revision_2": mesh_proximity(revised, wrap.points[selected]),
        }
    relevant = ("photo", "tifxyz-transformed", "layers-zarr")
    seg = specimen["segments"][front_id]
    paths = [origin["path"] for item in specimen["sample"]["data"] + seg["data"]
             if item["type"] in relevant for origin in item["origins"]]
    roles = sorted({entry["type"] for segment in specimen["segments"].values() for entry in segment["data"]})
    return {"status": "field_not_localized", "front_face_of_optical_field": "indeterminate",
            "accepted_landmarks": [], "fit": None, "ct_reference_volume": "20250526151718",
            "atlas_sha256": sha(ATLAS), "atlas_segment_count": len(specimen["segments"]),
            "atlas_segment_roles": roles, "atlas_geometry_and_photo_paths": paths,
            "front_atlas_segment": seg["long_id"], "wrap_atlas_segment": "20250919184428-0500P2-wrap01_0919",
            "front_mesh": {f.name: sha(f) for f in front_path.iterdir() if f.is_file()},
            "front_mesh_revision_2": {f.name: sha(f) for f in revised_path.iterdir() if f.is_file()},
            "wrap_mesh": {f.name: sha(f) for f in PHASE8_MESH.iterdir() if f.is_file()},
            "front_zarr_attributes_sha256": sha(work/"front-zattrs.json"),
            "optical_audit_sha256": sha(optical), "ct_pitch_um": PITCH,
            "optical_sample_center_span_yx_um": list(opt),
            "optical_nominal_xy_diagonal_um": float(np.linalg.norm(opt)),
            "optical_diagonal_um_if_paper_pitch": float(np.linalg.norm(
                (np.array(optical_meta["shape_yx"])-1)*.34)),
            "wrap_raster_nominal_center_span_vu_um": ((np.array(support.shape)-1)*PITCH).tolist(),
            "wrap_mesh_3d_diameter_um": float(diameter),
            "front_mesh_step_um": front.step_voxels*PITCH,
            "front_relative_geometry_all_wrap": mesh_proximity(front, wrap_points),
            "front_relative_geometry_all_wrap_revision_2": mesh_proximity(revised, wrap_points),
            "front_relative_geometry_review": roi_probes,
            "photo": {"shape_yx": [h,w], "sha256": sha(work/"PHerc0500P2_photo.jpg"),
                      "instrument_coordinates": None, "roi_footprint": None},
            "front_registration_reference": {"source": "https://arxiv.org/abs/2606.29085v1",
                "reference_image": "Naples M1050 IR #017", "extent_mm": [35.8,58.1],
                "figure": "Extended Data Fig. 5", "ct_to_ir_control_points_found": False,
                "profilometer_to_ir_crosswalk_found": False}}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=Path)
    p.add_argument("optical_audit", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    args.output.write_text(json.dumps(localize(args.work,args.optical_audit), indent=2,
                                      allow_nan=False)+"\n", encoding="utf8")
