"""Strict report validation and portable escaped HTML, using only stdlib."""
import json
import math
from html import escape
from importlib.resources import files


def validate_report(report):
    """Validate the versioned schema subset used by this package.

    This stdlib validator keeps jsonschema optional (dev extra). The schema has
    deliberately only structural keywords implemented below; tests also validate
    every report with the independent Draft202012Validator implementation.
    """
    schema = json.loads(files(__package__).joinpath('report.schema.json').read_text())
    json.dumps(report, allow_nan=False)

    def visit(value, rule, path):
        if '$ref' in rule:
            rule = schema['$defs'][rule['$ref'].rsplit('/', 1)[-1]]
        expected = rule.get('type')
        types = expected if isinstance(expected, list) else [expected]
        kinds = {'object': isinstance(value, dict), 'array': isinstance(value, list),
                 'string': isinstance(value, str), 'null': value is None,
                 'integer': isinstance(value, int) and not isinstance(value, bool),
                 'number': isinstance(value, (int, float)) and not isinstance(value, bool)}
        if expected and not any(kinds[kind] for kind in types):
            raise ValueError(f'{path} : type invalide.')
        if 'enum' in rule and value not in rule['enum']:
            raise ValueError(f'{path} : valeur inconnue.')
        if isinstance(value, (int, float)) and ((isinstance(value, float) and not math.isfinite(value)) or value < rule.get('minimum', -math.inf)):
            raise ValueError(f'{path} : nombre invalide.')
        if isinstance(value, dict):
            if any(key not in value for key in rule.get('required', [])):
                raise ValueError(f'{path} : champ requis manquant.')
            properties = rule.get('properties', {})
            for key, child in value.items():
                if key in properties:
                    visit(child, properties[key], f'{path}.{key}')
                elif rule.get('additionalProperties') is False:
                    raise ValueError(f'{path}.{key} : champ inconnu.')
                elif isinstance(rule.get('additionalProperties'), dict):
                    visit(child, rule['additionalProperties'], f'{path}.{key}')
        if isinstance(value, list):
            if len(value) < rule.get('minItems', 0) or len(value) > rule.get('maxItems', math.inf):
                raise ValueError(f'{path} : longueur invalide.')
            for index, child in enumerate(value):
                visit(child, rule.get('items', {}), f'{path}[{index}]')
    visit(report, schema, 'report')
    counts = {status: sum(r['status'] == status for r in report['results']) for status in report['summary']}
    if report['summary'] != counts or report['budget']['voxels_read'] > report['parameters']['max_voxels']:
        raise ValueError('Résumé ou budget incohérent.')


def render_html(report):
    validate_report(report)
    def text(value):
        return escape(str(value), quote=True)
    summary = ' '.join(f'<span class="{text(status)}">{text(status)} : {count}</span>'
                       for status, count in report['summary'].items())
    rows = []
    for result in report['results']:
        locations = '; '.join(f"{v['level']} / {v['axis']}={v['index']} / origine {v['origin']} / taille {v['size']}"
                              for v in result['locations'])
        cells = (result['check_id'], result['status'], result['value'], result['threshold'],
                 result['message'], locations)
        rows.append('<tr>' + ''.join(f'<td>{text(value)}</td>' for value in cells) + '</tr>')
    return ('<!doctype html><html lang="fr"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Contrôle qualité Vesuvius</title><style>'
            'body{font:16px system-ui;margin:2rem;color:#18232b}table{border-collapse:collapse}'
            'td,th{padding:.6rem;border:1px solid #aaa;text-align:left;vertical-align:top}'
            'span{padding:.5rem;display:inline-block}.pass{background:#ccebd6}'
            '.warn{background:#fff0ba}.fail,.error{background:#ffd0cc}.skipped{background:#ddd}'
            '</style><h1>Contrôle qualité Vesuvius</h1>'
            f'<p>Cible : {text(report["target"]["uri"])} ; niveau {text(report["target"]["level"])}</p>'
            f'<p>{summary}</p><p>Voxels matérialisés : {report["budget"]["voxels_read"]}</p>'
            f'<p>{text(report["budget"]["physical_io_note"])}</p>'
            + ''.join(f'<p>{text(warning)}</p>' for warning in report['parameters']['warnings'])
            + '<table><thead><tr><th>Contrôle</th><th>Statut</th><th>Valeur</th><th>Seuils</th>'
              '<th>Message</th><th>Localisations</th></tr></thead><tbody>'
            + ''.join(rows) + '</tbody></table></html>')
