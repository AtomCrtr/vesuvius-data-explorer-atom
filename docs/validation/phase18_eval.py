"""Phase 18: depth order of checkpoint A on PHerc0343P with identical tiling, supports N and E.

Protocol: docs/validation/phase18-protocol.json, committed with this script and its tests before any
phase 18 download or inference. From the repository root, in order (two interpreters):

    .venv/Scripts/python.exe docs/validation/phase18_eval.py --prepare        # layers 01-63 + mask
    data/phase6-cuda/Scripts/python.exe docs/validation/phase18_eval.py --run  # A, six maps (CUDA)
    .venv/Scripts/python.exe docs/validation/phase18_eval.py --baselines      # B1, B2
    .venv/Scripts/python.exe docs/validation/phase18_eval.py --hash           # phase18-scores.json, commit
    .venv/Scripts/python.exe docs/validation/phase18_eval.py --supports       # labels + IR, counts, commit
    .venv/Scripts/python.exe docs/validation/phase18_eval.py --report docs/validation/phase18-eval.json

``--supports`` refuses to run before phase18-scores.json matches the maps on disk, and ``--report``
refuses any map whose SHA-256 differs from it. No ROC-AUC is computed before ``--report``.
"""

import argparse
import hashlib
import itertools
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
from scipy import ndimage
from scipy.sparse import csr_matrix

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from phase12_ink_eval import ranking  # noqa: E402

PROTOCOL = HERE / "phase18-protocol.json"
PROTOCOL_SHA = {"phase18-protocol.json": "1c115794a0eecaf496b4c2b5107c43a98e54bcfad5d66f4f87771deea1aebe26"}
SCORES_JSON = HERE / "phase18-scores.json"
SUPPORTS_JSON = HERE / "phase18-supports.json"
PREPARE_JSON = HERE / "phase18-prepare.json"
TILE, BINS, QLEVELS = 256, 4096, 256
DRAWS, SEED_COMPONENTS, SEED_ROI, SEED_BLOCK = 1999, 218, 219, 220
ROLLS, SEED_ROLLS, MIN_SHIFT = 2000, 1802, 64
PRIMARY = ("Z_out_s128", "Z_in_s128")
BASELINES = ("B1", "B2")
PAIRS = [PRIMARY, ("Z_out_s256", "Z_in_s256"), ("Z_out_s256", "Z_out_s128"), ("Z_in_s256", "Z_in_s128"),
         ("Z_out_s128_w0162", "Z_in_s128_w0162")]
# Support E variants: (score reduction, score scale, negatives). The first one carries the hypotheses.
E_VARIANTS = [("area", "quantised", "clean"), ("area", "raw_4096", "clean"), ("area", "quantised", "clean_no_ir"),
              ("nearest", "quantised", "clean")]


# --------------------------------------------------------------------------- protocol and files

def read_protocol(path=PROTOCOL):
    path = Path(path)
    content = path.read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(content).hexdigest() != PROTOCOL_SHA.get(path.name):
        raise ValueError("Unknown or modified phase 18 protocol")
    return json.loads(content)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(1 << 24):
            digest.update(block)
    return digest.hexdigest()


def fetch(url, path, budget):
    """Download once into path; budget is a one-element list of remaining bytes."""
    path = Path(path)
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "vesuvius-data-explorer"})
    with urlopen(request, timeout=300) as response:
        size = int(response.headers["Content-Length"])
        if size > budget[0]:
            raise ValueError("Phase 18 download budget exhausted")
        budget[0] -= size
        temp = path.with_suffix(path.suffix + ".part")
        with temp.open("wb") as out:
            while block := response.read(1 << 20):
                out.write(block)
        if temp.stat().st_size != size:
            raise IOError(f"Incomplete download: {url}")
    temp.replace(path)
    return path


def load_grey(path):
    """Ink labels as booleans (> 127 in 8-bit grey), the phase 13 rule."""
    from PIL import Image

    with Image.open(path) as image:
        return np.asarray(image.convert("L")) > 127


def load_luma(path):
    """Infrared as float luma: grey as is, RGB(A) 0.299 R + 0.587 G + 0.114 B, 16-bit as float."""
    from PIL import Image

    with Image.open(path) as image:
        if image.mode in ("RGB", "RGBA"):
            rgb = np.asarray(image.convert("RGB"))
            return (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]).astype(np.float32)
        return np.asarray(image).astype(np.float32)


def load_mask(path):
    from phase17_orientation import load_mask as phase17_mask

    return phase17_mask(path)


# --------------------------------------------------------------------------- tiling

def plane_indices(window, order):
    """Indices into the layer stack 01-63 (layer k at index k - 1) in model order."""
    first, last = window
    ascending = list(range(first - 1, last))
    return ascending[::-1] if order == "Z_out" else ascending


def padded_shape(shape, tile=TILE):
    return tuple(int(np.ceil(n / tile) * tile) for n in shape)


def tile_origins(shape_p, stride, tile=TILE):
    return [(v, u) for v in range(0, shape_p[0] - tile + 1, stride) for u in range(0, shape_p[1] - tile + 1, stride)]


def run_tiles(mask, stride, tile=TILE):
    """Origins of the tiles that contain at least one mask pixel, on the padded canvas."""
    shape_p = padded_shape(mask.shape, tile)
    padded = np.zeros(shape_p, bool)
    padded[:mask.shape[0], :mask.shape[1]] = mask
    integral = np.pad(padded.astype(np.int64).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    keep = []
    for v, u in tile_origins(shape_p, stride, tile):
        total = integral[v + tile, u + tile] - integral[v, u + tile] - integral[v + tile, u] + integral[v, u]
        if total:
            keep.append((v, u))
    return keep


def coverage(shape, origins, tile=TILE):
    shape_p = padded_shape(shape, tile)
    covered = np.zeros(shape_p, bool)
    for v, u in origins:
        covered[v:v + tile, u:u + tile] = True
    return covered[:shape[0], :shape[1]]


def hann(tile=TILE):
    w = np.hanning(tile + 2)[1:-1]
    return np.outer(w, w).astype(np.float64)


# --------------------------------------------------------------------------- grid reduction

def grid_shape(shape, scale, mode):
    f = np.rint if mode == "round" else np.floor
    return tuple(int(f(scale * n)) for n in shape)


def cell_bounds(n, m):
    return (np.arange(m + 1) * n) // m


def cell_sums(values, rows, cols):
    return np.add.reduceat(np.add.reduceat(values, rows[:-1], axis=0, dtype=np.float64), cols[:-1], axis=1)


def reduce_mean(values, gshape, finite_share=None):
    """Cell means; with finite_share, NaN-aware and NaN where fewer finite pixels than that share."""
    rows, cols = cell_bounds(values.shape[0], gshape[0]), cell_bounds(values.shape[1], gshape[1])
    area = np.outer(np.diff(rows), np.diff(cols))
    if finite_share is None:
        return cell_sums(values, rows, cols) / area
    finite = np.isfinite(values)
    total = cell_sums(np.where(finite, values, 0), rows, cols)
    count = cell_sums(finite, rows, cols)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = total / count
    out[count < finite_share * area] = np.nan
    return out


def reduce_nearest(values, gshape):
    n, m = values.shape
    # The canvas pixel that contains the cell centre.
    rows = np.clip(np.floor((np.arange(gshape[0]) + 0.5) * n / gshape[0]).astype(int), 0, n - 1)
    cols = np.clip(np.floor((np.arange(gshape[1]) + 0.5) * m / gshape[1]).astype(int), 0, m - 1)
    return values[np.ix_(rows, cols)]


def reduce_binary(binary, gshape, how):
    if how == "nearest":
        return reduce_nearest(binary, gshape).astype(bool)
    mean = reduce_mean(binary, gshape)
    return mean >= 0.5 if how == "area_half" else mean > 0


def inside_distance(binary, metric):
    """Distance from each True pixel to the nearest False pixel; outside the image counts as False."""
    padded = np.pad(binary, 1, constant_values=False)
    if metric == "euclidean":
        dist = ndimage.distance_transform_edt(padded)
    else:
        dist = ndimage.distance_transform_cdt(padded, metric=metric)  # int32: no float copy on large canvases
    return dist[1:-1, 1:-1]


def erode(binary, radius, metric):
    return inside_distance(binary, metric) > radius


def distance_to(letters, metric):
    """Distance from each pixel to the nearest letter pixel; outside the image is not a letter."""
    padded = np.pad(~letters, 1, constant_values=True)
    if metric == "euclidean":
        dist = ndimage.distance_transform_edt(padded)
    else:
        dist = ndimage.distance_transform_cdt(padded, metric=metric)  # int32: no float copy on large canvases
    return dist[1:-1, 1:-1]


# --------------------------------------------------------------------------- support E

def combinations(protocol):
    keys = ("grid_size", "label_and_mask_reduction", "infrared_reduction", "morphology_grid", "metric",
            "median_population")
    options = protocol["support_E"]["interpretations"]
    return [dict(zip(keys, values)) for values in itertools.product(*(options[k] for k in keys))]


class SupportE:
    """Builds support E on one fragment for any interpretation, caching the shared intermediate steps."""

    def __init__(self, labels, luma, mask, covered, scale):
        if not labels.shape == luma.shape == mask.shape == covered.shape:
            raise ValueError("Labels, infrared, mask and coverage must share the canvas")
        self.labels, self.luma, self.mask, self.covered, self.scale = labels, luma, mask, covered, scale
        self.cache = {}

    def _get(self, key, build):
        if key not in self.cache:
            self.cache[key] = build()
        return self.cache[key]

    def build(self, combo):
        s = self.scale
        gshape = self._get(("g", combo["grid_size"]), lambda: grid_shape(self.labels.shape, s, combo["grid_size"]))
        how, metric, where = combo["label_and_mask_reduction"], combo["metric"], combo["morphology_grid"]
        letters = self._get(("L", gshape, how), lambda: reduce_binary(self.labels, gshape, how))
        mask_g = self._get(("M", gshape, how), lambda: reduce_binary(self.mask, gshape, how))
        covered = self._get(("C", gshape), lambda: reduce_mean(self.covered, gshape) >= 1.0)
        if where == "grid":
            ink_eroded = self._get(("ie", gshape, how, metric), lambda: erode(letters, 2, metric))
            far = self._get(("far", gshape, how, metric), lambda: distance_to(letters, metric) >= 12)
            mask_eroded = self._get(("me", gshape, how, metric), lambda: erode(mask_g, 10, metric))
        else:
            ink_eroded = self._get(("ie", gshape, how, metric, "c"), lambda: reduce_binary(
                self._get(("cie", metric), lambda: erode(self.labels, 2 / s, metric)), gshape, how))
            far = self._get(("far", gshape, how, metric, "c"), lambda: reduce_binary(
                self._get(("cfar", metric), lambda: distance_to(self.labels, metric) >= 12 / s), gshape, how))
            mask_eroded = self._get(("me", gshape, how, metric, "c"), lambda: reduce_binary(
                self._get(("cme", metric), lambda: erode(self.mask, 10 / s, metric)), gshape, how))
        region = mask_eroded & covered
        ink = ink_eroded & region
        luma = self._get(("ir", gshape, combo["infrared_reduction"]), lambda: (
            reduce_mean(self.luma, gshape) if combo["infrared_reduction"] == "area"
            else reduce_nearest(self.luma, gshape)))
        population = {"region": region, "mask": mask_g, "region_non_ink": region & ~letters}[combo["median_population"]]
        median = float(np.median(luma[population]))
        bright = luma > median
        clean = region & far & bright & ~ink
        return {"gshape": gshape, "letters": letters, "region": region, "ink": ink, "clean": clean,
                "clean_no_ir": region & far & ~ink, "luma": luma, "median": median, "bright": bright,
                "counts": {"ink": int(ink.sum()), "clean": int(clean.sum()), "valid": int(region.sum())}}


def select_combination(protocol, builders):
    """Counts and errors of every interpretation; the selected one minimises the maximal relative error."""
    published = protocol["support_E"]["published_counts"]
    rows, best = [], None
    for index, combo in enumerate(combinations(protocol)):
        counts, errors = {}, []
        for fragment, builder in builders.items():
            counts[fragment] = builder.build(combo)["counts"]
            for key, target in published[fragment].items():
                gap = abs(counts[fragment][key] - target)
                errors.append(gap / target if target else (0.0 if gap == 0 else np.inf))
        row = {"index": index, **combo, "counts": counts, "max_relative_error": float(max(errors))}
        rows.append(row)
        if best is None or row["max_relative_error"] < best["max_relative_error"]:
            best = row
    limit = protocol["support_E"]["reconstructed_if_max_relative_error_at_most"]
    return {"combinations": rows, "selected": best["index"],
            "status": "reconstructed" if best["max_relative_error"] <= limit else "approximate"}


# --------------------------------------------------------------------------- scores and units

def binned(score, bins=BINS):
    """Phase 12 binning on [0, 1]; non-finite pixels get bin 0 and must never be selected."""
    score = np.nan_to_num(np.asarray(score, dtype=np.float32), nan=0.0, posinf=1.0, neginf=0.0)
    return np.clip((score * bins).astype(np.int32), 0, bins - 1).astype(np.int16)


def quantize(score, region, levels=QLEVELS):
    """EconLearn's rule: 256 levels between the 0.1 and 99.9 percentiles of the map over the region."""
    values = score[region & np.isfinite(score)]
    lo, hi = np.percentile(values, [0.1, 99.9])
    span = hi - lo if hi > lo else 1.0
    filled = np.nan_to_num(score, nan=lo)
    return np.clip(np.floor((filled - lo) / span * levels), 0, levels - 1).astype(np.int16)


def require_finite(raw, names, selection):
    for name in names:
        if not np.isfinite(raw[name][selection]).all():
            raise ValueError(f"{name} is not finite on every evaluated pixel")


def attach_units(positives, evaluated, step=1):
    """Unit id per pixel: positives keep their 8-connected component, other pixels the nearest one."""
    components, count = ndimage.label(positives, structure=np.ones((3, 3)))
    if count == 0:
        raise ValueError("No positive pixel: no ink component to bootstrap")
    if step > 1:
        n, m = components.shape
        padded = np.pad(components, ((0, -n % step), (0, -m % step)))
        blocks = padded.reshape(padded.shape[0] // step, step, padded.shape[1] // step, step).max(axis=(1, 3))
    else:
        blocks = components
    _, (ri, ci) = ndimage.distance_transform_edt(blocks == 0, return_indices=True)
    nearest = blocks[ri, ci]
    if step > 1:
        nearest = np.repeat(np.repeat(nearest, step, 0), step, 1)[:components.shape[0], :components.shape[1]]
    units = np.where(positives, components, nearest)
    return np.where(evaluated, units, 0), count


def unit_histograms(bins_map, units, selection, n_units, nbins):
    rows, cols = units[selection] - 1, bins_map[selection]
    data = np.ones(rows.size, dtype=np.float64)
    return csr_matrix((data, (rows, cols)), shape=(n_units, nbins))


def bootstrap(maps, positives, negatives, units, n_units, nbins, draws, seed):
    """Point estimates and per-draw (AP, ROC-AUC) of every map with the same unit draws."""
    rng = np.random.default_rng(seed)
    weights = np.stack([np.bincount(rng.integers(0, n_units, n_units), minlength=n_units) for _ in range(draws)])
    estimate, per_draw = {}, {}
    for name, bins_map in maps.items():
        pos = unit_histograms(bins_map, units, positives, n_units, nbins)
        neg = unit_histograms(bins_map, units, negatives, n_units, nbins)
        estimate[name] = ranking(np.asarray(pos.sum(0)).ravel(), np.asarray(neg.sum(0)).ravel())
        pos_draws, neg_draws = (pos.T @ weights.T).T, (neg.T @ weights.T).T
        per_draw[name] = np.array([ranking(a, b) for a, b in zip(pos_draws, neg_draws)], dtype=float)
    return estimate, per_draw


def interval(values):
    lo, hi = np.nanpercentile(values, [2.5, 97.5])
    return [float(lo), float(hi)]


def hypotheses(estimate, per_draw):
    roc = {k: v[:, 1] for k, v in per_draw.items()}
    best = np.maximum(roc["B1"], roc["B2"])
    h1 = interval(roc["Z_out_s128"] - roc["Z_in_s128"])
    h2 = interval(roc["Z_out_s128"])
    h3 = interval(roc["Z_out_s128"] - best)
    point = {k: v[1] for k, v in estimate.items()}
    return {
        "H1": {"estimate": point["Z_out_s128"] - point["Z_in_s128"], "interval_95": h1, "supported": h1[0] > 0},
        "H2": {"estimate": point["Z_out_s128"], "interval_95": h2, "supported": h2[0] > 0.5},
        "H3": {"estimate": point["Z_out_s128"] - max(point["B1"], point["B2"]), "interval_95": h3,
               "supported": h3[0] > 0}}


def summarize(estimate, per_draw, positives, negatives):
    out = {"positives": int(positives.sum()), "negatives": int(negatives.sum()),
           "prevalence": float(positives.sum() / (positives.sum() + negatives.sum()))}
    for name, (ap, roc) in estimate.items():
        out[name] = {"PR_AUC": ap, "PR_AUC_95": interval(per_draw[name][:, 0]),
                     "ROC_AUC": roc, "ROC_AUC_95": interval(per_draw[name][:, 1])}
    return out


def differences(estimate, per_draw, pairs):
    return {f"{a} - {b}": {"estimate": estimate[a][1] - estimate[b][1],
                           "interval_95": interval(per_draw[a][:, 1] - per_draw[b][:, 1])} for a, b in pairs}


def placement_test(maps_q, support, rolls, seed, min_shift, metric):
    """Rank of the true letters among cyclic rolls of the letters (EconLearn's control, our rule)."""
    letters, region, bright = support["letters"], support["region"], support["bright"]
    eroded = erode(letters, 2, metric)
    far = distance_to(letters, metric) >= 12
    rng = np.random.default_rng(seed)
    shifts = []
    while len(shifts) < rolls:
        dy, dx = int(rng.integers(0, letters.shape[0])), int(rng.integers(0, letters.shape[1]))
        wrap_y, wrap_x = min(dy, letters.shape[0] - dy), min(dx, letters.shape[1] - dx)
        if np.hypot(wrap_y, wrap_x) >= min_shift:
            shifts.append((dy, dx))

    def roc(q, ink, clean):
        value = ranking(np.bincount(q[ink], minlength=QLEVELS), np.bincount(q[clean], minlength=QLEVELS))[1]
        return np.nan if value is None else value

    true = {name: roc(q, support["ink"], support["clean"]) for name, q in maps_q.items()}
    rolled = {name: [] for name in maps_q}
    for dy, dx in shifts:
        ink = np.roll(eroded, (dy, dx), (0, 1)) & region
        clean = region & np.roll(far, (dy, dx), (0, 1)) & bright & ~ink
        for name, q in maps_q.items():
            rolled[name].append(roc(q, ink, clean))
    result = {}
    for name, values in rolled.items():
        values = np.array(values)
        defined = values[np.isfinite(values)]  # A roll whose letters leave the region has no ink: undefined.
        result[name] = {"true_ROC_AUC": true[name], "rolls": rolls, "defined_rolls": int(defined.size),
                        "rolled_max": float(defined.max()), "rolled_p99": float(np.percentile(defined, 99)),
                        "true_beats": int((defined < true[name]).sum()), "econlearn_best_random": 0.722}
    return result


# --------------------------------------------------------------------------- steps

def work_dir(protocol):
    return Path(protocol["work_dir"])


def prepare(protocol):
    from PIL import Image

    work, frag = work_dir(protocol), protocol["fragment"]
    budget = [protocol["budget_bytes"]]
    files = {}
    mask_path = fetch(frag["base_url"] + frag["mask"], work / "raw" / frag["mask"], budget)
    files[frag["mask"]] = sha(mask_path)
    mask = load_mask(mask_path)
    if list(mask.shape) != frag["canvas_shape_hw"]:
        raise ValueError(f"Unexpected canvas {mask.shape}")
    shape_p = padded_shape(mask.shape)
    stack = np.lib.format.open_memmap(work / "layers01_63.npy", mode="w+", dtype=np.uint8, shape=(63, *shape_p))
    for k in range(1, 64):
        name = frag["layers"].format(k)
        path = fetch(frag["base_url"] + name, work / "raw" / name, budget)
        files[name] = sha(path)
        with Image.open(path) as image:
            if image.mode != "L" or image.size != (mask.shape[1], mask.shape[0]):
                raise ValueError(f"{name}: expected 8-bit grey on the mask canvas")
            stack[k - 1, :mask.shape[0], :mask.shape[1]] = np.asarray(image)
    stack.flush()
    tiles = {str(s): run_tiles(mask, s) for s in (128, 256)}
    manifest = {"protocol_sha256": PROTOCOL_SHA[PROTOCOL.name], "files_sha256": files, "padded_shape": shape_p,
                "run_tiles": {s: len(t) for s, t in tiles.items()}, "stack": "layers01_63.npy (outside Git)"}
    (work / "tiles.json").write_text(json.dumps(tiles), encoding="utf-8")
    PREPARE_JSON.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("padded_shape", "run_tiles")}, indent=1))


def run(protocol, phase6):
    import time

    import torch
    from phase6_cuda import CHECKPOINT, CODE, WEIGHTS_SHA, prepare_tile

    work = work_dir(protocol)
    if json.loads(PREPARE_JSON.read_bytes())["protocol_sha256"] != PROTOCOL_SHA[PROTOCOL.name]:
        raise ValueError("phase18-prepare.json was written under another protocol")
    ckpt = phase6 / "canonical" / CHECKPOINT
    if sha(ckpt) != WEIGHTS_SHA or any(sha(phase6 / "villa" / p) != h for p, h in CODE.items()):
        raise ValueError("The checkpoint or the audited model code changed")
    sys.path.insert(0, str((phase6 / "villa").resolve()))
    from model_resnet3d_3d_decoder import RegressionModel, _strip_known_prefixes

    dev = torch.device("cuda:0")
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.allow_tf32 = torch.backends.cuda.matmul.allow_tf32 = False
    blob = torch.load(ckpt, map_location="cpu", weights_only=True, mmap=True)
    state = _strip_known_prefixes(blob["state_dict"])
    with torch.device("meta"):
        model = RegressionModel(with_norm=any(k.startswith("normalization.") for k in state))
    model.load_state_dict(state, strict=True, assign=True)
    model = model.to(dev).eval()
    del blob, state

    def infer(tile):
        prepared, _ = prepare_tile(np.ascontiguousarray(tile), False)  # planes already in model order
        with torch.inference_mode():
            logits = model(torch.from_numpy(prepared).to(dev))
            score = torch.nn.functional.interpolate(logits.sigmoid(), size=(TILE, TILE), mode="bilinear",
                                                    align_corners=False)
        return score[0, 0].cpu().numpy().astype(np.float64)

    stack = np.load(work / "layers01_63.npy", mmap_mode="r")
    tiles = json.loads((work / "tiles.json").read_bytes())
    height, width = protocol["fragment"]["canvas_shape_hw"]
    weight = hann()
    report = {"weights_sha256": WEIGHTS_SHA, "torch": torch.__version__, "cuda": torch.version.cuda,
              "gpu": torch.cuda.get_device_name(), "inference": "eval_fp32_no_tf32_deterministic_cudnn", "maps": {}}
    for name, spec in protocol["inputs"]["maps"].items():
        start = time.time()
        planes = plane_indices(spec["window"], spec["order"])
        origins = [tuple(o) for o in tiles[str(spec["stride"])]]
        acc = np.zeros(stack.shape[1:])
        wsum = np.zeros(stack.shape[1:])
        for v, u in origins:
            acc[v:v + TILE, u:u + TILE] += weight * infer(stack[planes, v:v + TILE, u:u + TILE])
            wsum[v:v + TILE, u:u + TILE] += weight
        v, u = origins[len(origins) // 2]
        first = infer(stack[planes, v:v + TILE, u:u + TILE])
        again = infer(stack[planes, v:v + TILE, u:u + TILE])
        with np.errstate(invalid="ignore", divide="ignore"):
            np.save(work / f"{name}.npy", (acc / wsum)[:height, :width].astype(np.float32))
        if name == "Z_out_s128":
            np.save(work / "weight_s128.npy", wsum[:height, :width].astype(np.float32))
        report["maps"][name] = {"tiles": len(origins), "seconds": round(time.time() - start, 1),
                                "repeat_max_abs_diff": float(np.abs(first - again).max())}
        print(name, report["maps"][name], flush=True)
    (work / "run.json").write_text(json.dumps(report, indent=1), encoding="utf-8")


def baselines(protocol, strip=512, halo=32):
    from phase13_eval import baselines as phase13_baselines

    work = work_dir(protocol)
    stack = np.load(work / "layers01_63.npy", mmap_mode="r")
    height, width = protocol["fragment"]["canvas_shape_hw"]
    planes = plane_indices(protocol["inputs"]["primary_window"], "Z_out")
    b1, b2 = np.full((height, width), np.nan, np.float32), np.full((height, width), np.nan, np.float32)
    for top in range(0, height, strip):
        lo, hi = max(top - halo, 0), min(top + strip + halo, height)
        volume = stack[planes, lo:hi, :width]
        x1, x2 = phase13_baselines(volume)
        b1[top:top + strip] = x1[top - lo:top - lo + strip]
        b2[top:top + strip] = x2[top - lo:top - lo + strip]
    np.save(work / "B1.npy", b1)
    np.save(work / "B2.npy", b2)


def map_names(protocol):
    return [*protocol["inputs"]["maps"], *BASELINES, "weight_s128"]


def hash_maps(protocol, econlearn_sha=None):
    work = work_dir(protocol)
    frag = protocol["fragment"]
    mask = load_mask(work / "raw" / frag["mask"])
    out = {"protocol_sha256": PROTOCOL_SHA[PROTOCOL.name], "statement": "score maps hashed before any label or "
           "infrared download", "run": json.loads((work / "run.json").read_bytes()), "maps": {}}
    for name in map_names(protocol):
        path = work / f"{name}.npy"
        values = np.load(path, mmap_mode="r")
        inside = np.asarray(values[mask])
        finite = inside[np.isfinite(inside)]
        out["maps"][name] = {"sha256": sha(path), "finite_share_in_mask": float(finite.size / inside.size),
                             "mean": float(finite.mean()), "p99": float(np.percentile(finite, 99)),
                             "share_above_0.5": float((finite > 0.5).mean())}
    if econlearn_sha:
        theirs = json.loads(Path(econlearn_sha).read_bytes())
        ours = json.loads(PREPARE_JSON.read_bytes())["files_sha256"]
        out["econlearn_layer_sha256"] = {k: theirs[k] == v for k, v in ours.items() if k in theirs}
    SCORES_JSON.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: v["mean"] for k, v in out["maps"].items()}, indent=1))


def check_maps(protocol):
    if not SCORES_JSON.exists():
        raise ValueError("phase18-scores.json is missing: hash the score maps before opening labels")
    frozen = json.loads(SCORES_JSON.read_bytes())["maps"]
    work = work_dir(protocol)
    for name in map_names(protocol):
        if sha(work / f"{name}.npy") != frozen[name]["sha256"]:
            raise ValueError(f"{name}.npy differs from phase18-scores.json")


def fragment_inputs(protocol, key, budget):
    spec = protocol[key]
    work = work_dir(protocol) / ("raw" if key == "fragment" else "raw500p2")
    names = ([spec["mask"], spec["infrared"], spec["ink_labels"]] if key == "fragment" else spec["files"])
    paths = [fetch(spec["base_url"] + n, work / n, budget) for n in names]
    mask, luma, labels = load_mask(paths[0]), load_luma(paths[1]), load_grey(paths[2])
    if list(mask.shape) != spec["canvas_shape_hw"] or luma.shape != mask.shape or labels.shape != mask.shape:
        raise ValueError(f"{spec['name']}: mask, infrared and labels do not share the expected canvas")
    covered = coverage(mask.shape, run_tiles(mask, 128))
    return {"mask": mask, "luma": luma, "labels": labels, "covered": covered,
            "sha256": {n: sha(p) for n, p in zip(names, paths)}}


def roi_ids(shape, size):
    rows, cols = np.indices(shape, sparse=True)
    return (rows // size) * int(np.ceil(shape[1] / size)) + cols // size


def support_n(protocol, labels, mask, weight, finite, tolerance_um, distance=None):
    """Valid, positive and negative pixels of support N on the canvas (phase 11 and phase 12 rules)."""
    valid = ndimage.binary_erosion(mask, iterations=16) & (weight >= 0.25 * np.nanmax(weight)) & finite
    positives = valid & labels
    if distance is None:
        distance = ndimage.distance_transform_edt(~labels)
    negatives = valid & ~labels & (distance > tolerance_um / protocol["fragment"]["canvas_um_per_px"])
    return valid, positives, negatives


def included_rois(protocol, mask, positives, negatives):
    """ROIs of the frozen pavage that enter the pooled N metrics (mask share and MIN_CLASS)."""
    rois = protocol["support_N"]["rois"]
    roi = roi_ids(mask.shape, rois["size_px"])
    ids = np.unique(roi)
    fraction = ndimage.sum(mask, roi, ids) / rois["size_px"] ** 2
    pos, neg = ndimage.sum(positives, roi, ids), ndimage.sum(negatives, roi, ids)
    candidates = fraction >= rois["keep_if_mask_fraction_at_least"]
    keep = ids[candidates & (pos >= 1000) & (neg >= 1000)]
    return np.isin(roi, keep), roi, {"candidates": int(candidates.sum()), "kept": int(keep.size)}


def tolerances(protocol):
    return [protocol["support_N"]["tolerance_um"], *protocol["support_N"]["tolerance_sensitivity_um"]]


def supports(protocol):
    check_maps(protocol)
    budget = [protocol["budget_bytes"]]
    frag = fragment_inputs(protocol, "fragment", budget)
    other = fragment_inputs(protocol, "count_check_fragment", budget)
    work = work_dir(protocol)
    weight = np.load(work / "weight_s128.npy")
    finite = np.all([np.isfinite(np.load(work / f"{m}.npy", mmap_mode="r")) for m in (*PRIMARY, *BASELINES)], axis=0)
    distance = ndimage.distance_transform_edt(~frag["labels"])
    counts_n, rois = {}, None
    for t in tolerances(protocol):
        valid, pos, neg = support_n(protocol, frag["labels"], frag["mask"], weight, finite, t, distance)
        if rois is None:
            keep, _, rois = included_rois(protocol, frag["mask"], pos, neg)
        counts_n[f"T{t}um"] = {"valid": int(valid.sum()), "positives": int((pos & keep).sum()),
                               "negatives": int((neg & keep).sum())}
    del distance
    scale = protocol["support_E"]["scale"]
    builders = {protocol["fragment"]["name"]: SupportE(frag["labels"], frag["luma"], frag["mask"], frag["covered"],
                                                       scale),
                protocol["count_check_fragment"]["name"]: SupportE(other["labels"], other["luma"], other["mask"],
                                                                   other["covered"], scale)}
    selection = select_combination(protocol, builders)
    out = {"protocol_sha256": PROTOCOL_SHA[PROTOCOL.name], "statement": "supports and counts only, no ROC-AUC",
           "files_sha256": {**frag["sha256"], **other["sha256"]},
           "support_N": {"counts_in_included_rois": counts_n, "rois": rois}, "support_E": selection}
    SUPPORTS_JSON.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({"status": selection["status"],
                      "selected": selection["combinations"][selection["selected"]]}, indent=1))


def secondary_intervals(maps, positives, negatives, unit_map, nbins, seed):
    """Paired bootstrap over arbitrary units (ROIs or blocks), for the secondary intervals."""
    selection = positives | negatives
    ids, inverse = np.unique(unit_map[selection], return_inverse=True)
    units = np.zeros(positives.shape, dtype=np.int64)
    units[selection] = inverse + 1
    estimate, per_draw = bootstrap(maps, positives, negatives, units, ids.size, nbins, DRAWS, seed)
    return {"units": int(ids.size), "differences": differences(estimate, per_draw, [PRIMARY]),
            "Z_out_s128_ROC_AUC_95": interval(per_draw["Z_out_s128"][:, 1])}


def evaluate(maps, positives, negatives, nbins, step=1):
    units, n_units = attach_units(positives, positives | negatives, step)
    estimate, per_draw = bootstrap(maps, positives, negatives, units, n_units, nbins, DRAWS, SEED_COMPONENTS)
    return {"components": n_units, **summarize(estimate, per_draw, positives, negatives),
            "differences": differences(estimate, per_draw, PAIRS)}, estimate, per_draw


def report(protocol, out):
    check_maps(protocol)
    if not SUPPORTS_JSON.exists():
        raise ValueError("phase18-supports.json is missing")
    work, frozen = work_dir(protocol), json.loads(SUPPORTS_JSON.read_bytes())
    frag = fragment_inputs(protocol, "fragment", [0])  # Already on disk since --supports.
    names = [*protocol["inputs"]["maps"], *BASELINES]
    raw = {m: np.load(work / f"{m}.npy") for m in names}
    weight = np.load(work / "weight_s128.npy")
    finite = np.all([np.isfinite(raw[m]) for m in (*PRIMARY, *BASELINES)], axis=0)
    result = {"protocol_sha256": PROTOCOL_SHA[PROTOCOL.name], "not_blind": protocol["not_blind"],
              "training_list_check": protocol["training_list_check"]["result"], "N": {}, "E": {}}

    # Support N: canvas, raw scores in 4096 bins, components attached on 4 x 4 blocks.
    bins_n = {m: binned(v) for m, v in raw.items()}
    distance = ndimage.distance_transform_edt(~frag["labels"])
    keep = None
    for t in tolerances(protocol):
        valid, pos, neg = support_n(protocol, frag["labels"], frag["mask"], weight, finite, t, distance)
        if keep is None:
            keep, roi, rois = included_rois(protocol, frag["mask"], pos, neg)
        pos, neg = pos & keep, neg & keep
        require_finite(raw, names, pos | neg)
        entry, estimate, per_draw = evaluate(bins_n, pos, neg, BINS, step=4)
        if t == protocol["support_N"]["tolerance_um"]:
            entry["hypotheses"] = hypotheses(estimate, per_draw)
            entry["rois"] = rois
            entry["roi_bootstrap"] = secondary_intervals(bins_n, pos, neg, np.broadcast_to(roi, pos.shape), BINS,
                                                         SEED_ROI)
            entry["block_bootstrap"] = secondary_intervals(bins_n, pos, neg, roi_ids(pos.shape, 64), BINS, SEED_BLOCK)
        result["N"][f"T{t}um"] = entry
    del distance, bins_n

    # Support E: the frozen interpretation, 8.64 um grid.
    chosen = combinations(protocol)[frozen["support_E"]["selected"]]
    support = SupportE(frag["labels"], frag["luma"], frag["mask"], frag["covered"],
                       protocol["support_E"]["scale"]).build(chosen)
    frozen_counts = frozen["support_E"]["combinations"][frozen["support_E"]["selected"]]["counts"]
    if support["counts"] != frozen_counts[protocol["fragment"]["name"]]:
        raise ValueError("Support E differs from phase18-supports.json")
    gshape, region = support["gshape"], support["region"]
    size = protocol["support_N"]["rois"]["size_px"]
    rows, cols = np.indices(gshape, sparse=True)
    centre_r = ((rows + 0.5) * frag["mask"].shape[0] / gshape[0]).astype(int) // size
    centre_c = ((cols + 0.5) * frag["mask"].shape[1] / gshape[1]).astype(int) // size
    roi_e = centre_r * int(np.ceil(frag["mask"].shape[1] / size)) + centre_c
    grids = {}
    for reduction, scale_kind, negatives in E_VARIANTS:
        if reduction not in grids:
            grids[reduction] = {m: (reduce_mean(v, gshape, finite_share=0.5) if reduction == "area"
                                    else reduce_nearest(v, gshape)) for m, v in raw.items()}
        grid = grids[reduction]
        ok = np.all([np.isfinite(grid[m]) for m in (*PRIMARY, *BASELINES)], axis=0)
        pos, neg = support["ink"] & ok, support[negatives] & ok
        require_finite(grid, names, pos | neg)
        if scale_kind == "quantised":
            maps, nbins = {m: quantize(v, region) for m, v in grid.items()}, QLEVELS
        else:
            maps, nbins = {m: binned(v) for m, v in grid.items()}, BINS
        entry, estimate, per_draw = evaluate(maps, pos, neg, nbins)
        if (reduction, scale_kind, negatives) == E_VARIANTS[0]:
            entry["hypotheses"] = hypotheses(estimate, per_draw)
            entry["confirmatory"] = frozen["support_E"]["status"] == "reconstructed"
            entry["comparison_with_EconLearn"] = {
                "Z_out_s128": {"ours": estimate["Z_out_s128"][1], "EconLearn": 0.936},
                "Z_in_s256": {"ours": estimate["Z_in_s256"][1], "EconLearn": 0.599}}
            entry["roi_bootstrap"] = secondary_intervals(maps, pos, neg, np.broadcast_to(roi_e, gshape), nbins,
                                                         SEED_ROI)
            entry["block_bootstrap"] = secondary_intervals(maps, pos, neg, roi_ids(gshape, 64), nbins, SEED_BLOCK)
            entry["placement_test"] = placement_test({m: maps[m] for m in PRIMARY}, support, ROLLS, SEED_ROLLS,
                                                     MIN_SHIFT, chosen["metric"])
        result["E"]["_".join((reduction, scale_kind, negatives))] = entry
    result["E"]["status"] = frozen["support_E"]["status"]
    result["E"]["selected_combination"] = chosen
    Path(out).write_text(json.dumps(result, indent=1), encoding="utf-8")
    key = "_".join(E_VARIANTS[0])
    print(json.dumps({"N": result["N"][f"T{protocol['support_N']['tolerance_um']}um"]["hypotheses"],
                      "E": result["E"][key]["hypotheses"]}, indent=1))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    step = cli.add_mutually_exclusive_group(required=True)
    for flag in ("--prepare", "--run", "--baselines", "--hash", "--supports"):
        step.add_argument(flag, action="store_true")
    step.add_argument("--report", type=Path)
    cli.add_argument("--phase6", type=Path, default=Path("data/phase6"))
    cli.add_argument("--econlearn-sha", type=Path, help="JSON {layer file name: SHA-256} posted by EconLearn")
    args = cli.parse_args()
    protocol = read_protocol()
    if args.prepare:
        prepare(protocol)
    elif args.run:
        run(protocol, args.phase6)
    elif args.baselines:
        baselines(protocol)
    elif args.hash:
        hash_maps(protocol, args.econlearn_sha)
    elif args.supports:
        supports(protocol)
    else:
        report(protocol, args.report)
