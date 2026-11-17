"""Generate synthetic example reports: python docs/examples/generate_qc_example.py."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import zarr

from vesuvius_data_explorer.qc import run_volume
from vesuvius_data_explorer.qc.report import render_html


def main():
    with TemporaryDirectory() as folder:
        root = zarr.open_group(folder, mode='w')
        datasets = []
        for index, side in enumerate((128, 64, 32)):
            data = np.random.default_rng(index).integers(20, 220, (side,) * 3, dtype='uint8')
            root.create_array(str(index), data=data, chunks=(32,) * 3)
            datasets.append({'path': str(index), 'coordinateTransformations': [
                {'type': 'scale', 'scale': [2**index] * 3}]})
        root.attrs['multiscales'] = [{'axes': ['z', 'y', 'x'], 'datasets': datasets}]
        report = run_volume(root, uri='synthetic://clean-multiscale-example', samples=4,
                            seed=0, max_voxels=2048)
    output = Path(__file__).parent
    (output / 'qc-synthetic.json').write_text(json.dumps(report, indent=2, ensure_ascii=False,
                                                       allow_nan=False) + '\n', encoding='utf-8')
    (output / 'qc-synthetic.html').write_text(render_html(report), encoding='utf-8')


if __name__ == '__main__':
    main()
