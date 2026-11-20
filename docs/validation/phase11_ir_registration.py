"""Phase 11, step B2: residual misregistration of the published aligned IR on the Frag4 CT grid.

Ink labels and predictions are never read. Two ink-independent measures on the 6064 x 9791 grid
(3.24 um per pixel), comparing the aligned IR with surface-volume layer 32:

1. outline: fragment edge found separately in each modality (Otsu on smoothed intensity), symmetric
   distances between the two edges, excluding CT pixels next to the mesh limit (CT == 0);
2. blocks: phase correlation of gradient magnitudes in 256 px blocks inside the eroded mask; blocks
   kept by the frozen acceptance rule ``ACCEPT``. A rigid and an affine correction are fitted on a
   checkerboard half of the blocks and scored on the other half (``landmarks_fit``).

    python -I docs/validation/phase11_ir_registration.py data/phase11 docs/validation/phase11-ir-registration.json
"""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image
from scipy import fft, ndimage

from vesuvius_data_explorer.core.optical_registration import Grid, landmarks_fit

PITCH_UM = 3.24
# Run 1 (full resolution, 256 px blocks) accepted no block: the aligned IR (raw ~10 um/px, upsampled
# about 3x) lacks the fine fibre texture of the CT. Run 2 matches at 1/4 scale (12.96 um/px); the
# acceptance rule is unchanged. Outline run 1 thresholded CT intensity (fibres); run 2 uses local std.
SCALE = 4
BLOCK, STEP, MAX_SHIFT = 128, 64, 24  # In 1/4-scale pixels: 512, 256 and 96 full-resolution pixels.
ACCEPT = {"min_ncc": 0.20, "min_peak_ratio": 1.5, "max_shift_px": MAX_SHIFT}
FEATURE_UM = 100.0  # Predeclared smallest width of interest (ink stroke order of magnitude).


def otsu(values):
    hist, edges = np.histogram(values, 256)
    centers = (edges[:-1] + edges[1:]) / 2
    w = np.cumsum(hist)
    m = np.cumsum(hist * centers)
    between = (m[-1] * w / w[-1] - m) ** 2 / np.maximum(w * (w[-1] - w), 1)
    return float(centers[np.argmax(between)])


def largest(component_mask):
    labels, count = ndimage.label(component_mask)
    if count == 0:
        return component_mask
    sizes = ndimage.sum(component_mask, labels, range(1, count + 1))
    return ndimage.binary_fill_holes(labels == 1 + int(np.argmax(sizes)))


def outline_distances(ct, ir):
    # Run 3: at 1/4 scale the papyrus texture fills the CT mesh up to a thin rim, so the mesh
    # outline (from the CT segmentation, independent of IR and ink) is the CT fragment outline.
    meshed = ct > 0
    ct_support = largest(meshed)
    ir_s = ndimage.gaussian_filter(ir.astype(np.float32), 1)
    ir_support = largest(ir_s < otsu(ir_s))  # Papyrus darker than the bright background.
    edge = lambda m: m & ~ndimage.binary_erosion(m)  # noqa: E731
    e_ct, e_ir = edge(ct_support), edge(ir_support)
    d_to_ir = ndimage.distance_transform_edt(~e_ir)[e_ct]
    d_to_ct = ndimage.distance_transform_edt(~e_ct)[e_ir]
    both = np.concatenate([d_to_ir, d_to_ct])
    stats = lambda d: {"n": int(d.size), "median_px": float(np.median(d)),  # noqa: E731
                       "rms_px": float(np.sqrt(np.mean(d**2))), "p90_px": float(np.quantile(d, .9))}
    signed = np.where(ir_support, -1, 1) * ndimage.distance_transform_edt(~e_ir)
    sweep = {}
    for k in (0, 4, 8, 12, 16):  # Uniform rim of the CT mesh versus residual misregistration.
        m = ndimage.binary_erosion(ct_support, iterations=k) if k else ct_support
        em = edge(m)
        d = np.concatenate([ndimage.distance_transform_edt(~e_ir)[em],
                            ndimage.distance_transform_edt(~em)[e_ir]])
        sweep[k] = {**stats(d), "iou": float((m & ir_support).sum() / (m | ir_support).sum())}
    return {"ct_to_ir": stats(d_to_ir), "ir_to_ct": stats(d_to_ct), "symmetric": stats(both),
            "ct_edge_signed_px_median": float(np.median(signed[e_ct])),
            "ct_erosion_sweep_px": sweep,
            "support_iou": float((ct_support & ir_support).sum() / (ct_support | ir_support).sum()),
            "ct_threshold": "CT mesh support (layer 32 > 0), largest component, holes filled",
            "ir_threshold": "Otsu on gaussian(1) IR", "scale": SCALE, "pixel_um": PITCH_UM * SCALE}


def gradient(image, valid):
    filled = np.where(valid, image, np.nanmedian(image[valid])).astype(np.float32)
    smooth = ndimage.gaussian_filter(filled, 3)  # 1/4 scale: ~39 um, cracks and edges
    return np.hypot(ndimage.sobel(smooth, 0), ndimage.sobel(smooth, 1))


def phase_shift(a, b):
    """(dy, dx) such that b(y + dy, x + dx) ~ a(y, x); peak ratio over the second maximum."""
    win = np.outer(np.hanning(a.shape[0]), np.hanning(a.shape[1]))
    fa, fb = fft.fft2((a - a.mean()) * win), fft.fft2((b - b.mean()) * win)
    cross = fb * np.conj(fa)
    corr = np.real(fft.ifft2(cross / np.maximum(np.abs(cross), 1e-12)))
    corr = fft.fftshift(corr)
    peak = np.unravel_index(np.argmax(corr), corr.shape)
    top = corr[peak]
    masked = corr.copy()
    masked[max(peak[0] - 3, 0):peak[0] + 4, max(peak[1] - 3, 0):peak[1] + 4] = -np.inf
    ratio = float(top / max(masked.max(), 1e-12))
    sub = []
    for axis in (0, 1):
        idx = list(peak)
        if 0 < peak[axis] < corr.shape[axis] - 1:
            idx[axis] -= 1
            lo = corr[tuple(idx)]
            idx[axis] += 2
            hi = corr[tuple(idx)]
            denom = lo - 2 * top + hi
            sub.append(0.5 * (lo - hi) / denom if denom else 0.0)
        else:
            sub.append(0.0)
    center = np.array(corr.shape) // 2
    return np.array(peak) - center + np.array(sub), ratio


def ncc_at(a, b_full, origin, shift):
    """NCC between block a and b sampled at origin + shift (bilinear)."""
    yy, xx = np.mgrid[0:a.shape[0], 0:a.shape[1]].astype(float)
    b = ndimage.map_coordinates(b_full, [yy + origin[0] + shift[0], xx + origin[1] + shift[1]], order=1)
    a0, b0 = a - a.mean(), b - b.mean()
    return float((a0 * b0).sum() / np.sqrt((a0**2).sum() * (b0**2).sum()))


def main(work, out):
    work = Path(work)
    ct = tifffile.imread(work / "raw/sv_32.tif").astype(np.float32)
    ir = np.asarray(Image.open(work / "raw/ir_aligned.png")).astype(np.float32)
    mask = np.asarray(Image.open(work / "raw/mask.png")) > 0
    assert ct.shape == ir.shape == mask.shape == (9791, 6064)
    full_shape = ct.shape
    crop = lambda a: a[:a.shape[0] // SCALE * SCALE, :a.shape[1] // SCALE * SCALE]  # noqa: E731
    down = lambda a: crop(a).reshape(a.shape[0] // SCALE, SCALE, a.shape[1] // SCALE, SCALE).mean((1, 3))  # noqa: E731
    meshed_full = ct > 0
    ct = np.where(down(meshed_full) == 1, down(ct), 0).astype(np.float32)
    ir = down(ir).astype(np.float32)
    mask = down(mask) == 1
    outline = outline_distances(ct, ir)
    print("outline", outline["symmetric"], file=sys.stderr, flush=True)
    g_ct, g_ir = gradient(ct, ct > 0), gradient(ir, np.ones_like(mask))
    inner = ndimage.binary_erosion(mask, iterations=MAX_SHIFT + 16)
    blocks = []
    for i, y in enumerate(range(0, ct.shape[0] - BLOCK, STEP)):
        for j, x in enumerate(range(0, ct.shape[1] - BLOCK, STEP)):
            if not inner[y:y + BLOCK, x:x + BLOCK].all():
                continue
            a, b = g_ct[y:y + BLOCK, x:x + BLOCK], g_ir[y:y + BLOCK, x:x + BLOCK]
            shift, ratio = phase_shift(a, b)
            ncc = ncc_at(a, g_ir, (y, x), shift) if np.abs(shift).max() < MAX_SHIFT else float("nan")
            ok = bool(np.isfinite(ncc) and ncc >= ACCEPT["min_ncc"] and ratio >= ACCEPT["min_peak_ratio"])
            blocks.append({"ij": [i, j], "yx": [y, x], "shift_yx_px": shift.tolist(), "peak_ratio": ratio,
                           "ncc_at_shift": ncc, "ncc_at_zero": ncc_at(a, g_ir, (y, x), (0, 0)),
                           "accepted": ok})
    acc = [b for b in blocks if b["accepted"]]
    d = np.array([b["shift_yx_px"] for b in acc]) if acc else np.zeros((0, 2))
    norms = np.linalg.norm(d, axis=1)
    identity = {"blocks_total": len(blocks), "blocks_accepted": len(acc),
                "coverage_fraction_of_inner_blocks": len(acc) / max(len(blocks), 1)}
    if acc:
        identity.update({"median_px": float(np.median(norms)), "rms_px": float(np.sqrt(np.mean(norms**2))),
                         "p90_px": float(np.quantile(norms, .9)), "mean_shift_yx_px": d.mean(0).tolist(),
                         "median_um": float(np.median(norms)) * PITCH_UM * SCALE,
                         "rms_um": float(np.sqrt(np.mean(norms**2))) * PITCH_UM * SCALE,
                         "pixel_um": PITCH_UM * SCALE})
    grid = Grid(tuple(int(n) for n in ct.shape), (PITCH_UM * SCALE, PITCH_UM * SCALE))
    rows = [{"id": f"B{b['ij'][0]:02d}_{b['ij'][1]:02d}",
             "split": "fit" if sum(b["ij"]) % 2 == 0 else "check",
             "feature": "gradient-magnitude block, phase correlation",
             "optical_yx": [b["yx"][0] + BLOCK / 2 + b["shift_yx_px"][0], b["yx"][1] + BLOCK / 2 + b["shift_yx_px"][1]],
             "ct_vu": [b["yx"][0] + BLOCK / 2, b["yx"][1] + BLOCK / 2]} for b in acc]
    fits = {}
    for kind in ("rigid", "affine"):
        try:
            audit = landmarks_fit(rows, grid, grid, feature_um=FEATURE_UM, kind=kind, parity=1)
            fits[kind] = {k: audit[k] for k in ("check_rms_um", "check_median_um", "check_p90_um",
                                                "check_rms_ct_px", "check_median_ct_px", "limit_um",
                                                "fit_hull_coverage", "check_hull_coverage",
                                                "check_within_fit_hull", "quality_gate",
                                                "ct_from_optical_um", "linear_singular_values")}
        except ValueError as error:
            fits[kind] = {"error": str(error)}
    result = {"inputs": {n: hashlib.sha256((work / "raw" / n).read_bytes()).hexdigest()
                         for n in ("sv_32.tif", "ir_aligned.png", "mask.png")},
              "blind": "ink labels and predictions not read",
              "pitch_um": PITCH_UM, "scale": SCALE, "full_shape": list(full_shape), "block": BLOCK, "accept_rule": ACCEPT, "feature_um": FEATURE_UM,
              "outline": outline, "identity_residual": identity, "correction_fits": fits,
              "blocks": blocks}
    Path(out).write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps({"outline": outline["symmetric"], "iou": outline["support_iou"],
                      "identity": identity,
                      "fits": {k: {kk: v.get(kk) for kk in ("check_rms_ct_px", "check_median_ct_px",
                                                           "quality_gate", "error")}
                               for k, v in fits.items()}}, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:3])
