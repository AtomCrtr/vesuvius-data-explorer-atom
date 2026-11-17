"""Feasibility (T5.1 spec): mean intensity profile along segment normals, on a few patches.

Usage: python T5.1_profil_normales.py SEGMENT_URI VOLUME_URI LEVEL N_PATCHES SHIFT|random
Environment: D = half range of offsets in level-0 voxels (default 24).

SHIFT moves every point by SHIFT voxels along its normal (synthetic misalignment); "random"
moves each patch by its own random shift in [-30, 30] (incoherent control).
"""

import json
import os
import sys
import time

import numpy as np
from scipy import ndimage

from vesuvius_data_explorer.core.tifxyz import load_tifxyz
from vesuvius_data_explorer.core.volume import open_multiscale

seg_uri, vol_uri, level, n_patches, shift_arg = sys.argv[1:6]
level, n_patches = int(level), int(n_patches)
random_shift = shift_arg == "random"
shift = 0.0 if random_shift else float(shift_arg)
P, D = 6, int(os.environ.get("D", "24"))  # patch of P x P grid points, offsets -D..D
started = time.time()
surface = load_tifxyz(seg_uri)
arrays, levels = open_multiscale(vol_uri)
array = arrays[level]
factor = np.array(levels[0].shape) / np.array(levels[level].shape)
points = surface.points
valid = np.isfinite(points).all(2)
normals = np.cross(np.gradient(points, axis=1), np.gradient(points, axis=0))
normals /= np.linalg.norm(normals, axis=2, keepdims=True)
usable = valid & np.isfinite(normals).all(2)
rng = np.random.default_rng(0)
candidates = [(r, c) for r in range(0, points.shape[0] - P, P)
              for c in range(0, points.shape[1] - P, P) if usable[r:r + P, c:c + P].all()]
chosen = rng.choice(len(candidates), size=min(n_patches, len(candidates)), replace=False)
offsets = np.arange(-D, D + 1, 1.0)
profiles, voxels_read = [], 0
for r, c in (candidates[i] for i in chosen):
    p = points[r:r + P, c:c + P].reshape(-1, 3)
    n = normals[r:r + P, c:c + P].reshape(-1, 3)
    p = p + (rng.uniform(-30, 30) if random_shift else shift) * n
    samples = (p[:, None, :] + offsets[None, :, None] * n[:, None, :]) / factor
    flat = samples.reshape(-1, 3)
    low = np.maximum(np.floor(flat.min(0)).astype(int) - 1, 0)
    high = np.minimum(np.ceil(flat.max(0)).astype(int) + 2, levels[level].shape)
    box = np.asarray(array[low[0]:high[0], low[1]:high[1], low[2]:high[2]].compute(), np.float32)
    voxels_read += box.size
    values = ndimage.map_coordinates(box, (flat - low).T, order=1, mode="nearest")
    profiles.append(values.reshape(len(p), len(offsets)))
mean = np.concatenate(profiles).mean(0)
gradient = np.gradient(mean, offsets)
edge = int(np.argmax(np.abs(gradient)))
bootstrap = []
for _ in range(200):
    sample = rng.integers(len(profiles), size=len(profiles))
    resampled = np.concatenate([profiles[i] for i in sample]).mean(0)
    bootstrap.append(offsets[np.argmax(np.abs(np.gradient(resampled, offsets)))])
bootstrap = np.array(bootstrap)
noise = np.std(gradient[np.abs(offsets) > D / 2])
print(json.dumps({
    "level": level, "shift": shift_arg, "patches": len(profiles),
    "seconds": round(time.time() - started, 1), "voxels_read": int(voxels_read),
    "mean_profile_every_4": [round(float(v), 1) for v in mean[::4]],
    # Brightest sheet near the surface: the profile repeats with the next sheets further away.
    "peak_offset": float(offsets[np.abs(offsets) <= D / 2][np.argmax(mean[np.abs(offsets) <= D / 2])]),
    "edge_offset": float(offsets[edge]),
    "contrast": round(float(np.abs(gradient[edge]) / noise), 2),
    "bootstrap_within_2": float(np.mean(np.abs(bootstrap - offsets[edge]) <= 2)),
}))
