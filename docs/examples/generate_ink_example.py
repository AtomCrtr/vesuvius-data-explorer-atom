"""Build two synthetic test windows without downloading data or running a model."""

import argparse
import shutil
from pathlib import Path

import numpy as np
import tifffile


def make_planes(rng, opened):
    y, x = np.indices((72, 104))
    radius = np.hypot(x - 44, y - 38)
    ink = (radius >= 12) & (radius <= 15)
    if opened:
        ink &= ~((x > 44) & (abs(y - 38) < 5))
    labels = ink.astype(np.uint8)
    labels[57:, 68:] = 255
    strata = np.zeros_like(labels)
    strata[8:22, 65:95] = 1
    strata[25:53, 72:94] = 2
    strata[10:58, 8:23] = 3
    strata[labels == 255] = 4
    left = rng.normal(0.18, 0.065, labels.shape)
    right = rng.normal(0.20, 0.055, labels.shape)
    left[ink] += 0.54
    right[ink] += 0.52
    left[(strata == 1) & (y % 4 == 0)] += 0.55
    right[(strata == 1) & (x % 5 == 0)] += 0.53
    shared = (strata == 2) & (abs(x - 82) < 3)
    left[shared] += 0.50
    right[shared] += 0.52
    left[(strata == 3) & (y % 6 <= 1)] += 0.60
    left[(radius < 12) & (y > 35)] += 0.34
    if opened:
        # The second reader misses part of an otherwise strong arc.
        right[ink & (x < 37) & (abs(y - 38) < 5)] -= 0.46
    ct = 124 + 19 * np.sin(y * 1.12 + x * 0.043) + rng.normal(0, 9, labels.shape)
    ct += ink * 14 + shared * 32
    return {
        'left': np.rint(np.clip(left, 0, 1) * 255).astype(np.uint8),
        'right': np.rint(np.clip(right, 0, 1) * 255).astype(np.uint8),
        'labels': labels,
        'strata': strata,
        'ct': np.rint(np.clip(ct, 0, 255)).astype(np.uint8),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    output = parser.parse_args().output
    output.mkdir(parents=True)
    rng = np.random.default_rng(211306)
    for name, opened in [('anneau', False), ('arc', True)]:
        for key, plane in make_planes(rng, opened).items():
            tifffile.imwrite(output / f'{name}-{key}.tif', plane, photometric='minisblack')
    shutil.copyfile(Path(__file__).with_name('ink_benchmark.toml'), output / 'manifest.toml')


if __name__ == '__main__':
    main()
