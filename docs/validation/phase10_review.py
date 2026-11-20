"""Add two bounded raw CT witnesses to the verified, model-free phase 9 packet."""

import argparse
import io
import json
from hashlib import sha256
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import numpy as np
import tifffile
from phase7_orientation import uv_geometry
from phase9_optical import sha

from vesuvius_data_explorer.core.tifxyz import load_tifxyz
from vesuvius_data_explorer.core.volume import open_levels

PRIOR = Path("data/phase9/relecture-neutre-R02-R04-phase9.zip")
MESH = Path("data/phase6/historical.tifxyz")
SIDE = 80


def extract(work, review, orientation):
    mesh_hashes = {p.name: sha(p) for p in MESH.iterdir() if p.is_file()}
    if mesh_hashes != orientation["mesh_sha256"]:
        raise ValueError("The historical mesh does not match the orientation audit.")
    mesh = load_tifxyz(str(MESH.resolve()))
    raw, levels = open_levels(orientation["raw_volume"], cache=True)
    if tuple(orientation["raw_level_shape_zyx"]) != tuple(levels[0].shape):
        raise ValueError("Unexpected raw CT geometry.")
    evidence = []
    for row in review["regions"]:
        center = (np.array(row["start_vu"]) + np.array(row["stop_vu"])-1) / 2
        knot = np.rint(center / mesh.step_voxels).astype(int)
        v, u = np.rint(knot*mesh.step_voxels).astype(int)
        point, normal = uv_geometry(mesh, int(v), int(u), radius=2)
        origin = np.rint(point[2,2]).astype(int) - SIDE//2
        stop = origin+SIDE
        if np.any(origin < 0) or np.any(stop > levels[0].shape):
            raise ValueError("Witness outside the source scan.")
        payload = np.asarray(raw[0][tuple(slice(a,b) for a,b in zip(origin,stop))])
        if payload.shape != (SIDE,)*3 or not payload.any():
            raise ValueError("Empty or truncated CT witness.")
        path = work/f"{row['id']}-raw-L0.tif"
        tifffile.imwrite(path, payload, photometric="minisblack", metadata={"axes":"ZYX"})
        evidence.append({
            "id": row["id"], "render_witness_vu": [int(v),int(u)], "tifxyz_knot_index_vu": knot.tolist(),
            "raw_center_zyx": point[2,2].tolist(),
            "raw_bounds_zyx": [origin.tolist(),stop.tolist()], "raw_pitch_um": orientation["atlas_render_pitch_um"],
            "mesh_normal_xyz": normal[2,2,::-1].tolist(), "tiff_sha256": sha(path),
            "voxel_sha256": sha256(payload.tobytes()).hexdigest(),
            "dtype": str(payload.dtype), "min_code": int(payload.min()), "max_code": int(payload.max()),
            "raw_cache_file": path.name,
        })
    return {"source_volume":orientation["raw_volume"],"mesh_sha256":mesh_hashes,
            "source_packet_sha256":sha(PRIOR),"witnesses":evidence}


def pack(source_zip, work, result, tasks):
    target = work/"relecture-CT-R02-R04-phase10.zip"
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        for name in source_zip.namelist():
            archive.writestr(ZipInfo(name), source_zip.read(name), compress_type=ZIP_DEFLATED)
        for row in result["witnesses"]:
            raw = work/row["raw_cache_file"]
            if sha(raw) != row["tiff_sha256"]:
                raise ValueError("Unexpected modification of raw CT extract.")
            archive.writestr(ZipInfo(f"{row['id']}/CT-brut-L0-ZYX.tif"),raw.read_bytes(),
                             compress_type=ZIP_DEFLATED)
        archive.writestr(ZipInfo("CT-brut-provenance.json"),json.dumps(result,indent=2),
                         compress_type=ZIP_DEFLATED)
        archive.writestr(ZipInfo("Examen-CT.md"),tasks.read_bytes(),compress_type=ZIP_DEFLATED)
    return target


def figure(source_zip, work, result, target):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2,4,figsize=(12,5.5),layout="constrained")
    for row, entry in zip(axes,result["witnesses"]):
        name = entry["id"]
        raw = tifffile.imread(work/entry["raw_cache_file"])
        ct = tifffile.imread(io.BytesIO(source_zip.read(f"{name}/ct-ZVU.tif")))
        value = (255 if raw.dtype == np.uint8 else int(raw.max()))
        samples = (ct[:, :, 64],raw[40],raw[:,40,:],raw[:,:,40])
        bounds = entry["raw_bounds_zyx"]
        coords = json.loads(source_zip.read("ct-provenance.json"))
        region = next(r for r in coords["regions"] if r["id"] == name)
        v0,v1 = region["start_vu"][0],region["stop_vu"][0]
        z0,y0,x0 = np.asarray(bounds[0])-.5
        z1,y1,x1 = np.asarray(bounds[1])-.5
        extents = ((v0-.5,v1-.5,89.5,27.5),(x0,x1,y1,y0),(x0,x1,z1,z0),(y0,y1,z1,z0))
        labels = (("Rendu à U médian","V","Profondeur"),
                  ("CT brut à Z médian","X","Y"),("CT brut à Y médian","X","Z"),
                  ("CT brut à X médian","Y","Z"))
        for i,(axis,image,extent,(title,x,y)) in enumerate(zip(row,samples,extents,labels)):
            axis.imshow(image, extent=extent,cmap="gray",vmin=0,vmax=255 if i==0 else value)
            axis.set(title=f"{name} · {title}",xlabel=x,ylabel=y)
    fig.savefig(target,dpi=140)
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work",type=Path)
    p.add_argument("tasks",type=Path)
    p.add_argument("report",type=Path)
    p.add_argument("figure",type=Path)
    args = p.parse_args()
    archives = json.loads(Path("docs/validation/phase9-exports.json").read_bytes())
    orientation = json.loads(Path("docs/validation/phase8-orientation-windows.json").read_bytes())
    if sha(PRIOR) != archives[PRIOR.name]:
        raise ValueError("Unexpected phase 9 archive.")
    with ZipFile(PRIOR) as ct:
        info = json.loads(ct.read("ct-provenance.json"))
        output = extract(args.work,info,orientation)
        target = pack(ct,args.work,output,args.tasks)
        figure(ct,args.work,output,args.figure)
    output["archive_sha256"] = sha(target)
    output["figure_sha256"] = sha(args.figure)
    args.report.write_text(json.dumps(output,indent=2)+"\n",encoding="utf8")
