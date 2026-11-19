"""Offline comparison of registered ink scores and independently labelled crops."""

import hashlib
import json
import math
import tomllib
from pathlib import Path
from statistics import mean
from tempfile import TemporaryDirectory

import numpy as np
import scipy
import tifffile
from PIL import Image, ImageDraw
from PIL import __version__ as pillow_version
from scipy import ndimage, stats

from .. import __version__

METHODS = ('left', 'right', 'mean', 'minimum', 'product')
STRATA = ('standard', 'blank', 'scan_artifact', 'geometry_error', 'uncertain')
METRICS = ('auc', 'precision', 'recall', 'fpr')
CROSS = ndimage.generate_binary_structure(2, 1)
FULL = ndimage.generate_binary_structure(2, 2)


def _rate(numerator, denominator):
    return numerator / denominator if denominator else None


def _pixel_metrics(score, labels, threshold):
    known = labels != 255
    positives, negatives = labels == 1, labels == 0
    predicted = score >= threshold
    tp = int(np.count_nonzero(predicted & positives))
    fp = int(np.count_nonzero(predicted & negatives))
    p, n = int(positives.sum()), int(negatives.sum())
    auc = None
    if p and n:
        ranks = stats.rankdata(score[known])
        auc = float((ranks[positives[known]].sum() - p * (p + 1) / 2) / (p * n))
    return {
        'tp': tp, 'fp': fp, 'fn': p - tp, 'tn': n - fp,
        'unlabelled': int(np.count_nonzero(~known)),
        'unlabelled_positive': int(np.count_nonzero(~known & predicted)),
        'auc': auc, 'precision': _rate(tp, tp + fp), 'recall': _rate(tp, p),
        'fpr': _rate(fp, n),
    }


def _topology(mask):
    # Complementary connectivities avoid counting diagonal foreground gaps as holes.
    components = ndimage.label(mask, structure=FULL)[1]
    holes = ndimage.label(~np.pad(mask, 1), structure=CROSS)[1] - 1
    return {'components': components, 'holes': holes}


def _glyph_metrics(predicted, truth, tolerance):
    a = predicted & ~ndimage.binary_erosion(predicted, structure=CROSS)
    b = truth & ~ndimage.binary_erosion(truth, structure=CROSS)
    boundary_f1 = 0.0
    if a.any() and b.any():
        precision = np.mean(ndimage.distance_transform_edt(~b)[a] <= tolerance)
        recall = np.mean(ndimage.distance_transform_edt(~a)[b] <= tolerance)
        boundary_f1 = float(2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    predicted_topology, reference_topology = _topology(predicted), _topology(truth)
    return {
        'boundary_f1': boundary_f1, 'predicted': predicted_topology,
        'reference': reference_topology, 'topology_matches': predicted_topology == reference_topology,
    }


def _read_plane(path, max_pixels):
    if path.stat().st_size > 8 * max_pixels + 2**20:
        raise ValueError(f'TIFF trop volumineux : {path}')
    with path.open('rb') as stream:
        sha256 = hashlib.file_digest(stream, 'sha256').hexdigest()
        stream.seek(0)
        with tifffile.TiffFile(stream) as image:
            if len(image.series) != 1:
                raise ValueError(f'Un seul plan TIFF est attendu : {path}')
            series = image.series[0]
            if series.axes != 'YX' or math.prod(series.shape) > max_pixels:
                raise ValueError(f'Un plan TIFF YX de {max_pixels} pixels au plus est attendu : {path}')
            return series.asarray(), sha256


def _required_text(mapping, key):
    value = mapping[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{key} doit être un texte non vide.')
    return value


def _glyph_boxes(boxes, labels):
    result = {}
    height, width = labels.shape
    for name, coordinates in boxes.items():
        x0, y0, x1, y1 = coordinates
        if (
            any(type(value) is not int for value in coordinates)
            or not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height)
        ):
            raise ValueError(f'Boîte hors image ou invalide : {name}')
        box = np.s_[y0:y1, x0:x1]
        if np.any(labels[box] == 255) or not np.any(labels[box] == 1):
            raise ValueError(f'La boîte {name} doit être entièrement annotée et contenir de l’encre.')
        result[name] = box
    return result


def _comparison(path, scores, labels, ct, thresholds, dataset_kind):
    def grayscale(plane):
        return Image.fromarray(np.rint(plane * 255).astype(np.uint8)).convert('RGB')

    def errors(score, threshold):
        view = np.full((*labels.shape, 3), (65, 71, 85), dtype=np.uint8)
        predicted = score >= threshold
        view[labels == 0] = (14, 17, 24)
        view[(labels == 1) & predicted] = (89, 211, 150)
        view[(labels == 0) & predicted] = (255, 107, 107)
        view[(labels == 1) & ~predicted] = (115, 169, 255)
        return Image.fromarray(view)

    reference = np.where(labels == 255, 70, (labels == 1) * 255).astype(np.uint8)
    ct_panel = None
    if ct is not None:
        low, high = np.percentile(ct, [1, 99])
        ct = np.clip((ct - low) / (high - low), 0, 1) if high > low else np.zeros(ct.shape)
        ct_panel = grayscale(ct)
    # Each score uses the same display scale. The colour panels use manifest thresholds.
    panels = [
        ('Référence annotée', Image.fromarray(reference).convert('RGB')),
        ('Modèle droit', grayscale(scores['right'])),
        ('Avant (modèle gauche)', grayscale(scores['left'])),
        ('Après (produit)', grayscale(scores['product'])),
        ('CT (P1-P99)', ct_panel), ('', None),
        ('Erreurs avant', errors(scores['left'], thresholds['left'])),
        ('Erreurs après', errors(scores['product'], thresholds['product'])),
    ]
    height, width = labels.shape
    zoom = min(4, 350 / max(height, width))
    size = (max(1, round(width * zoom)), max(1, round(height * zoom)))
    cell_width, cell_height = max(size[0] + 12, 190), size[1] + 25
    cols = 4
    rows = math.ceil(len(panels) / cols)
    canvas = Image.new('RGB', (cols * cell_width, rows * cell_height + 25), (23, 28, 37))
    draw = ImageDraw.Draw(canvas)
    for index, (title, panel) in enumerate(panels):
        if panel is not None:
            x, y = (index % cols) * cell_width + 6, (index // cols) * cell_height
            draw.text((x, y + 3), title, fill='white')
            canvas.paste(panel.resize(size, Image.Resampling.NEAREST), (x, y + 19))
    prefix = 'Données simulées  |  ' if dataset_kind == 'synthetic' else ''
    draw.text((6, rows * cell_height + 4),
              prefix + 'Vert VP | Rouge FP | Bleu FN | Gris inconnu', fill='white')
    canvas.save(path)


def _evaluate_crop(crop, base, output, index, thresholds, scales, tolerance, max_pixels,
                   dataset_kind):
    metadata = {key: _required_text(crop, key) for key in
                ('id', 'scroll', 'volume', 'surface', 'provenance')}
    pixel_size = float(crop['pixel_size_um'])
    if not math.isfinite(pixel_size) or pixel_size <= 0:
        raise ValueError('pixel_size_um doit être positif et fini.')
    files, planes = {}, {}
    for key in ('left', 'right', 'labels', 'strata', 'ct'):
        if key in ('strata', 'ct') and key not in crop:
            continue
        filename = _required_text(crop, key)
        planes[key], sha256 = _read_plane(base / filename, max_pixels)
        files[key] = {'path': filename, 'sha256': sha256}
    labels = planes['labels']
    if any(plane.shape != labels.shape for plane in planes.values()):
        raise ValueError('Les plans doivent avoir les mêmes dimensions et le même repère.')
    if labels.dtype.kind not in 'bui' or not np.isin(labels, [0, 1, 255]).all():
        raise ValueError('Les labels TIFF doivent valoir 0, 1 ou 255.')
    strata = planes.get('strata', np.zeros(labels.shape, dtype=np.uint8))
    if strata.dtype.kind not in 'bui' or not np.isin(strata, range(len(STRATA))).all():
        raise ValueError('Les strates TIFF doivent être des entiers entre 0 et 4.')
    if np.any((strata == 1) & (labels == 1)) or np.any((strata == 4) & (labels != 255)):
        raise ValueError('Papyrus vierge : 0 ou 255. Zone incertaine : 255 uniquement.')
    ct = planes.get('ct')
    if ct is not None:
        if ct.dtype.kind not in 'buif' or not np.isfinite(ct).all():
            raise ValueError('Le plan CT doit contenir des valeurs réelles et finies.')
        ct = ct.astype(np.float64)
    scores = {}
    for key in METHODS[:2]:
        if planes[key].dtype.kind not in 'buif':
            raise ValueError(f'Le score {key} doit contenir des valeurs réelles.')
        score = planes[key].astype(np.float64) / scales[key]
        if not (np.isfinite(score).all() and np.all((score >= 0) & (score <= 1))):
            raise ValueError(f'Le score {key} divisé par son échelle doit être dans [0, 1].')
        scores[key] = score
    a, b = scores['left'], scores['right']
    scores.update(mean=(a + b) / 2, minimum=np.minimum(a, b), product=a * b)
    boxes = _glyph_boxes(crop.get('glyphs', {}), labels)
    results = {}
    for key, score in scores.items():
        threshold = thresholds[key]
        predicted = score >= threshold
        results[key] = {
            'pixels': _pixel_metrics(score, labels, threshold),
            'strata': {name: _pixel_metrics(score[mask], labels[mask], threshold)
                       for code, name in enumerate(STRATA) if (mask := strata == code).any()},
            'glyphs': {name: _glyph_metrics(predicted[box], labels[box] == 1, tolerance)
                       for name, box in boxes.items()},
        }
    filename = f'comparaison-{index:03d}.png'
    _comparison(output / filename, scores, labels, ct, thresholds, dataset_kind)
    return dict(metadata, pixel_size_um=pixel_size, shape_yx=list(labels.shape), files=files,
                glyphs=crop.get('glyphs', {}), comparison=filename, methods=results)


def _summarize(crops):
    """Average per crop within each scroll, then give all scrolls equal weight."""
    groups = {}
    for crop in crops:
        groups.setdefault(crop['scroll'], []).append(crop)
    by_scroll = {}
    for scroll, group in groups.items():
        by_scroll[scroll] = {}
        for method in METHODS:
            averages = {}
            for metric in METRICS:
                values = [crop['methods'][method]['pixels'][metric] for crop in group]
                defined = [value for value in values if value is not None]
                averages[metric] = mean(defined) if defined else None
            by_scroll[scroll][method] = averages
    macro = {}
    for method in METHODS:
        macro[method] = {}
        for metric in METRICS:
            values = [row[method][metric] for row in by_scroll.values()
                      if row[method][metric] is not None]
            macro[method][metric] = {'mean': mean(values) if values else None, 'scrolls': len(values)}
    return {'by_scroll': by_scroll, 'macro_scroll': macro}


def run_ink_benchmark(manifest, output):
    """Evaluate local 2D TIFF inputs and publish a report with one comparison per crop."""
    manifest, output = Path(manifest), Path(output).resolve()
    raw = manifest.read_bytes()
    config = tomllib.loads(raw.decode('utf-8'))
    if config['schema_version'] != 1 or config['dataset_kind'] not in ('synthetic', 'real'):
        raise ValueError('schema_version doit valoir 1, dataset_kind synthetic ou real.')
    max_pixels = config.get('max_pixels', 2**20)
    tolerance = config.get('boundary_tolerance_px', 1.0)
    if type(max_pixels) is not int or max_pixels <= 0:
        raise ValueError('max_pixels doit être un entier positif.')
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError('boundary_tolerance_px doit être positif ou nul et fini.')
    thresholds = {key: float(config['thresholds'][key]) for key in METHODS}
    if any(not 0 <= value <= 1 for value in thresholds.values()):
        raise ValueError('Les seuils doivent être dans [0, 1].')
    models, scales = config['models'], {}
    for key in METHODS[:2]:
        _required_text(models[key], 'name')
        _required_text(models[key], 'checkpoint')
        scales[key] = float(models[key]['scale'])
        if not math.isfinite(scales[key]) or scales[key] <= 0:
            raise ValueError('Les échelles doivent être positives et finies.')
    crops = config['crops']
    ids = [_required_text(crop, 'id') for crop in crops]
    if not ids or len(set(ids)) != len(ids):
        raise ValueError('Au moins une fenêtre et des identifiants uniques sont exigés.')
    if output.exists():
        raise FileExistsError(f'Le dossier de sortie existe déjà : {output}')
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as temporary:
        stage = Path(temporary) / 'benchmark'
        stage.mkdir()
        results = [
            _evaluate_crop(crop, manifest.parent, stage, index, thresholds, scales,
                           tolerance, max_pixels, config['dataset_kind'])
            for index, crop in enumerate(crops, 1)
        ]
        report = {
            'schema_version': 1, 'dataset_kind': config['dataset_kind'],
            'manifest_sha256': hashlib.sha256(raw).hexdigest(),
            'models': {key: {field: models[key][field] for field in ('name', 'checkpoint', 'scale')}
                       for key in METHODS[:2]},
            'thresholds': thresholds, 'boundary_tolerance_px': tolerance, 'max_pixels': max_pixels,
            'software': {'vesuvius-data-explorer': __version__, 'numpy': np.__version__,
                         'scipy': scipy.__version__, 'tifffile': tifffile.__version__,
                         'pillow': pillow_version},
            'crops': results, 'summary': _summarize(results),
        }
        (stage / 'rapport.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
            encoding='utf-8',
        )
        if output.exists():
            raise FileExistsError(f'Le dossier de sortie existe déjà : {output}')
        stage.rename(output)
    return report
