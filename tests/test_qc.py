"""QC contracts: defects, bounded sampling, safe reports and CLI behavior."""
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import jsonschema
import numpy as np
import pytest
import zarr

from vesuvius_data_explorer.core.demo import demo_surface
from vesuvius_data_explorer.core.volume import Level
from vesuvius_data_explorer.qc import run_surface, run_volume
from vesuvius_data_explorer.qc.checks import REGISTRY, run_checks
from vesuvius_data_explorer.qc.model import CheckResult, Location
from vesuvius_data_explorer.qc.report import render_html, validate_report
from vesuvius_data_explorer.qc.thresholds import load_thresholds


@pytest.fixture
def clean_volume(tmp_path):
    root = zarr.open_group(str(tmp_path / 'clean.zarr'), mode='w')
    datasets = []
    for index, side in enumerate((128, 64, 32)):
        data = np.random.default_rng(index).integers(20, 220, (side,) * 3, dtype='uint8')
        root.create_array(str(index), shape=data.shape, dtype=data.dtype, chunks=(32,) * 3)
        root[str(index)][:] = data
        datasets.append({'path': str(index), 'coordinateTransformations': [
            {'type': 'scale', 'scale': [2**index] * 3}]})
    root.attrs['multiscales'] = [{'axes': ['z', 'y', 'x'], 'datasets': datasets}]
    return root


def checked(report):
    schema = json.loads((Path(__file__).parents[1] / 'src/vesuvius_data_explorer/qc/report.schema.json').read_text())
    jsonschema.Draft202012Validator(schema).validate(report)
    json.dumps(report, allow_nan=False)
    validate_report(report)
    return {r['check_id']: r for r in report['results']}


def test_clean_volume_reports_pass_and_deterministic_budget(clean_volume):
    first = run_volume(clean_volume, uri='synthetic', samples=4, max_voxels=2048)
    results = checked(first)
    assert {r['status'] for r in results.values()} == {'pass'}
    assert first['target']['level'] == '2'
    assert first['budget']['voxels_read'] == 2048
    assert first['parameters']['samples_actual'] == 2
    second = run_volume(clean_volume, uri='synthetic', samples=4, max_voxels=2048)
    checked(second)
    for item in (first, second):
        item.pop('created_at')
        item.pop('duration_s')
    assert first == second


@pytest.mark.parametrize('defect,check_id', [
    ('nan', 'volume.finite'), ('saturated', 'volume.saturation'),
    ('constant', 'volume.empty'), ('low_contrast', 'volume.low_contrast'),
])
def test_sample_defects_are_localized(clean_volume, defect, check_id):
    if defect == 'nan':
        del clean_volume['2']
        data = np.random.default_rng(2).integers(20, 220, (32,) * 3).astype('float32')
        data[27, :16, :16] = np.nan
        clean_volume.create_array('2', shape=data.shape, dtype=data.dtype, chunks=(32,) * 3)
        clean_volume['2'][:] = data
    else:
        if defect == 'saturated':
            clean_volume['2'][27, :16, :16] = 255
        elif defect == 'constant':
            clean_volume['2'][27, :, :] = 40
        else:
            clean_volume['2'][27, :, :] = 100 + np.indices((32, 32)).sum(axis=0) % 2
    report = run_volume(clean_volume, uri='defect', samples=1)
    result = checked(report)[check_id]
    assert result['status'] == 'fail'
    assert result['locations'][0]['level'] == '2'
    assert result['locations'][0]['axis'] == 'z'
    assert result['locations'][0]['index'] == 27
    assert result['locations'][0]['size'] == [32, 32]
    if defect == 'low_contrast':
        assert checked(report)['volume.empty']['status'] == 'pass'
    if defect == 'nan':
        assert checked(report)['volume.saturation']['status'] == 'skipped'
        assert checked(report)['volume.low_contrast']['status'] == 'skipped'


@pytest.mark.parametrize('field,check_id,value', [
    ('dtype', 'volume.levels.dtype', 'uint16'),
    ('shape', 'volume.levels.shape_ratio', (32, 50, 32)),
    ('scale', 'volume.levels.scale_consistency', (9., 4., 4.)),
    ('chunks', 'volume.chunks.size', (1, 1, 1)),
])
def test_metadata_defects_have_locations_without_data_reads(field, check_id, value):
    levels = [Level('0', (128,) * 3, 'uint8', (32,) * 3),
              Level('1', (64,) * 3, 'uint8', (32,) * 3, (2.,) * 3),
              Level('2', (32,) * 3, 'uint8', (32,) * 3, (4.,) * 3)]
    levels[2] = replace(levels[2], **{field: value})
    results = run_checks('metadata', {'levels': tuple(levels)}, load_thresholds())
    result = {r.check_id: r for r in results}[check_id]
    assert result.status in ('warn', 'fail')
    assert result.locations[0].level == '2'


def test_zero_budget_reads_no_voxels(clean_volume):
    report = run_volume(clean_volume, uri='synthetic', samples=100, max_voxels=0)
    results = checked(report)
    assert report['budget']['voxels_read'] == 0
    assert results['volume.finite']['status'] == 'skipped'
    assert report['parameters']['samples_actual'] == 0


def test_surface_hole_and_flipped_region(tmp_path):
    # The default size180 has only0.93% missing; size75 contains5.33% missing.
    coords = demo_surface(size=75)
    for name, data in zip('xyz', coords):
        np.save(tmp_path / f'{name}.npy', data)
    report = run_surface(tmp_path, window=75)
    assert checked(report)['surface.valid']['status'] == 'warn'
    assert report['budget']['voxels_read'] == 75 * 75 * 3
    y, x = np.mgrid[:64, :64].astype(float)
    x[:, 48:] = 96 - x[:, 48:]
    for name, data in zip('xyz', (x, y, np.zeros_like(x))):
        np.save(tmp_path / f'{name}.npy', data)
    result = checked(run_surface(tmp_path, window=64))['surface.normal_flips']
    assert result['status'] == 'fail'
    assert result['locations']


def test_error_isolation_and_frozen_results(monkeypatch):
    def broken(context, thresholds):
        raise RuntimeError('injected')
    monkeypatch.setitem(REGISTRY, 'metadata', (('broken', broken), ('fine', lambda c, t: CheckResult('fine', 'pass', 0, {}, 'OK'))))
    results = run_checks('metadata', {}, load_thresholds())
    assert [r.status for r in results] == ['error', 'pass']
    with pytest.raises(FrozenInstanceError):
        results[0].status = 'pass'
    result = CheckResult('x', 'pass', 0, {'warn': 1}, 'ok', (Location('0', 'z', 0, (0, 0), (2, 2)),))
    with pytest.raises(TypeError):
        result.threshold['warn'] = 9


def test_threshold_config_safe_validation(tmp_path):
    config = tmp_path / 'thresholds.toml'
    config.write_text('["volume.saturation"]\nwarn = 0.5\nfail = 2.0\n')
    assert load_thresholds(config)['volume.saturation']['fail'] == 2
    for text in ('[unknown]\nwarn=1', '["volume.saturation"]\nwarn=nan',
                 '["volume.saturation"]\nwarn=6\nfail=2', '["surface.valid"]\nwarn=true', '["volume.finite"]\nwarn=' + '9' * 400):
        config.write_text(text)
        with pytest.raises(ValueError):
            load_thresholds(config)


def test_html_escapes_input_and_report_rejects_nonfinite(clean_volume):
    report = run_volume(clean_volume, uri='<script>alert(1)</script>', samples=1)
    checked(report)
    html = render_html(report)
    assert '&lt;script&gt;' in html
    assert '<script>' not in html
    assert 'https://' not in html and 'src=' not in html
    report['duration_s'] = float('nan')
    with pytest.raises(ValueError):
        validate_report(report)


def test_cli_exit_codes_threshold_override_and_outputs(clean_volume, tmp_path, capsys):
    from vesuvius_data_explorer.cli import main
    uri = str(clean_volume.store.root)
    assert main(['volume', uri, '--samples', '1']) == 0
    checked(json.loads(capsys.readouterr().out))
    clean_volume['2'][:] = 255
    output, html = tmp_path / 'report.json', tmp_path / 'report.html'
    assert main(['volume', uri, '--samples', '1', '-o', str(output), '--html', str(html)]) == 1
    checked(json.loads(output.read_text()))
    assert html.is_file()
    config = tmp_path / 'thresholds.toml'
    config.write_text('["volume.saturation"]\nwarn=100\nfail=100\n["volume.empty"]\nwarn=100\nfail=100\n["volume.low_contrast"]\nwarn=100\nfail=100\n')
    assert main(['volume', uri, '--samples', '1', '--config', str(config)]) == 0
    checked(json.loads(capsys.readouterr().out))
    for arguments in (['volume', '/no/such/path'], ['volume', 'https://example.org'],
                      ['volume', uri, '--samples', '-1'], ['volume', uri, '--level', 'missing']):
        assert main(arguments) == 2


def test_instrumented_array_proves_materialization_bound_and_no_implicit_full_read():
    class Array:
        shape = (100, 64, 64)
        dtype = np.dtype('uint8')
        chunks = (32, 32, 32)

        def __init__(self):
            self.requests = []

        def __array__(self, *args, **kwargs):
            raise AssertionError('Full volume materialization forbidden')

        def __getitem__(self, selection):
            assert isinstance(selection[0], int)
            assert selection[1:] == (slice(0, 64), slice(0, 64))
            self.requests.append(selection)
            return np.arange(4096, dtype='uint8').reshape(64, 64)

    array = Array()
    zero = run_volume(array, uri='instrumented', samples=100, max_voxels=4095)
    checked(zero)
    assert array.requests == []
    bounded = run_volume(array, uri='instrumented', samples=100, max_voxels=8193)
    checked(bounded)
    assert len(array.requests) == 2
    assert bounded['budget']['voxels_read'] == 8192
    assert bounded['budget']['chunks_touched'] is None


def test_zarr_counts_actual_store_chunk_gets_and_metadata_reads_none(clean_volume):
    zero = run_volume(clean_volume, uri='synthetic', samples=0)
    checked(zero)
    assert zero['budget']['chunks_touched'] == 0
    report = run_volume(clean_volume, uri='synthetic', samples=1)
    checked(report)
    # The selected32³ level is one stored chunk, despite1024 returned voxels.
    assert report['budget']['chunks_touched'] == 1
    assert report['budget']['store_objects_touched'] == 1
    assert report['budget']['voxels_read'] == 1024


def test_shards_are_not_misreported_as_logical_chunks(tmp_path):
    array = zarr.create_array(str(tmp_path / 'sharded.zarr'), shape=(16, 32, 32),
                            chunks=(8, 16, 16), shards=(16, 32, 32), dtype='uint8')
    array[:] = 127
    report = run_volume(array, uri='sharded', samples=1)
    checked(report)
    assert report['budget']['chunks_touched'] is None
    assert report['budget']['store_objects_touched'] == 1


def test_surface_budget_and_degenerate_metrics_are_json_safe(tmp_path):
    for name in 'xyz':
        np.save(tmp_path / f'{name}.npy', np.full((64, 64), np.nan))
    report = run_surface(tmp_path, window=64, max_voxels=3 * 16 * 16)
    results = checked(report)
    assert report['budget']['voxels_read'] == 768
    assert results['surface.valid']['status'] == 'fail'
    assert results['surface.stretch']['status'] == 'skipped'
    assert results['surface.normal_flips']['status'] == 'skipped'


@pytest.mark.parametrize('values', [
    {'duration_s': -1}, {'unknown': 1}, {'schema_version': '2.0'},
    {'summary': {'pass': 0}}, {'results': [{'check_id': 'incomplete'}]},
])
def test_runtime_validation_rejects_invalid_reports(clean_volume, values):
    report = run_volume(clean_volume, uri='synthetic', samples=0)
    checked(report)
    report.update(values)
    with pytest.raises(ValueError):
        validate_report(report)


def test_cli_rejects_non_3d_and_bad_config(tmp_path, capsys):
    from vesuvius_data_explorer.cli import main
    array = zarr.open_array(str(tmp_path / '2d.zarr'), mode='w', shape=(8, 8), dtype='uint8')
    assert main(['volume', str(array.store.root)]) == 2
    config = tmp_path / 'bad.toml'
    config.write_text('broken[')
    assert main(['surface', str(tmp_path), '--config', str(config)]) == 2
    assert not capsys.readouterr().out


@pytest.mark.network
def test_qc_real_volume_optional(tmp_path):
    import os

    from vesuvius_data_explorer.cli import main
    uri = os.environ.get('VESUVIUS_TEST_ZARR')
    if not uri:
        pytest.skip('VESUVIUS_TEST_ZARR is not set')
    output = tmp_path / 'real-report.json'
    status = main(['volume', uri, '--samples', '1', '--max-voxels', '65536', '-o', str(output)])
    assert status in (0, 1)
    checked(json.loads(output.read_text()))


def test_committed_synthetic_example_is_schema_valid():
    examples = Path(__file__).parents[1] / 'docs/examples'
    report = json.loads((examples / 'qc-synthetic.json').read_text())
    checked(report)
    assert report['summary'] == {'pass': 10, 'warn': 0, 'fail': 0, 'error': 0, 'skipped': 0}
    assert report['budget']['voxels_read'] == 2048


def test_installed_console_script_emits_only_json_on_stdout(clean_volume):
    import subprocess
    import sys

    result = subprocess.run([str(Path(sys.executable).parent / 'vesuvius-qc'), 'volume',
                             str(clean_volume.store.root), '--samples', '1'],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    checked(json.loads(result.stdout))
    assert 'physique' in result.stderr


def test_large_integer_budget_remains_a_valid_json_integer(clean_volume):
    report = run_volume(clean_volume, uri='synthetic', samples=1, max_voxels=10**400)
    checked(report)
    assert report['budget']['voxels_read'] == 1024


def test_cli_truncated_surface_coordinate_is_input_error(tmp_path, capsys):
    from vesuvius_data_explorer.cli import main

    (tmp_path / 'x.npy').touch()
    assert main(['surface', str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ''
    assert 'vesuvius-qc' in captured.err


def test_cli_corrupt_compressed_chunk_is_input_error(tmp_path, capsys):
    from vesuvius_data_explorer.cli import main

    folder = tmp_path / 'corrupt.zarr'
    zarr.create_array(str(folder), data=np.full((32,) * 3, 127, dtype='uint8'),
                      chunks=(32,) * 3, zarr_format=3)
    (folder / 'c/0/0/0').write_bytes(b'corrupt')
    assert main(['volume', str(folder), '--samples', '1']) == 2
    captured = capsys.readouterr()
    assert captured.out == ''
    assert 'vesuvius-qc' in captured.err


@pytest.fixture
def masked_volume(tmp_path):
    """Healthy masked scan: a scroll disc (60–200) on a background of zeros, no saturation."""
    root = zarr.open_group(str(tmp_path / 'masked.zarr'), mode='w')
    datasets = []
    for index, side in enumerate((128, 64, 32)):
        rng = np.random.default_rng(index)
        _, y, x = np.ogrid[:side, :side, :side]
        inside = (y - side / 2) ** 2 + (x - side / 2) ** 2 < (0.35 * side) ** 2
        data = np.where(inside, rng.integers(60, 200, (side,) * 3), 0).astype('uint8')
        root.create_array(str(index), shape=data.shape, dtype=data.dtype, chunks=(32,) * 3)
        root[str(index)][:] = data
        datasets.append({'path': str(index), 'coordinateTransformations': [
            {'type': 'scale', 'scale': [2**index] * 3}]})
    root.attrs['multiscales'] = [{'axes': ['z', 'y', 'x'], 'datasets': datasets}]
    return root


def test_masked_background_is_reported_not_failed(masked_volume):
    results = checked(run_volume(masked_volume, uri='masked', level='0', samples=16))
    assert {r['status'] for r in results.values()} == {'pass'}
    assert results['volume.background']['value'] > 20


def test_real_saturation_inside_masked_volume_still_fails(masked_volume):
    masked_volume['0'][:, 40:88, 40:88] = 255
    results = checked(run_volume(masked_volume, uri='masked', level='0', samples=16))
    assert results['volume.saturation']['status'] == 'fail'
    assert results['volume.saturation']['locations']


def test_background_rois_are_ignored_not_counted_empty(masked_volume):
    masked_volume['2'][:] = 0
    results = checked(run_volume(masked_volume, uri='masked', samples=4))
    for check_id in ('volume.saturation', 'volume.empty', 'volume.low_contrast'):
        assert results[check_id]['status'] == 'skipped'
        assert 'fond ignorée' in results[check_id]['message']
    assert results['volume.background']['value'] == 100


def test_background_exclusion_can_be_disabled(masked_volume, tmp_path):
    config = tmp_path / 'no-background.toml'
    config.write_text('["volume.background"]\nenabled = 0\n')
    results = checked(run_volume(masked_volume, uri='masked', level='0', samples=16,
                                 thresholds=load_thresholds(config)))
    assert results['volume.background']['status'] == 'skipped'
    assert results['volume.saturation']['status'] == 'fail'


def test_background_threshold_validation(tmp_path):
    config = tmp_path / 'background.toml'
    config.write_text('["volume.background"]\nvalue = -1000\n')
    assert load_thresholds(config)['volume.background']['value'] == -1000
    config.write_text('["volume.background"]\nenabled = 2\n')
    with pytest.raises(ValueError):
        load_thresholds(config)


def test_unit_fallback_scales_skip_scale_consistency(tmp_path):
    root = zarr.open_group(str(tmp_path / 'nometa.zarr'), mode='w')
    for index, side in enumerate((64, 32, 16)):
        root.create_array(str(index), shape=(side,) * 3, dtype='uint8', chunks=(16,) * 3)
        root[str(index)][:] = np.random.default_rng(index).integers(20, 220, (side,) * 3)
    with pytest.warns(UserWarning, match='échelles unitaires'):
        results = checked(run_volume(root, uri='nometa', samples=2))
    assert results['volume.levels.scale_consistency']['status'] == 'skipped'
    assert results['volume.levels.shape_ratio']['status'] == 'pass'
