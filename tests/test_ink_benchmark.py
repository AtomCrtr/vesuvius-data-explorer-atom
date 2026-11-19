import json

import numpy as np
import pytest
import tifffile
from PIL import Image

from vesuvius_data_explorer.cli import main
from vesuvius_data_explorer.qc.ink import _glyph_metrics, _pixel_metrics, run_ink_benchmark


@pytest.fixture
def benchmark(tmp_path):
    labels = np.array([[1, 1, 0], [0, 0, 255]], dtype=np.uint8)
    planes = {
        'labels': labels,
        'strata': np.array([[0, 0, 1], [1, 2, 4]], dtype=np.uint8),
        'left': np.array([[210, 210, 200], [20, 210, 250]], dtype=np.uint8),
        'right': np.array([[0.9, 0.8, 0.1], [0.9, 0.8, 0.9]], dtype=np.float32),
        'ct': np.ones_like(labels),
    }
    for key, plane in planes.items():
        tifffile.imwrite(tmp_path / f'{key}.tif', plane)
    manifest = tmp_path / 'benchmark.toml'
    manifest.write_text(
        '''schema_version = 1
dataset_kind = "synthetic"
max_pixels = 6
boundary_tolerance_px = 0.0
[thresholds]
left = 0.5
right = 0.5
mean = 0.5
minimum = 0.5
product = 0.5
[models.left]
name = "left"
checkpoint = "fixture"
scale = 255
[models.right]
name = "right"
checkpoint = "fixture"
scale = 1
[[crops]]
id = "crop"
scroll = "roll"
volume = "volume"
surface = "surface"
provenance = "independently constructed fixture"
pixel_size_um = 9
left = "left.tif"
right = "right.tif"
labels = "labels.tif"
strata = "strata.tif"
ct = "ct.tif"
glyphs = { frame = [0, 0, 2, 2] }
''',
        encoding='utf-8',
    )
    return manifest, tmp_path / 'output'


def test_command_writes_reproducible_metrics_and_png(benchmark):
    manifest, output = benchmark
    assert main(['encre', str(manifest), '-o', str(output)]) == 0
    report = json.loads((output / 'rapport.json').read_text(encoding='utf-8'))
    crop = report['crops'][0]
    methods = crop['methods']
    assert report['dataset_kind'] == 'synthetic'
    assert len(crop['files']['left']['sha256']) == 64
    assert methods['left']['pixels']['fpr'] == pytest.approx(2 / 3)
    assert methods['product']['pixels'] == {
        'tp': 2, 'fp': 1, 'fn': 0, 'tn': 2, 'unlabelled': 1,
        'unlabelled_positive': 1, 'auc': pytest.approx(11 / 12),
        'precision': pytest.approx(2 / 3), 'recall': 1, 'fpr': pytest.approx(1 / 3),
    }
    assert methods['product']['strata']['blank']['fp'] == 0
    assert methods['product']['strata']['scan_artifact']['fp'] == 1
    assert methods['product']['strata']['uncertain']['fpr'] is None
    assert methods['product']['glyphs']['frame']['boundary_f1'] == 0.8
    with Image.open(output / crop['comparison']) as image:
        assert image.format == 'PNG'
        image.verify()
    assert run_ink_benchmark(manifest, output.with_name('repeat')) == report
    assert main(['encre', str(manifest), '-o', str(output)]) == 2
    assert json.loads((output / 'rapport.json').read_text(encoding='utf-8')) == report


@pytest.mark.parametrize('key, plane', [
    ('right', np.full((2, 3), np.nan)),
    ('left', np.full((2, 4), 2, dtype=np.uint8)),
    ('labels', np.full((2, 3), 2, dtype=np.uint8)),
    ('ct', np.zeros((2, 2, 3), dtype=np.uint8)),
    ('strata', np.full((2, 3), 4, dtype=np.uint8)),
])
def test_bad_input_does_not_leave_output(benchmark, key, plane):
    manifest, output = benchmark
    tifffile.imwrite(manifest.parent / f'{key}.tif', plane, photometric='minisblack')
    assert main(['encre', str(manifest), '-o', str(output)]) == 2
    assert not output.exists()


def test_ties_and_empty_denominators():
    assert _pixel_metrics(np.array([0.5, 0.5]), np.array([0, 1]), 0.5)['auc'] == 0.5
    metrics = _pixel_metrics(np.array([0.2, 0.9]), np.array([0, 255]), 0.5)
    assert metrics['recall'] is metrics['precision'] is metrics['auc'] is None
    assert metrics['fpr'] == 0
    assert metrics['unlabelled_positive'] == 1


def test_shape_checks_distinguish_filled_hole_and_missing_stroke():
    reference = np.ones((5, 5), dtype=bool)
    reference[1:-1, 1:-1] = False
    filled = _glyph_metrics(np.ones_like(reference), reference, 0)
    assert filled['boundary_f1'] == 1
    assert filled['reference'] == {'components': 1, 'holes': 1}
    assert filled['predicted'] == {'components': 1, 'holes': 0}
    assert not filled['topology_matches']
    assert _glyph_metrics(np.zeros_like(reference), reference, 0)['boundary_f1'] == 0
