"""Phase 11, decision 2: CT-only intensity window for Frag4, frozen before any ink label is read.

Air level = median of layers 52..64 (outside the papyrus, along +n); window top = 99.9th percentile
of layers 11..32 (papyrus side of the depth range A sees). Samples: 128 x 128 px centred on the
8 frozen geometric patches of phase11_geometry.select_patches, inside the support mask.
Mapping (uint16 v -> uint8): round(200 * clip((v - air) / (top - air), 0, 1)), so that the
inference rule clip 200 / 200 sends air to 0 and the window top to 1.

W1 (above) was frozen first; it clips the papyrus darker than air (a large share in this DLS
volume) and gives a papyrus mean of 0.17 against 0.38 in the recipe. W2, decided after seeing W1's
statistics (never labels or scores), is primary: a linear map matching the mean and standard
deviation of layers 11..53 (A's whole depth range) to the verified PHerc0500P2 reference tile
(0.379 and 0.148 after clip 200 / 200).

    python docs/validation/phase11_window.py data/phase11 docs/validation/phase11-window.json
"""

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from phase11_geometry import PATCH, Ranges, select_patches  # noqa: E402

SIDE = 128
AIR_LAYERS = tuple(range(52, 65, 4))
PAPYRUS_LAYERS = tuple(range(11, 33, 3))
DEPTH_LAYERS = tuple(range(11, 54, 3))
TOP_PERCENTILE = 99.9
TARGET_MEAN, TARGET_STD = 0.379 * 200, 0.148 * 200  # phase 6 tile ct-v512-u512, in uint8 units


def moments_u8(volume, mean, std):
    """W2: uint16 -> uint8 with the recipe's mean and standard deviation (before clip 200)."""
    scaled = (np.asarray(volume, np.float64) - mean) / std * TARGET_STD + TARGET_MEAN
    return np.round(np.clip(scaled, 0, 255)).astype(np.uint8)


def window_u8(volume, air, top):
    """uint16 -> uint8 so that air maps to 0 and ``top`` to 200 (the inference clip)."""
    scaled = (np.asarray(volume, np.float64) - air) / (top - air)
    return np.round(200 * np.clip(scaled, 0, 1)).astype(np.uint8)


def main(work, out):
    work = Path(work)
    mask = np.asarray(Image.open(work / "raw/mask.png")) > 0
    ranges = Ranges()
    air, papyrus, depth, patches = [], [], [], []
    for r, c in select_patches(mask[::8, ::8]):
        r0, c0 = r + PATCH // 2 - SIDE // 2, c + PATCH // 2 - SIDE // 2
        inside = mask[r0:r0 + SIDE, c0:c0 + SIDE]
        patches.append([r0, c0])
        air += [ranges.layer(k, r0, c0, SIDE, SIDE)[inside] for k in AIR_LAYERS]
        papyrus += [ranges.layer(k, r0, c0, SIDE, SIDE)[inside] for k in PAPYRUS_LAYERS]
        depth += [ranges.layer(k, r0, c0, SIDE, SIDE)[inside] for k in DEPTH_LAYERS]
        print("patch", r0, c0, file=sys.stderr, flush=True)
    air_values, papyrus_values = np.concatenate(air), np.concatenate(papyrus)
    level = float(np.median(air_values))
    top = float(np.percentile(papyrus_values, TOP_PERCENTILE))
    mapped = window_u8(papyrus_values, level, top)
    depth_values = np.concatenate(depth).astype(np.float64)
    mean, std = float(depth_values.mean()), float(depth_values.std())
    w2 = np.minimum(moments_u8(depth_values, mean, std), 200) / 200
    result = {"blind": "CT only; ink labels and predictions not read", "patch_origins_rc": patches,
              "side": SIDE, "air_layers": AIR_LAYERS, "papyrus_layers": PAPYRUS_LAYERS,
              "air_level_u16": level, "air_iqr_u16": np.percentile(air_values, [25, 75]).tolist(),
              "top_percentile": TOP_PERCENTILE, "top_u16": top,
              "papyrus_after_window_mean_over_200": float(mapped.mean() / 200),
              "papyrus_after_shift8_mean_over_200": float(np.minimum(papyrus_values >> 8, 200).mean() / 200),
              "w1_papyrus_clipped_to_zero": float((papyrus_values <= level).mean()),
              "w2_depth_layers": DEPTH_LAYERS, "w2_mean_u16": mean, "w2_std_u16": std,
              "w2_target_mean_std_over_200": [TARGET_MEAN / 200, TARGET_STD / 200],
              "w2_after_mean_std_over_200": [float(w2.mean()), float(w2.std())],
              "w2_saturated_fraction": float((w2 >= 1).mean()),
              "w2_zero_fraction": float((w2 <= 0).mean()), "primary": "W2",
              "rule": __doc__.split("Mapping")[1].split("\n\n    python")[0].strip()}
    Path(out).write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:3])
