"""Validate geometric depth on geographically distributed raw CT witnesses."""

import argparse
import json
from pathlib import Path

import numpy as np
from phase6_cuda import digest
from phase7_orientation import WITNESSES, test_witness
from phase8_spatial import mesh_features, surface_cube
from scipy.ndimage import distance_transform_edt

from vesuvius_data_explorer.core.tifxyz import load_tifxyz
from vesuvius_data_explorer.core.volume import open_levels


def select_witnesses(mesh, valid):
    """Sample four quadrants plus two geometry extremes, before comparing signs."""
    knots, bend = mesh_features(mesh, valid.shape)
    distance = distance_transform_edt(np.pad(valid, 1))[1:-1, 1:-1]
    available = []
    for v in range(1, mesh.grid_shape[0]-1):
        for u in range(1, mesh.grid_shape[1]-1):
            r, c = 20*v, 20*u
            d = distance[r, c]
            if d >= 12 and knots[r, c] and np.isfinite(bend[r, c]):
                available.append((v, u, float(d), float(bend[r, c])))
    selected = list(WITNESSES)
    witnesses = []

    def take(category, possible, criterion):
        pool = [row for row in possible if all(max(abs(row[0]-a), abs(row[1]-b)) >= 4
                                               for a, b in selected)]
        if pool:
            v, u, d, angle = min(pool, key=criterion)
            selected.append((v, u))
            witnesses.append({"kind": category, "knot": (v, u), "distance_px": d, "bend_deg": angle})

    for half_v in range(2):
        for half_u in range(2):
            subset = [r for r in available if int(r[0]*2 >= mesh.grid_shape[0]) == half_v
                      and int(r[1]*2 >= mesh.grid_shape[1]) == half_u]
            take(f"quadrant_{half_v}_{half_u}", subset, lambda p: (-p[2], p[0], p[1]))
    take("near_border", available, lambda p: (p[2], p[0], p[1]))
    take("high_bend", available, lambda p: (-p[3], p[0], p[1]))
    return witnesses


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--phase7", type=Path, default=Path("data/phase7"))
    parser.add_argument("--mesh", type=Path, default=Path("data/phase6/historical.tifxyz"))
    args = parser.parse_args()
    phase4 = json.loads(Path("docs/validation/phase4-ink-windows.json").read_bytes())
    plan = json.loads((args.work/"input-plan.json").read_bytes())
    cube = surface_cube(plan, args.work, args.phase7)
    mesh = load_tifxyz(str(args.mesh.resolve()))
    witness_plan = select_witnesses(mesh, np.any(cube, axis=0))
    arrays, levels = open_levels(phase4["volume"], cache=True)
    level = levels[0]
    # This legacy raw header uses isotropic index units. The pitch in µm
    # is documented by the render and the Atlas volume identity.
    if level.shape != (28096, 18209, 18209) or len(set(level.scale)) != 1:
        raise ValueError("Unexpected raw scan index frame")
    results = []
    for witness in witness_plan:
        results.append({**witness, **test_witness(arrays[0], mesh, cube, (0, 0), witness["knot"])})
    args.output.write_text(json.dumps({
        "render": plan["uri"], "raw_volume": phase4["volume"], "anatomical_face": "unverified",
        "basis": "XYZ right-handed dP/dU cross dP/dV", "declared_flip_normals": True,
        "raw_level_shape_zyx": level.shape, "raw_level_header_scale_zyx": level.scale,
        "atlas_render_pitch_um": plan["pixel_size_um"],
        "mesh_sha256": {f.name: digest(f) for f in args.mesh.iterdir() if f.is_file()},
        "witnesses": results}, indent=2, allow_nan=False)+"\n", encoding="utf-8")
