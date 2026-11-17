"""Registry of pure checks; data acquisition belongs to the engine."""
from math import isfinite, prod

import numpy as np

from ..model import CheckResult, Location

REGISTRY = {'metadata': (), 'samples': (), 'surface': ()}


def register(group, check_id):
    def decorate(function):
        REGISTRY[group] += ((check_id, function),)
        return function
    return decorate


def run_checks(group, context, thresholds):
    results = []
    for check_id, function in REGISTRY[group]:
        try:
            results.append(function(context, thresholds))
        except Exception as exc:
            results.append(CheckResult(check_id, 'error', None, {},
                                       f'Échec du contrôle : {type(exc).__name__} : {exc}'))
    return tuple(results)


def _location(level):
    return Location(level.key, 'z', 0, (0, 0), (min(256, level.shape[1]), min(256, level.shape[2])))


def _metadata_result(check_id, bad, thresholds, message):
    return CheckResult(check_id, 'warn' if bad else 'pass', float(len(bad)),
                       thresholds.get(check_id, {}), message, tuple(_location(v) for v in bad))


@register('metadata', 'volume.levels.present')
def levels_present(context, thresholds):
    levels = context['levels']
    return CheckResult('volume.levels.present', 'pass' if levels else 'fail', float(len(levels)),
                       {}, f'{len(levels)} niveau(x) 3D détecté(s).')


@register('metadata', 'volume.levels.dtype')
def levels_dtype(context, thresholds):
    levels = context['levels']
    bad = [v for v in levels[1:] if np.dtype(v.dtype) != np.dtype(levels[0].dtype)]
    return _metadata_result('volume.levels.dtype', bad, thresholds,
                            'Types des niveaux identiques.' if not bad else 'Types des niveaux différents.')


@register('metadata', 'volume.levels.shape_ratio')
def shape_ratio(context, thresholds):
    key = 'volume.levels.shape_ratio'
    tolerance = thresholds[key]['tolerance_voxels']
    bad = [b for a, b in zip(context['levels'], context['levels'][1:])
           if any(abs(y - x / 2) > tolerance for x, y in zip(a.shape, b.shape))]
    return _metadata_result(key, bad, thresholds, 'Rapport des formes : moitié ± tolérance en voxels.')


@register('metadata', 'volume.levels.scale_consistency')
def scale_consistency(context, thresholds):
    key = 'volume.levels.scale_consistency'
    levels = context['levels']
    if not all(level.scale_from_metadata for level in levels):
        return CheckResult(key, 'skipped', None, thresholds[key],
                           'Échelles unitaires de repli (métadonnées absentes ou invalides) : '
                           'cohérence non évaluable.')
    tolerance = thresholds[key]['relative_tolerance']
    bad = [b for a, b in zip(levels, levels[1:])
           if any(abs((sb / sa) / (na / nb) - 1) > tolerance
                  for sa, sb, na, nb in zip(a.scale, b.scale, a.shape, b.shape))]
    return _metadata_result(key, bad, thresholds, 'Cohérence échelles/formes (tolérance relative).')


@register('metadata', 'volume.chunks.size')
def chunks_size(context, thresholds):
    key = 'volume.chunks.size'
    threshold = thresholds[key]
    bad = [v for v in context['levels'] if not threshold['min_bytes'] <=
           prod(v.chunks) * np.dtype(v.dtype).itemsize <= threshold['max_bytes']]
    return _metadata_result(key, bad, thresholds, 'Taille non compressée des chunks dans les bornes.')


def _graded(check_id, value, locations, thresholds, message, lower=False):
    threshold = thresholds[check_id]
    if value is None or not isfinite(value):
        return CheckResult(check_id, 'skipped', None, threshold, 'Mesure non définie : ' + message)
    status = 'pass'
    for candidate in ('warn', 'fail'):
        if (value < threshold[candidate]) if lower else (value > threshold[candidate]):
            status = candidate
    return CheckResult(check_id, status, float(value), threshold, message,
                       tuple(locations) if status != 'pass' else ())


@register('samples', 'volume.finite')
def finite(context, thresholds):
    samples = context['samples']
    total = sum(data.size for _, data in samples)
    count = sum(np.count_nonzero(~np.isfinite(data)) for _, data in samples)
    bad = [loc for loc, data in samples if (~np.isfinite(data)).any()]
    return _graded('volume.finite', 100 * count / total if total else None, bad, thresholds,
                   'Pourcentage de voxels non finis.')


def _foreground(data, thresholds):
    """Voxels outside the masked background; the whole ROI when exclusion is disabled."""
    background = thresholds['volume.background']
    if not background['enabled']:
        return data.ravel()
    return data[data != background['value']]


def _foreground_samples(samples, thresholds):
    """(location, foreground voxels) for ROIs that are not entirely background."""
    pairs = [(loc, _foreground(data, thresholds)) for loc, data in samples]
    return [(loc, voxels) for loc, voxels in pairs if voxels.size]


def _background_note(samples, kept):
    ignored = len(samples) - len(kept)
    return f' {ignored} ROI entièrement dans le fond ignorée(s).' if ignored else ''


@register('samples', 'volume.background')
def background(context, thresholds):
    key = 'volume.background'
    threshold = thresholds[key]
    samples = context['samples']
    if not threshold['enabled']:
        return CheckResult(key, 'skipped', None, threshold, 'Exclusion du fond désactivée.')
    total = sum(data.size for _, data in samples)
    if not total:
        return CheckResult(key, 'skipped', None, threshold, 'Aucun voxel échantillonné.')
    count = sum(np.count_nonzero(data == threshold['value']) for _, data in samples)
    return CheckResult(key, 'pass', 100 * count / total, threshold,
                       f'Information : pourcentage de voxels de fond (valeur {threshold["value"]:g}), '
                       'exclus des contrôles de saturation, de zones vides et de contraste.')


@register('samples', 'volume.saturation')
def saturation(context, thresholds):
    key = 'volume.saturation'
    if not np.issubdtype(np.dtype(context['dtype']), np.integer):
        return CheckResult(key, 'skipped', None, thresholds[key], 'Saturation réservée aux entiers.')
    limits = np.iinfo(context['dtype'])
    kept = _foreground_samples(context['samples'], thresholds)
    scores = [(loc, np.count_nonzero((v == limits.min) | (v == limits.max)), v.size)
              for loc, v in kept]
    total = sum(size for _, _, size in scores)
    bad = [loc for loc, n, size in scores if 100 * n / size > thresholds[key]['warn']]
    return _graded(key, 100 * sum(n for _, n, _ in scores) / total if total else None,
                   bad, thresholds, 'Pourcentage de voxels hors fond aux extrêmes du dtype.'
                   + _background_note(context['samples'], kept))


@register('samples', 'volume.empty')
def empty(context, thresholds):
    kept = _foreground_samples(context['samples'], thresholds)
    bad = [loc for loc, v in kept if np.isfinite(v).all() and np.all(v == v[0])]
    return _graded('volume.empty', 100 * len(bad) / len(kept) if kept else None,
                   bad, thresholds, 'Pourcentage de ROI (hors fond) entièrement constantes.'
                   + _background_note(context['samples'], kept))


@register('samples', 'volume.low_contrast')
def low_contrast(context, thresholds):
    key = 'volume.low_contrast'
    dtype = np.dtype(context['dtype'])
    if not np.issubdtype(dtype, np.integer):
        return CheckResult(key, 'skipped', None, thresholds[key],
                           'Plage physique du dtype flottant inconnue : contraste non évalué.')
    limits = np.iinfo(dtype)
    cutoff = (float(limits.max) - float(limits.min)) * thresholds[key]['range_fraction']
    kept = _foreground_samples(context['samples'], thresholds)
    bad = [loc for loc, v in kept if np.std(v.astype(np.float64)) < cutoff]
    return _graded(key, 100 * len(bad) / len(kept) if kept else None,
                   bad, thresholds, 'Pourcentage de ROI de faible contraste (voxels hors fond).'
                   + _background_note(context['samples'], kept))


@register('surface', 'surface.valid')
def surface_valid(context, thresholds):
    # Informational since T5: the irregular outline of a healthy segment lowers this ratio.
    value = context['metrics']['valid_pct']
    return CheckResult('surface.valid', 'pass', float(value) if isfinite(value) else None, {},
                       'Pourcentage de points valides (informatif : les bords irréguliers du '
                       'segment le font baisser sans défaut ; voir surface.holes).')


@register('surface', 'surface.holes')
def surface_holes(context, thresholds):
    locations = [Location('surface', 'z', 0, hole['origin'], hole['size'], hole['center'])
                 for hole in context['metrics']['holes']]
    return _graded('surface.holes', context['metrics']['hole_pct'], locations, thresholds,
                   'Pourcentage de points manquants à l\'intérieur du segment (trous non reliés '
                   'au bord de la grille).')


@register('surface', 'surface.stretch')
def surface_stretch(context, thresholds):
    median = context['metrics']['median_step']
    ratio = context['metrics']['p95_step'] / median if median > 0 else None
    return _graded('surface.stretch', ratio, [context['location']], thresholds,
                   'Rapport pas p95 / pas médian.')


@register('surface', 'surface.normal_flips')
def surface_normal_flips(context, thresholds):
    return _graded('surface.normal_flips', context['metrics']['normal_flip_pct'],
                   [context['location']], thresholds,
                   'Pourcentage de cellules voisines aux normales opposées (replis ; heuristique).')


@register('surface', 'surface.bounds')
def surface_bounds(context, thresholds):
    key = 'surface.bounds'
    threshold = thresholds[key]
    outside = context['metrics']['out_of_bounds_pct']
    if outside is None:
        return CheckResult(key, 'skipped', None, threshold,
                           'Forme du volume inconnue : points hors volume non évalués.')
    message = f'{outside:.4g} % des points valides hors du volume'
    overlap = context.get('overlap_ratio')
    if overlap is None:
        return CheckResult(key, 'pass', float(outside), threshold,
                           message + ' (informatif : couverture du catalogue inconnue).')
    gap = abs((100 - outside) - 100 * overlap)
    status = 'warn' if gap > threshold['tolerance_points'] else 'pass'
    message += (f' ; couverture annoncée par le catalogue {100 * overlap:.4g} %, écart '
                f'{gap:.2g} point(s)')
    message += ' : catalogue incohérent avec les données.' if status == 'warn' else '.'
    return CheckResult(key, status, float(outside), threshold, message)
