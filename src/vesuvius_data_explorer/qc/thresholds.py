"""Provisional heuristics; all numeric QC decision thresholds live here."""
import math
import tomllib
import warnings
from types import MappingProxyType

_DEFAULTS = {
    # Masked scans set everything outside the scroll to one value (0 in Vesuvius data).
    # Those voxels are background, excluded from saturation, empty and contrast checks.
    # enabled = 0 disables the exclusion; value may be any finite number.
    'volume.background': {'value': 0.0, 'enabled': 1.0},
    'volume.levels.shape_ratio': {'tolerance_voxels': 1.0},
    'volume.levels.scale_consistency': {'relative_tolerance': 0.05},
    'volume.chunks.size': {'min_bytes': 32768.0, 'max_bytes': 67108864.0},
    'volume.finite': {'warn': 0.0, 'fail': 1.0},
    'volume.saturation': {'warn': 1.0, 'fail': 5.0},
    'volume.empty': {'warn': 10.0, 'fail': 50.0},
    'volume.low_contrast': {'warn': 25.0, 'fail': 75.0, 'range_fraction': 0.01},
    # Interior holes only: invalid points on the irregular outline of a segment are normal.
    'surface.holes': {'warn': 1.0, 'fail': 5.0},
    'surface.stretch': {'warn': 2.0, 'fail': 4.0},
    # Share of adjacent cells with opposite normals (local, since T5). On 30 real segments:
    # 0 to 0.33 %; one fold across a 64 x 64 grid: 0.8 %.
    'surface.normal_flips': {'warn': 0.5, 'fail': 2.0},
    # Valid points inside the volume vs the catalogue coverage ratio, in percentage points.
    'surface.bounds': {'tolerance_points': 2.0},
    # Exploratory (T5.1): informational until calibrated and enabled by the Product Owner.
    'surface.alignment': {'enabled': 0.0, 'max_offset_voxels': 8.0, 'min_prominence': 1.0,
                          'max_bootstrap_iqr': 4.0},
}
# surface.valid is informational since T5 (irregular outlines lower it on healthy segments).
_IGNORED = {'surface.valid'}


def load_thresholds(path=None):
    values = {key: dict(value) for key, value in _DEFAULTS.items()}
    if path is not None:
        with open(path, 'rb') as stream:
            overrides = tomllib.load(stream)
        for check_id, thresholds in overrides.items():
            if check_id in _IGNORED:
                warnings.warn(f'Seuils {check_id} ignorés : ce contrôle est informatif depuis T5 '
                              '(voir surface.holes).', UserWarning, stacklevel=2)
                continue
            if check_id not in values or not isinstance(thresholds, dict):
                raise ValueError(f'Contrôle inconnu : {check_id}')
            for name, value in thresholds.items():
                if name not in values[check_id] or isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f'Seuil inconnu ou non numérique : {check_id}.{name}')
                try:
                    value = float(value)
                except OverflowError as exc:
                    raise ValueError('Seuil numérique trop grand.') from exc
                if not math.isfinite(value):
                    raise ValueError('Les seuils doivent être finis.')
                if name == 'enabled' and value not in (0, 1):
                    raise ValueError(f'{check_id}.enabled vaut 0 ou 1.')
                if value < 0 and not (check_id == 'volume.background' and name == 'value'):
                    raise ValueError('Les seuils doivent être finis et positifs ou nuls.')
                values[check_id][name] = float(value)
    for check_id, threshold in values.items():
        if 'warn' in threshold:
            if threshold['warn'] > threshold['fail']:
                raise ValueError(f'Ordre des seuils invalide : {check_id}')
            if check_id != 'surface.stretch' and max(threshold['warn'], threshold['fail']) > 100:
                raise ValueError('Un pourcentage ne peut dépasser 100.')
        if 'min_bytes' in threshold and not 0 < threshold['min_bytes'] <= threshold['max_bytes']:
            raise ValueError('Bornes de chunk invalides.')
        if threshold.get('tolerance_points', 0) > 100:
            raise ValueError('Une tolérance en points de pourcentage ne peut dépasser 100.')
        for name in ('relative_tolerance', 'range_fraction'):
            if name in threshold and threshold[name] > 1:
                raise ValueError('Une fraction doit rester entre 0 et 1.')
    return MappingProxyType({key: MappingProxyType(value) for key, value in values.items()})
