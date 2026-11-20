"""Phase 11, step B1: blind check of the chain native CT -> PPM surface -> flattened layers (Frag4).

No ink label or prediction is read. Patches are chosen from the support mask only, by the rule
frozen in ``select_patches`` (eroded mask, fixed grid fractions), before any CT is sampled.

For each patch the per-pixel map (PPM: x, y, z, nx, ny, nz in CT voxels) is read by HTTP ranges,
the native 54 keV CT is sampled at ``p + s * (k - 32) * n + o`` and compared with the published
surface-volume layer ``k``. Hypotheses: normal sign ``s``, voxel-centre offset ``o``, interpolation.

    python -I docs/validation/phase11_geometry.py data/phase11 docs/validation/phase11-geometry-ppm.json
"""

import hashlib
import json
import sys
from itertools import product
from pathlib import Path

import fsspec
import numpy as np
import tifffile
from PIL import Image
from scipy import ndimage

from vesuvius_data_explorer.core.chunkcache import DecodedChunks, sample_trilinear
from vesuvius_data_explorer.core.volume import open_volume_store

PKG = "https://dl.ash2txt.org/fragments/Frag4/PHercParis1Fr39.volpkg/"
SURF = PKG + "working/54keV_exposed_surface/"
PPM = SURF + "extras/PHercParis1Fr39_54keV.ppm"  # Mesh map (UV -> cropped CT voxels).
# The *_surface_volume.ppm is an identity map of the surface volume (x=col, y=row, z=32, n=+z).
IDENTITY_PPM = SURF + "extras/PHercParis1Fr39_54keV_surface_volume.ppm"
LAYER = SURF + "PHercParis1Fr39_54keV_surface_volume/{:02d}.tif"
CT = PKG + "volumes_zarr/54keV_3.24um_.zarr"
W, H, CENTER = 6064, 9791, 32
PATCH = 32
LAYERS = tuple(range(0, 65, 8))
PROFILE_LAYERS = tuple(range(0, 65, 2))


def select_patches(mask):
    """Frozen rule: mask eroded by 160 px, bbox grid fractions rows .2/.4/.6/.8 x cols .35/.65."""
    inner = ndimage.binary_erosion(mask, iterations=20, structure=np.ones((3, 3)))  # on 1/8 grid
    rows, cols = np.nonzero(inner)
    points = []
    for fr, fc in product((.2, .4, .6, .8), (.35, .65)):
        target = np.array([rows.min() + fr * np.ptp(rows), cols.min() + fc * np.ptp(cols)])
        best = np.argmin((rows - target[0])**2 + (cols - target[1])**2)
        points.append((int(rows[best]) * 8 - PATCH // 2, int(cols[best]) * 8 - PATCH // 2))
    return points


class Ranges:
    def __init__(self):
        self.fs = fsspec.filesystem("https")
        head = self.fs.cat_file(PPM, start=0, end=1024)
        self.ppm_header = head[:head.index(b"<>\n") + 3].decode()
        assert "width: 6064" in self.ppm_header and "height: 9791" in self.ppm_header
        assert "dim: 6" in self.ppm_header and "type: double" in self.ppm_header
        self.ppm_offset = head.index(b"<>\n") + 3
        self.tiffs = {}

    def rows(self, url, offset, itemsize, r0, c0, h, w):
        starts = [offset + ((r0 + i) * W + c0) * itemsize for i in range(h)]
        return b"".join(self.fs.cat_ranges([url] * h, starts, [s + w * itemsize for s in starts]))

    def ppm(self, r0, c0, h=PATCH, w=PATCH):
        raw = self.rows(PPM, self.ppm_offset, 48, r0, c0, h, w)
        return np.frombuffer(raw, "<f8").reshape(h, w, 6)

    def layer(self, k, r0, c0, h=PATCH, w=PATCH):
        url = LAYER.format(k)
        if url not in self.tiffs:
            with self.fs.open(url, "rb", block_size=1 << 16) as handle:
                tif = tifffile.TiffFile(handle)
                page = tif.pages[0]
                assert page.shape == (H, W) and page.compression == 1 and len(page.dataoffsets) == 1
                self.tiffs[url] = (int(page.dataoffsets[0]), np.dtype(page.dtype).newbyteorder(tif.byteorder))
        offset, dtype = self.tiffs[url]
        return np.frombuffer(self.rows(url, offset, dtype.itemsize, r0, c0, h, w), dtype).reshape(h, w)


def compare(ct, published):
    a, b = ct.ravel().astype(float), published.ravel().astype(float)
    return {"pearson": float(np.corrcoef(a, b)[0, 1]), "mae": float(np.abs(a - b).mean()),
            "within_1_level": float(np.mean(np.abs(a - b) <= 1))}


def main(work, out):
    work = Path(work)
    mask = np.asarray(Image.open(work / "raw/mask.png")) > 0
    assert mask.shape == (H, W)
    patches = select_patches(mask[::8, ::8])
    ranges = Ranges()
    root = open_volume_store(CT)
    level0 = DecodedChunks(root["0"], max_bytes=2 * 2**30)
    shape_zyx = np.array(level0.shape)
    hypotheses = [(s, o, interp) for s in (1, -1) for o in (0.0, -0.5, 0.5) for interp in ("linear", "nearest")]
    scores = {h: [] for h in hypotheses}
    report = []
    for r0, c0 in patches:
        ppm = ranges.ppm(r0, c0)
        p, n = ppm[..., :3], ppm[..., 3:]
        valid = np.any(ppm != 0, axis=2) & mask[r0:r0 + PATCH, c0:c0 + PATCH]
        layers = {k: ranges.layer(k, r0, c0) for k in PROFILE_LAYERS}
        dx = np.linalg.norm(np.diff(p, axis=1), axis=2)[valid[:, 1:] & valid[:, :-1]]
        dy = np.linalg.norm(np.diff(p, axis=0), axis=2)[valid[1:] & valid[:-1]]
        entry = {"rc": [r0, c0], "valid_px": int(valid.sum()),
                 "xyz_min": p[valid].min(0).tolist(), "xyz_max": p[valid].max(0).tolist(),
                 "normal_norm_median": float(np.median(np.linalg.norm(n[valid], axis=1))),
                 "pitch_cols_vox_median": float(np.median(dx)), "pitch_rows_vox_median": float(np.median(dy)),
                 "normal_mean_xyz": (n[valid].mean(0) / np.linalg.norm(n[valid].mean(0))).tolist(),
                 "layer_mean_profile": {k: float(v[valid].mean()) for k, v in layers.items()},
                 "hypotheses": {}}
        inside = np.all((p[valid][:, ::-1] >= 0) & (p[valid][:, ::-1] < shape_zyx), axis=1)
        entry["ppm_inside_cropped_volume"] = float(inside.mean())
        for s, o, interp in hypotheses:
            per_layer = {}
            for k in LAYERS:
                q = p[valid] + s * (k - CENTER) * n[valid] + o
                zyx = q[:, ::-1]
                if interp == "nearest":
                    zyx = np.floor(zyx + .5)
                per_layer[k] = compare(sample_trilinear(level0, zyx), layers[k][valid])
            entry["hypotheses"][f"s{s:+d}_o{o:+.1f}_{interp}"] = per_layer
            scores[(s, o, interp)].append(np.mean([v["mae"] for v in per_layer.values()]))
        report.append(entry)
        print("patch", r0, c0, "done", file=sys.stderr, flush=True)
    ranking = sorted(((float(np.mean(v)), f"s{h[0]:+d}_o{h[1]:+.1f}_{h[2]}") for h, v in scores.items()))
    best = ranking[0][1]
    # Residual sub-voxel shift of the best hypothesis, layer 32 then layer 0 and 64: global xyz grid.
    s = 1 if best.startswith("s+1") else -1
    o = float(best.split("_o")[1].split("_")[0])
    interp = best.rsplit("_", 1)[1]
    shifts = np.arange(-1.0, 1.01, 0.25)
    shift_scores = {}
    cached = []
    for r0, c0 in patches:
        ppm = ranges.ppm(r0, c0)
        valid = np.any(ppm != 0, axis=2) & mask[r0:r0 + PATCH, c0:c0 + PATCH]
        cached.append((ppm[..., :3][valid], ppm[..., 3:][valid],
                       {k: ranges.layer(k, r0, c0)[valid] for k in (0, 32, 64)}))
    for k in (0, 32, 64):
        grid = {}
        for d in product(shifts, repeat=3):
            maes = []
            for p, n, published in cached:
                q = p + s * (k - CENTER) * n + o + np.array(d)
                zyx = q[:, ::-1] if interp == "linear" else np.floor(q[:, ::-1] + .5)
                maes.append(compare(sample_trilinear(level0, zyx), published[k])["mae"])
            grid[tuple(float(x) for x in d)] = float(np.mean(maes))
        argmin = min(grid, key=grid.get)
        shift_scores[k] = {"best_shift_xyz_vox": list(argmin), "mae_at_best": grid[argmin],
                           "mae_at_zero": grid[(0.0, 0.0, 0.0)]}
    result = {"sources": {"ppm": PPM, "ppm_header": ranges.ppm_header, "ct": CT, "layers": LAYER,
                          "mask_sha256": hashlib.sha256((work / "raw/mask.png").read_bytes()).hexdigest()},
              "blind": "ink labels and predictions not read; patches from eroded mask only",
              "patch_rule": select_patches.__doc__, "patch_size": PATCH, "patches": report,
              "hypothesis_ranking_mean_mae": ranking, "best": best, "residual_shift": shift_scores,
              "ct_shape_zyx": shape_zyx.tolist(), "chunks_decoded": level0.decoded}
    Path(out).write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps({"best": best, "ranking": ranking[:4], "shift": shift_scores}, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:3])
