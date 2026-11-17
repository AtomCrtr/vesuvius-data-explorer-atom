"""Deterministic bounded acquisition followed by pure registered checks."""
from datetime import datetime, timezone
from importlib.metadata import version
from time import perf_counter

import numpy as np

from ..core.tifxyz import DEFAULT_MAX_BYTES, load_tifxyz, tifxyz_metrics
from ..core.volume import get_array, list_levels, read_slice
from .checks import run_checks
from .model import STATUSES, Location
from .report import validate_report
from .thresholds import load_thresholds

SCHEMA_VERSION = '1.1'


def _report(kind, uri, level, parameters, budget, results, started):
    report = {
        'schema_version': SCHEMA_VERSION,
        'tool': {'name': 'vesuvius-data-explorer', 'version': version('vesuvius-data-explorer')},
        'created_at': datetime.now(timezone.utc).isoformat(),
        'duration_s': perf_counter() - started,
        'target': {'kind': kind, 'uri': str(uri), 'level': level},
        'parameters': parameters,
        'budget': budget,
        'summary': {status: sum(r.status == status for r in results) for status in STATUSES},
        'results': [result.to_dict() for result in results],
    }
    validate_report(report)
    return report


def _parameters(thresholds, **kwargs):
    return {**kwargs, 'thresholds': {key: dict(value) for key, value in thresholds.items()}}


def _instrument(array):
    """Count actual data-object get requests, never estimate from ROI geometry.

    Shards contain multiple logical chunks: their object count is exposed separately
    and chunks_touched stays null, since range reads cannot identify decoded chunks.
    """
    import zarr
    from zarr.storage import WrapperStore

    if not isinstance(array, zarr.Array):
        return array, None

    class Counter(WrapperStore):
        def __init__(self, store):
            super().__init__(store)
            self.keys = set()

        def with_read_only(self, read_only=False):
            return self._with_store(self._store.with_read_only(read_only))

        def _with_store(self, store):
            wrapper = type(self)(store)
            wrapper.keys = self.keys
            return wrapper

        def get_sync(self, key, *, prototype=None, byte_range=None):
            self.touch(key)
            return self._store.get_sync(key, prototype=prototype, byte_range=byte_range)

        async def get_ranges(self, key, byte_ranges, **kwargs):
            self.touch(key)
            async for group in self._store.get_ranges(key, byte_ranges, **kwargs):
                yield group

        def touch(self, key):
            if key.rsplit('/', 1)[-1] not in {'.zarray', '.zgroup', '.zattrs', '.zmetadata', 'zarr.json'}:
                self.keys.add(key)

        async def get(self, key, prototype, byte_range=None):
            self.touch(key)
            return await self._store.get(key, prototype, byte_range)

        async def _get_many(self, requests):
            requests = list(requests)
            for key, _, _ in requests:
                self.touch(key)
            async for item in self._store._get_many(requests):
                yield item

        async def get_partial_values(self, prototype, key_ranges):
            ranges = list(key_ranges)
            for key, _ in ranges:
                self.touch(key)
            return await self._store.get_partial_values(prototype, ranges)

    counter = Counter(array.store)
    wrapped = zarr.open_array(store=counter, path=array.path, mode='r')
    counter.keys.clear()
    return wrapped, counter


def run_volume(root, *, uri='', level=None, samples=16, seed=0, max_voxels=16777216,
               thresholds=None):
    started = perf_counter()
    if isinstance(samples, bool) or not isinstance(samples, int) or samples < 0:
        raise ValueError('Le nombre de ROI doit être un entier positif ou nul.')
    if isinstance(max_voxels, bool) or not isinstance(max_voxels, int) or max_voxels < 0:
        raise ValueError('Le budget doit être un entier positif ou nul.')
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError('La graine doit être un entier positif ou nul.')
    thresholds = thresholds if thresholds is not None else load_thresholds()
    levels = list_levels(root)
    selected = next((v for v in levels if v.key == level), None) if level is not None else levels[-1]
    if selected is None:
        raise ValueError(f'Niveau introuvable : {level}')
    if any(n < 1 for n in selected.shape):
        raise ValueError('Un niveau vide ne peut être échantillonné.')
    results = list(run_checks('metadata', {'levels': tuple(levels)}, thresholds))
    array, counter = _instrument(get_array(root, selected.key))
    width = min(256, selected.shape[1], selected.shape[2])
    count = min(samples, max_voxels // (width * width))
    rng = np.random.default_rng(seed)
    acquired = []
    voxels = 0
    for _ in range(count):
        index = int(rng.integers(selected.shape[0]))
        origin = (int(rng.integers(selected.shape[1] - width + 1)),
                  int(rng.integers(selected.shape[2] - width + 1)))
        data = read_slice(array, 'z', index, *origin, width=width)
        voxels += data.size
        acquired.append((Location(selected.key, 'z', index, origin, data.shape), data))
    results.extend(run_checks('samples', {'samples': tuple(acquired), 'dtype': selected.dtype}, thresholds))
    warnings = []
    if count < samples:
        warnings.append(f'Budget : nombre de ROI réduit de {samples} à {count}.')
    warnings.append('Le plafond concerne les voxels matérialisés des ROI ; les chunks ou shards '
                    'compressés peuvent imposer davantage de lectures/décodage physique.')
    sharded = getattr(array, 'shards', None) is not None
    objects = len(counter.keys) if counter is not None else None
    budget = {'voxels_read': voxels, 'chunks_touched': objects if not sharded else None,
              'store_objects_touched': objects, 'physical_io_note': warnings[-1]}
    parameters = _parameters(thresholds, samples=samples, samples_actual=count, seed=seed,
                             max_voxels=max_voxels, roi_width=width, warnings=warnings)
    return _report('volume', uri, selected.key, parameters, budget, results, started)


def run_surface(source, *, max_bytes=DEFAULT_MAX_BYTES, thresholds=None, volume_shape=None,
                overlap_ratio=None, window=None, max_voxels=None, surface=None):
    """QC of a tifxyz segment read within ``max_bytes`` per grid.

    ``volume_shape`` (z, y, x) enables surface.bounds; ``overlap_ratio`` is the catalogue
    coverage of that volume. ``window`` and ``max_voxels`` belong to the pre-T5 patch reader:
    accepted, ignored, and reported. ``surface`` reuses an already loaded segment.
    """
    started = perf_counter()
    thresholds = thresholds if thresholds is not None else load_thresholds()
    if surface is None:
        surface = load_tifxyz(str(source), max_bytes=max_bytes)
    metrics = tifxyz_metrics(surface, volume_shape)
    rows, cols = surface.points.shape[:2]
    location = Location('surface', 'z', 0, (0, 0), surface.grid_shape)
    context = {'metrics': metrics, 'location': location, 'overlap_ratio': overlap_ratio}
    results = run_checks('surface', context, thresholds)
    warnings = ['Localisation surface : fenêtre de grille (ligne, colonne) du fichier complet ; '
                'centre éventuel en voxels (z, y, x) du niveau 0 du volume visé.']
    warnings += list(surface.warnings)
    if surface.stride > 1:
        warnings.append('Grille décimée : les trous plus petits que le pas de lecture peuvent '
                        'échapper à surface.holes.')
    for name, value in (('window', window), ('max_voxels', max_voxels)):
        if value is not None:
            warnings.append(f'Option {name} ignorée pour une surface depuis T5 '
                            '(budget en octets par grille : max_bytes).')
    budget = {'voxels_read': 3 * rows * cols, 'chunks_touched': None,
              'store_objects_touched': None,
              'physical_io_note': f'{surface.bytes_read} octets de grilles lus (en-têtes TIFF et '
                                  'meta.json en sus) ; voxels_read compte les coordonnées '
                                  'matérialisées.'}
    parameters = _parameters(thresholds, samples=1, samples_actual=1, seed=0,
                             max_voxels=3 * (max_bytes // 4), roi_width=cols, warnings=warnings,
                             max_bytes=max_bytes, stride=surface.stride,
                             grid_shape=list(surface.grid_shape),
                             volume_shape=None if volume_shape is None else list(volume_shape),
                             overlap_ratio=overlap_ratio)
    return _report('surface', source, 'surface', parameters, budget, results, started)
