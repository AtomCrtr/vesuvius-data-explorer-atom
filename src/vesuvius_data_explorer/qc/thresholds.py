"""Provisional heuristics; all numeric QC decision thresholds live here."""
import math
import tomllib
from types import MappingProxyType

_DEFAULTS = {
    'volume.levels.shape_ratio': {'tolerance_voxels': 1.0},
    'volume.levels.scale_consistency': {'relative_tolerance': 0.05},
    'volume.chunks.size': {'min_bytes': 32768.0, 'max_bytes': 67108864.0},
    'volume.finite': {'warn': 0.0, 'fail': 1.0},
    'volume.saturation': {'warn': 1.0, 'fail': 5.0},
    'volume.empty': {'warn': 10.0, 'fail': 50.0},
    'volume.low_contrast': {'warn': 25.0, 'fail': 75.0, 'range_fraction': 0.01},
    'surface.valid': {'warn': 95.0, 'fail': 80.0},
    'surface.stretch': {'warn': 2.0, 'fail': 4.0},
    'surface.normal_flips': {'warn': 1.0, 'fail': 5.0},
}


def load_thresholds(path=None):
    values = {key: dict(value) for key, value in _DEFAULTS.items()}
    if path is not None:
        with open(path, 'rb') as stream:
            overrides = tomllib.load(stream)
        for check_id, thresholds in overrides.items():
            if check_id not in values or not isinstance(thresholds, dict):
                raise ValueError(f'Contrôle inconnu : {check_id}')
            for name, value in thresholds.items():
                if name not in values[check_id] or isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f'Seuil inconnu ou non numérique : {check_id}.{name}')
                try:
                    value = float(value)
                except OverflowError as exc:
                    raise ValueError('Seuil numérique trop grand.') from exc
                if not math.isfinite(value) or value < 0:
                    raise ValueError('Les seuils doivent être finis et positifs ou nuls.')
                values[check_id][name] = float(value)
    for check_id, threshold in values.items():
        if 'warn' in threshold:
            lower = check_id == 'surface.valid'
            if (threshold['warn'] < threshold['fail']) == lower and threshold['warn'] != threshold['fail']:
                raise ValueError(f'Ordre des seuils invalide : {check_id}')
            if check_id != 'surface.stretch' and max(threshold['warn'], threshold['fail']) > 100:
                raise ValueError('Un pourcentage ne peut dépasser 100.')
        if 'min_bytes' in threshold and not 0 < threshold['min_bytes'] <= threshold['max_bytes']:
            raise ValueError('Bornes de chunk invalides.')
        for name in ('relative_tolerance', 'range_fraction'):
            if name in threshold and threshold[name] > 1:
                raise ValueError('Une fraction doit rester entre 0 et 1.')
    return MappingProxyType({key: MappingProxyType(value) for key, value in values.items()})
