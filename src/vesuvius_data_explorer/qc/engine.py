"""Deterministic bounded acquisition followed by pure registered checks."""
from datetime import datetime, timezone
from importlib.metadata import version
from math import isqrt, prod
from time import perf_counter

import numpy as np

from ..core.surface import load_surface_patch, surface_metrics
from ..core.volume import get_array, list_levels, read_slice
from .checks import run_checks
from .model import STATUSES, Location
from .report import validate_report
from .thresholds import load_thresholds


def _report(kind, uri, level, parameters, budget, results, started):
    report = {
        'schema_version': '1.0',
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


def run_surface(folder, *, window=256, max_voxels=16777216, thresholds=None):
    started = perf_counter()
    if not isinstance(window, int) or isinstance(window, bool) or not 8 <= window <= 512:
        raise ValueError('Fenêtre autorisée : 8 à 512 pixels.')
    if not isinstance(max_voxels, int) or isinstance(max_voxels, bool) or max_voxels < 0:
        raise ValueError('Budget invalide.')
    actual_window = min(window, isqrt(max_voxels // 3))
    if actual_window < 8:
        raise ValueError('Budget insuffisant pour trois grilles de 8×8 coordonnées.')
    thresholds = thresholds if thresholds is not None else load_thresholds()
    coords = load_surface_patch(folder, limit=actual_window)
    location = Location('surface', 'z', 0, (0, 0), coords[0].shape)
    metrics = surface_metrics(*coords)
    results = run_checks('surface', {'metrics': metrics, 'location': location}, thresholds)
    warnings = ['Localisation surface : fenêtre de grille (ligne, colonne), niveau surface ; '
                'aucune transformation implicite vers les coordonnées physiques CT.']
    if actual_window != window:
        warnings.append(f'Budget : fenêtre réduite de {window} à {actual_window}.')
    budget = {'voxels_read': sum(prod(coord.shape) for coord in coords), 'chunks_touched': None,
              'store_objects_touched': None,
              'physical_io_note': 'Trois grilles mappées en mémoire ; compte des coordonnées '
                                  'matérialisées, pas des pages disque du système.'}
    parameters = _parameters(thresholds, samples=1, samples_actual=1, seed=0,
                             max_voxels=max_voxels, roi_width=actual_window, warnings=warnings)
    return _report('surface', folder, 'surface', parameters, budget, results, started)
