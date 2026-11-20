"""Build the native-frame napari bundle and the independent CT review packet."""

import argparse
import io
import json
import shutil
from hashlib import sha256
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import numpy as np
import tifffile
from phase9_optical import sha

from vesuvius_data_explorer.core.multimodal import export_multimodal

SOURCE = Path("data/phase8")
REPORTS = Path("docs/validation")


def emit(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+"\n", encoding="utf8")


def napari_bundle(work, optical, location):
    folder = work/"validation"
    folder.mkdir(exist_ok=True)
    files = {}
    phase8 = json.loads((SOURCE/"surface/comparison.json").read_bytes())
    for role, relative in (("ct",phase8["ct"]), ("surface",phase8["surface"]),
                           ("a_plus",phase8["predictions"][0]["path"]), ("a_minus",phase8["predictions"][1]["path"])):
        dest = folder/f"{role}.tif"
        shutil.copyfile(SOURCE/"surface"/relative, dest)
        files[role] = {"path": dest.name, "sha256": sha(dest)}
    with np.load(work/"optical-preview.npz", allow_pickle=False) as preview:
        for role, array in (("height", preview["height"]), ("brightfield", preview["bright"]),
                            ("ink_mask", preview["label"].astype("u1"))):
            dest = folder/f"{role}.tif"
            tifffile.imwrite(dest, array, photometric="rgb" if role == "brightfield" else "minisblack")
            files[role] = {"path": dest.name, "sha256": sha(dest)}
    ct_pitch = location["ct_pitch_um"]
    pitch_yx = [optical[axis]["pitch_um"]*4 for axis in ("axis_y","axis_x")]
    case = optical["pilot"]["case_id"]
    manifest = folder/"validation.json"
    emit(manifest, {"version": 1, "files": files, "ct": {"pitch_um":[ct_pitch]*2, "origin_um":[0.,0.]},
                    "optical":{"pitch_um":pitch_yx,"origin_um":[optical[k]["origin_um"] for k in ("axis_y","axis_x")],
                               "preview_every_native_pixels":4},
                    "identity":{"location":"unverified","scale":"unverified","face":"indeterminate"},
                    "landmarks": [],
                    "summary_fr":f"{case} · pas exporté 0,688 µm · échelle instrumentale à confirmer. "
                                 "CT et relief sont présentés dans leurs repères natifs. "
                                 "Aucun repère commun ni mesure d’encre dans cette session.",
                    "provenance":{"optical_case":case,"optical_revision":optical["repository_revision"],
                                  "optical_source":"https://huggingface.co/datasets/scrollprize/profilometer",
                                  "optical_licenses":optical["license"],"optical_files":optical["files"],
                                  "ct_segment":location["wrap_atlas_segment"],
                                  "ct_revision":phase8["surface_revision"],
                                  "ct_volume":location["ct_reference_volume"],
                                  "ct_archive": "phase8/surface",
                                  "ct_surface_manifest_sha256":sha(SOURCE/"surface/comparison.json"),
                                  "phase8_model_pair":phase8["predictions"],
                                  "optical_audit_sha256":sha(REPORTS/"phase9-optical.json"),
                                  "localization_audit_sha256":sha(REPORTS/"phase9-localization.json")}})
    export_multimodal(manifest, work/"validation-CT-optique-phase9.zip")


def neutral_packet(work, location):
    origin = SOURCE/"CT-relecture-neutre-phase8.zip"
    prior = json.loads((REPORTS/"phase8-review-windows.json").read_bytes())
    if sha(origin) != prior["neutral_ct_sha256"]:
        raise ValueError("Phase 8 neutral archive changed")
    result = work/"relecture-neutre-R02-R04-phase9.zip"
    notes = """# Relecture CT de PHerc0500P2

Examiner R02 puis R04, en commençant par CT59 et en naviguant dans les 62 coupes ZVU. Les intensités uint8 proviennent du rendu historique CT au pas de 2,215 µm. Les plages sont à base zéro, borne supérieure exclue. Les masques représentent le support CT.

- R02, V[644,772) U[636,764). Une bande claire légèrement inclinée traverse la coupe 59. Aux coupes 71 et 83, les faisceaux clairs se déplacent vers le travers de la fenêtre. Vérifier si les coupes intermédiaires relient ces structures au sein d’une lamelle ou révèlent un croisement de couches.
- R04, V[644,772) U[764,892). Des arcs clairs bordent des zones sombres et un point lumineux apparaît vers le haut gauche en coupe 59. Aux coupes 71 et 83, la bordure claire se place surtout en haut et à gauche. Vérifier si elle délimite un vide, une fissure, une frontière de couche ou une structure matérielle continue.

Pour chaque région, consigner les coupes et positions V,U, la structure observée, une interprétation structurale éventuelle et le degré d’incertitude. Les deux régions ont un support CT intégral et appartiennent à la surface 20250919184428. Le sens de profondeur a été contrôlé sur le segment. La face de ces régions et leur correspondance avec un champ optique restent indéterminées. La distance au maillage frontal publiée dans le manifeste est indicative à la maille d’échantillonnage, dont le pas est de 44,3 µm.

Pour confronter l’observation à une autre modalité, demander les photos de situation et la transformation documentée du champ optique vers la surface frontale. Attribuer toute lecture papyrologique à ses propres sources.

Vesuvius Challenge Open Data, CC BY-NC 4.0. Attribution et conditions https://github.com/ScrollPrize/open-data#support-and-citation
"""
    with ZipFile(origin) as src, ZipFile(result, "w") as dst:
        meta = json.loads(src.read("ct-provenance.json"))
        meta["regions"] = [row for row in meta["regions"] if row["id"] in ("R02","R04")]
        meta["surface_id"] = location["wrap_atlas_segment"]
        meta["volume_id"] = location["ct_reference_volume"]
        meta["phase8_ct_archive_sha256"] = sha(origin)
        meta["independent_ink_annotation"] = None
        for row in meta["regions"]:
            row["geometry"] = location["front_relative_geometry_review"][row["id"]]
            for filename, expected in row["sha256"].items():
                payload = src.read(filename)
                if sha256(payload).hexdigest() != expected:
                    raise ValueError(filename)
                dst.writestr(ZipInfo(filename), payload, compress_type=ZIP_DEFLATED)
        dst.writestr(ZipInfo("LIRE.md"), notes.encode("utf8"), compress_type=ZIP_DEFLATED)
        dst.writestr(ZipInfo("ct-provenance.json"), json.dumps(meta, ensure_ascii=False, indent=2).encode("utf8"),
                     compress_type=ZIP_DEFLATED)
    return result


def figure(work, target):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    with np.load(work/"optical-preview.npz", allow_pickle=False) as data:
        relief, bright = data["height"], data["bright"]
    with np.load(SOURCE/"surface.npz", allow_pickle=False) as data:
        ct, mask = data["ct59"], data["valid"]
    fig, axes = plt.subplots(1, 3, figsize=(12,4), layout="constrained")
    axes[0].imshow(np.where(mask, ct, np.nan), cmap="gray")
    axes[0].set(title="CT59 · wrap01_0919", xlabel="U (px CT)", ylabel="V (px CT)")
    axes[1].imshow(bright)
    axes[1].set(title="ν2 · photographie optique", xlabel="X (px d’aperçu)", ylabel="Y (px d’aperçu)")
    lo, hi = np.nanpercentile(relief,[1,99])
    c = axes[2].imshow(relief,cmap="terrain",vmin=lo,vmax=hi)
    axes[2].set(title="ν2 · relief brut", xlabel="X (px d’aperçu)", ylabel="Y (px d’aperçu)")
    fig.colorbar(c, ax=axes[2], label="Hauteur exportée (µm)", shrink=.73)
    fig.savefig(target, dpi=140)
    plt.close(fig)


def depth_figure(packet, target):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2,5,figsize=(11,4.4),layout="constrained")
    with ZipFile(packet) as source:
        for row, region in zip(axes, ("R02", "R04")):
            cube = tifffile.imread(io.BytesIO(source.read(f"{region}/ct-ZVU.tif")))
            for axis, depth in zip(row, (35,47,59,71,83)):
                axis.imshow(cube[depth-28], cmap="gray", vmin=0, vmax=255)
                axis.set(title=f"{region} · Z{depth}", xticks=[], yticks=[])
    fig.savefig(target, dpi=135)
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=Path)
    args = p.parse_args()
    opt = json.loads((REPORTS/"phase9-optical.json").read_bytes())
    loc = json.loads((REPORTS/"phase9-localization.json").read_bytes())
    napari_bundle(args.work, opt, loc)
    packet = neutral_packet(args.work, loc)
    figure(args.work, REPORTS/"phase9-native-frames.png")
    depth_figure(packet, REPORTS/"phase9-R02-R04-depth.png")
    emit(REPORTS/"phase9-exports.json", {path.name:sha(path) for path in (
        packet, args.work/"validation-CT-optique-phase9.zip", args.work/"validation/validation.json")})
