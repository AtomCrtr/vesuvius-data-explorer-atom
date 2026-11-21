"""Phase 13: does A's papyrus -> air (Z_out) ranking of ink generalize? New Frag4 ROIs, Frag1, Frag3.

Protocol: docs/validation/phase13-protocol.json, committed with this script before any phase 13 score
and before the Frag1 / Frag3 ink labels were downloaded. Steps (two interpreters):

    .venv/Scripts/python.exe docs/validation/phase13_eval.py --prepare Frag4      # then Frag1, Frag3
    data/phase6-cuda/Scripts/python.exe docs/validation/phase11_z_frag4.py data/phase13/frag4 \
        --window docs/validation/phase13-prepare-frag4.json                       # A, both orders
    .venv/Scripts/python.exe docs/validation/phase13_eval.py --report docs/validation/phase13-eval.json

``--prepare`` is label-free: surface-layer check, direction rule, W2 window, ROI extraction. It writes
the volumes in physical Z_out order (papyrus -> air) with the file names phase11_z_frag4.run expects,
so the inference code is the audited phase 11 one, unchanged.
"""

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

import fsspec
import numpy as np
import tifffile
from PIL import Image
from scipy import ndimage
from scipy.sparse import csr_matrix

sys.path.insert(0, str(Path(__file__).parent))
from phase11_geometry import PATCH, select_patches  # noqa: E402
from phase11_window import DEPTH_LAYERS, moments_u8  # noqa: E402
from phase11_z_frag4 import NATIVE_UM, OUT_PX, OUT_UM, layer_coords  # noqa: E402
from phase12_ink_eval import BINS, BLOCK, DRAWS, SEED, binned, ranking, sample_labels  # noqa: E402

HERE = Path(__file__).parent
PROTOCOL = HERE / "phase13-protocol.json"
PROTOCOL_SHA = "d5de92ab19da707721784a3c3b8ee51ef6c5332bf1434e1711c17aad9b531017"
ROOT = "https://dl.ash2txt.org/fragments/"
WORK = Path("data/phase13")
FILES = {"Frag4": ("PHercParis1Fr39_54keV_surface_volume/{:02d}.tif", "extras/PHercParis1Fr39_54keV_surface_volume.ppm",
                   "PHercParis1Fr39_54keV_inklabels.png"),
         "Frag1": ("surface_volume/{:02d}.tif", "surface_volume.ppm", "inklabels.png"),
         "Frag3": ("surface_volume/{:02d}.tif", "surface_volume.ppm", "inklabels.png")}
FRAG4_LABELS_SHA = "a6f39eb59422a4507313ec912185eb92b44e3dd9e2e8e6a97e7b571462ce18fc"
AIR_ENDS = {"low": range(0, 13), "high": range(52, 65)}
SCORES = ("Z_out", "Z_in", "B1", "B2")
MIN_CLASS = 1000


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_frozen_protocol(path):
    # Git stores LF; Windows checkouts can use CRLF for this same frozen document.
    content = path.read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(content).hexdigest() != PROTOCOL_SHA:
        raise ValueError(f"{path} is not a frozen protocol (modified content)")
    return json.loads(content)


class Surface:
    """Byte-range reader of one fragment's uncompressed surface-volume layers and identity PPM."""

    def __init__(self, fragment, shape):
        protocol = read_frozen_protocol(PROTOCOL)
        self.base = ROOT + protocol["fragments"][fragment]["surface"]
        self.layer_url, self.ppm_url, self.label_url = (self.base + f for f in FILES[fragment])
        self.shape, self.fs, self.offsets = shape, fsspec.filesystem("https"), {}

    def _rows(self, url, offset, itemsize, r0, c0, h, w):
        width = self.shape[1]
        starts = [offset + ((r0 + i) * width + c0) * itemsize for i in range(h)]
        return b"".join(self.fs.cat_ranges([url] * h, starts, [s + w * itemsize for s in starts]))

    def layer(self, k, r0, c0, h, w):
        url = self.layer_url.format(k)
        if url not in self.offsets:
            with self.fs.open(url, "rb", block_size=1 << 16) as handle:
                tif = tifffile.TiffFile(handle)
                page = tif.pages[0]
                assert page.shape == self.shape and page.compression == 1 and len(page.dataoffsets) == 1
                self.offsets[url] = (int(page.dataoffsets[0]), np.dtype(page.dtype).newbyteorder(tif.byteorder))
        offset, dtype = self.offsets[url]
        return np.frombuffer(self._rows(url, offset, dtype.itemsize, r0, c0, h, w), dtype).reshape(h, w)

    def ppm_pixel(self, r, c):
        head = self.fs.cat_file(self.ppm_url, start=0, end=1024)
        assert f"width: {self.shape[1]}".encode() in head and f"height: {self.shape[0]}".encode() in head
        offset = head.index(b"<>\n") + 3
        return np.frombuffer(self._rows(self.ppm_url, offset, 48, r, c, 1, 1), "<f8").tolist()


def direction(surface, mask, patches):
    """Label-free: the depth end whose layers are least textured is air."""
    side, profile = 64, {}
    for k in [*AIR_ENDS["low"], *AIR_ENDS["high"]]:
        stds = []
        for r, c in patches:
            r0, c0 = r + PATCH // 2 - side // 2, c + PATCH // 2 - side // 2
            inside = mask[r0:r0 + side, c0:c0 + side]
            stds.append(float(surface.layer(k, r0, c0, side, side)[inside].std()))
        profile[k] = float(np.median(stds))
    ends = {e: float(np.mean([profile[k] for k in ks])) for e, ks in AIR_ENDS.items()}
    return {"layer_std_median": profile, "end_mean_std": ends, "air": min(ends, key=ends.get)}


def window(surface, mask, patches):
    """W2 statistics, phase11_window rule."""
    side, values = 128, []
    for r, c in patches:
        r0, c0 = r + PATCH // 2 - side // 2, c + PATCH // 2 - side // 2
        inside = mask[r0:r0 + side, c0:c0 + side]
        values += [surface.layer(k, r0, c0, side, side)[inside] for k in DEPTH_LAYERS]
    values = np.concatenate(values).astype(np.float64)
    return {"w2_depth_layers": list(DEPTH_LAYERS), "w2_mean_u16": float(values.mean()),
            "w2_std_u16": float(values.std()), "w2_target_mean_std_over_200": [0.379, 0.148]}


def extract(surface, mask, patch, coords, w2):
    """ROI volume sampled at the fractional layers ``coords`` (phase11_z_frag4.prepare, generic reader)."""
    span = OUT_PX * OUT_UM / NATIVE_UM
    r, c = patch
    r0, c0 = int(round(r + PATCH / 2 - span / 2)) - 2, int(round(c + PATCH / 2 - span / 2)) - 2
    n = int(np.ceil(span)) + 5
    lo, hi = int(np.floor(coords.min())), int(np.ceil(coords.max()))
    block = np.stack([surface.layer(k, r0, c0, n, n) for k in range(lo, hi + 1)]).astype(np.float32)
    grid = 2 + np.arange(OUT_PX) * OUT_UM / NATIVE_UM
    yy, xx = np.meshgrid(grid, grid, indexing="ij")
    below = np.floor(coords - lo).astype(int)
    frac = (coords - lo) - below
    planes = [(1 - f) * block[b] + f * block[min(b + 1, len(block) - 1)] for b, f in zip(below, frac)]
    volume = np.stack([ndimage.map_coordinates(p, [yy, xx], order=1, mode="nearest") for p in planes])
    roi_mask = ndimage.map_coordinates(mask[r0:r0 + n, c0:c0 + n].astype(np.float32), [yy, xx], order=0) > 0.5
    return moments_u8(volume, w2["w2_mean_u16"], w2["w2_std_u16"]), roi_mask, [r0, c0], n


def prepare(fragment):
    protocol = read_frozen_protocol(PROTOCOL)
    work = WORK / fragment.lower()
    mask = np.asarray(Image.open(work / "mask.png")) > 0  # Palette masks, index 0 = black.
    surface = Surface(fragment, mask.shape)
    patches = select_patches(mask[::8, ::8])
    r, c = patches[0]
    ppm = surface.ppm_pixel(r + PATCH // 2, c + PATCH // 2)
    if abs(ppm[2] - 32) > 1e-6:
        raise ValueError(f"{fragment}: surface layer is z = {ppm[2]}, not 32")
    found = direction(surface, mask, patches)
    if fragment == "Frag4" and found["air"] != "high":
        raise ValueError("Positive control failed: the direction rule is void")
    coords = layer_coords() if found["air"] == "high" else 64 - layer_coords()  # Z_out: papyrus -> air
    w2 = window(surface, mask, patches)
    if fragment == "Frag4":  # Same rule and patches as phase 11: must reproduce its window.
        ref = json.loads((HERE / "phase11-window.json").read_bytes())
        assert np.allclose([w2["w2_mean_u16"], w2["w2_std_u16"]], [ref["w2_mean_u16"], ref["w2_std_u16"]])
    summary = {"blind": "ink labels not read", "fragment": fragment, "mask_sha256": sha(work / "mask.png"),
               "mask_shape": list(mask.shape), "patches_rc": patches, "ppm_at_patch0": ppm, "direction": found,
               "z_out_layer_coords": coords.tolist(), **w2, "rois": []}
    for index in protocol["fragments"][fragment]["patches"]:
        u8, roi_mask, origin, n = extract(surface, mask, patches[index], coords, w2)
        name = f"roi{index}"
        np.save(work / f"{name}-zout-w2.npy", u8)
        np.save(work / f"{name}-mask.npy", roi_mask)
        summary["rois"].append({"name": name, "patch_index": index, "native_origin_rc": origin, "native_size": n,
                                "npy_sha256": sha(work / f"{name}-zout-w2.npy"),
                                "mask_fraction": float(roi_mask.mean())})
        print(fragment, name, "prepared", file=sys.stderr, flush=True)
    text = json.dumps(summary, indent=1)
    (work / "z-frag4-w2-prepare.json").write_text(text, encoding="utf-8")
    (HERE / f"phase13-prepare-{fragment.lower()}.json").write_text(text, encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("direction", "w2_mean_u16", "w2_std_u16")}, indent=1))


def baselines(volume):
    """B1 and B2 of the protocol, from the W2 input volume (Z_out order)."""
    b1 = 1 - volume[30:32].astype(np.float64).mean(0) / 255
    m = volume[26:36].astype(np.float64).mean(0) / 255
    b2 = np.sqrt(np.maximum(ndimage.gaussian_filter(m * m, 4) - ndimage.gaussian_filter(m, 4) ** 2, 0))
    return b1, b2


def block_histograms(score, truth, valid):
    idx = binned(score)
    pos, neg = [], []
    for v in range(0, score.shape[0], BLOCK):
        for u in range(0, score.shape[1], BLOCK):
            box = np.s_[v:v + BLOCK, u:u + BLOCK]
            ok, t, i = valid[box], truth[box], idx[box]
            if ok.any():
                pos.append(np.bincount(i[ok & t], minlength=BINS))
                neg.append(np.bincount(i[ok & ~t], minlength=BINS))
    return np.array(pos), np.array(neg)


def interval(values):
    lo, hi = np.nanpercentile(values, [2.5, 97.5])
    return [float(lo), float(hi)]


def bootstrap_counts(weights, histograms):
    """Sum block histograms for each draw, skipping empty bins and keeping integer counts."""
    return (csr_matrix(histograms.T) @ weights.T).T


def pooled(maps, truth, valid):
    """Block bootstrap with the same draws for every score; paired differences for H4 and H5."""
    hist = {s: block_histograms(maps[s], truth, valid) for s in SCORES}
    blocks = len(hist["Z_out"][0])
    draws = np.random.default_rng(SEED).integers(0, blocks, (DRAWS, blocks))
    weights = np.stack([np.bincount(d, minlength=blocks) for d in draws])
    est = {s: ranking(p.sum(0), n.sum(0)) for s, (p, n) in hist.items()}
    boot = {}
    for s, (p, n) in hist.items():
        positives = bootstrap_counts(weights, p)
        negatives = bootstrap_counts(weights, n)
        boot[s] = np.array([ranking(a, b) for a, b in zip(positives, negatives)], dtype=float)
    out = {"blocks": blocks, "prevalence": float(truth[valid].mean())}
    for s in SCORES:
        out[s] = {"PR_AUC": est[s][0], "PR_AUC_95": interval(boot[s][:, 0]),
                  "ROC_AUC": est[s][1], "ROC_AUC_95": interval(boot[s][:, 1])}
    best_base = np.maximum(boot["B1"][:, 1], boot["B2"][:, 1])
    out["diff_PR_Zout_minus_Zin"] = {"estimate": est["Z_out"][0] - est["Z_in"][0],
                                     "interval_95": interval(boot["Z_out"][:, 0] - boot["Z_in"][:, 0])}
    out["diff_ROC_Zout_minus_best_baseline"] = {"estimate": est["Z_out"][1] - max(est["B1"][1], est["B2"][1]),
                                                "interval_95": interval(boot["Z_out"][:, 1] - best_base)}
    return out


def labels_for(fragment, surface, shape):
    if fragment == "Frag4":
        path = Path("data/phase11/raw/inklabels.png")
        if sha(path) != FRAG4_LABELS_SHA:
            raise ValueError("Frag4 labels changed since phase 12")
    else:
        path = WORK / fragment.lower() / "inklabels.png"
        if not path.exists():
            request = urllib.request.Request(surface.label_url, headers={"User-Agent": "vesuvius-data-explorer"})
            with urllib.request.urlopen(request, timeout=300) as response:
                path.write_bytes(response.read())
    labels = np.asarray(Image.open(path).convert("L")) > 127
    if labels.shape != shape:
        raise ValueError(f"{fragment}: label grid {labels.shape} differs from mask {shape}")
    return labels, {"url": surface.label_url, "sha256": sha(path), "positive_fraction_whole_grid": float(labels.mean())}


def roi_scores(maps, truth, valid):
    out = {}
    for s, m in maps.items():
        i = binned(m)
        out[s] = dict(zip(("PR_AUC", "ROC_AUC"), ranking(np.bincount(i[valid & truth], minlength=BINS),
                                                          np.bincount(i[valid & ~truth], minlength=BINS))))
    return out


def report(out):
    protocol = read_frozen_protocol(PROTOCOL)
    result = {"protocol_sha256": PROTOCOL_SHA, "label_of_results": protocol["label_of_results"], "fragments": {}}
    for fragment in protocol["fragments"]:
        work = WORK / fragment.lower()
        prep = json.loads((work / "z-frag4-w2-prepare.json").read_bytes())
        run = json.loads((work / "z-frag4-w2-run.json").read_bytes())
        if sha(work / "z-frag4-w2-scores.npz") != run["scores_npz_sha256"]:
            raise ValueError(f"{fragment}: scores changed since the CUDA run")
        scores = np.load(work / "z-frag4-w2-scores.npz")
        shape = tuple(prep["mask_shape"])
        labels, label_info = labels_for(fragment, Surface(fragment, shape), shape)
        entry = {"labels": label_info, "direction_air": prep["direction"]["air"], "run": run, "rois": {}}
        stacks, truths, valids = {s: [] for s in SCORES}, [], []
        for roi in prep["rois"]:
            name = roi["name"]
            weight = scores[f"{name}_weight"]
            maps = {"Z_out": scores[f"{name}_Z_out"].astype(float), "Z_in": scores[f"{name}_Z_in"].astype(float)}
            maps["B1"], maps["B2"] = baselines(np.load(work / f"{name}-zout-w2.npy"))
            support = ndimage.binary_erosion(np.load(work / f"{name}-mask.npy"), iterations=16)
            valid = support & (weight >= 0.25 * weight.max()) & np.isfinite(maps["Z_out"]) & np.isfinite(maps["Z_in"])
            truth = sample_labels(labels, roi["native_origin_rc"], 0)
            positives, negatives = int((valid & truth).sum()), int((valid & ~truth).sum())
            included = positives >= MIN_CLASS and negatives >= MIN_CLASS
            entry["rois"][name] = {"valid_pixels": int(valid.sum()), "positives": positives, "included": included,
                                   **roi_scores(maps, truth, valid)}
            if included:
                for s in SCORES:
                    stacks[s].append(maps[s])
                truths.append(truth)
                valids.append(valid)
        if truths:
            p = pooled({s: np.hstack(v) for s, v in stacks.items()}, np.hstack(truths), np.hstack(valids))
            entry["pooled"] = p
            entry["hypotheses"] = {"H3": p["Z_out"]["ROC_AUC_95"][0] > 0.5,
                                   "H4": p["diff_PR_Zout_minus_Zin"]["interval_95"][0] > 0,
                                   "H5": p["diff_ROC_Zout_minus_best_baseline"]["interval_95"][0] > 0}
        else:
            entry["pooled"], entry["hypotheses"] = None, {"H3": False, "H4": False, "H5": False}
        result["fragments"][fragment] = entry
    result["generalization"] = all(e["hypotheses"]["H3"] for e in result["fragments"].values())
    Path(out).write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps({f: e["hypotheses"] for f, e in result["fragments"].items()}, indent=1),
          "generalization:", result["generalization"])


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cli.add_argument("--prepare", choices=sorted(FILES))
    cli.add_argument("--report", type=Path)
    args = cli.parse_args()
    if args.prepare:
        prepare(args.prepare)
    elif args.report:
        report(args.report)
    else:
        cli.error("--prepare FRAGMENT or --report")
