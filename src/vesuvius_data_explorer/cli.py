"""Headless vesuvius-qc entry point; checks live exclusively in qc/."""
import argparse
import json
import sys
from pathlib import Path

from .core.tifxyz import DEFAULT_MAX_BYTES
from .core.volume import open_levels, open_volume_store
from .qc import run_surface, run_volume
from .qc.report import render_html
from .qc.thresholds import load_thresholds


class _UsageError(ValueError):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _UsageError(message)


def main(argv=None):
    parser = _Parser(prog='vesuvius-qc', description='Contrôle qualité borné, sans interface graphique.')
    commands = parser.add_subparsers(dest='kind', required=True, parser_class=_Parser)
    for kind in ('volume', 'surface'):
        command = commands.add_parser(kind)
        command.add_argument('uri')
        command.add_argument('--max-voxels', type=int, default=None if kind == 'surface' else 16777216)
        command.add_argument('--config')
        command.add_argument('-o', '--output')
        command.add_argument('--html')
        if kind == 'volume':
            command.add_argument('--level')
            command.add_argument('--samples', type=int, default=16)
            command.add_argument('--seed', type=int, default=0)
        else:
            command.add_argument('--max-bytes', type=int, default=DEFAULT_MAX_BYTES,
                                 help='budget de lecture par grille, en octets')
            # Pre-T5 options of the patch reader: accepted, ignored, reported as warnings.
            command.add_argument('--window', type=int, default=None, help=argparse.SUPPRESS)
            command.add_argument('--volume', help='volume visé : active surface.bounds et le '
                                 'profil exploratoire surface.alignment')
            command.add_argument('--pixel-size-um', type=float, default=None,
                                 help='taille de voxel du volume (portée du profil en µm)')
    try:
        args = parser.parse_args(argv)
        if args.output and args.html and Path(args.output).resolve() == Path(args.html).resolve():
            raise ValueError('Les sorties JSON et HTML doivent être différentes.')
        thresholds = load_thresholds(args.config)
        if args.kind == 'volume':
            root = open_volume_store(args.uri, cache=True)
            report = run_volume(root, uri=args.uri, level=args.level, samples=args.samples,
                                seed=args.seed, max_voxels=args.max_voxels, thresholds=thresholds)
        else:
            volume = None
            if args.volume:
                arrays, levels = open_levels(args.volume)
                volume = (arrays, [level.shape for level in levels])
            report = run_surface(args.uri, max_bytes=args.max_bytes, window=args.window,
                                 max_voxels=args.max_voxels, thresholds=thresholds,
                                 volume=volume, pixel_size_um=args.pixel_size_um)
        document = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
        if args.output:
            Path(args.output).write_text(document, encoding='utf-8')
        else:
            sys.stdout.write(document)
        if args.html:
            Path(args.html).write_text(render_html(report), encoding='utf-8')
        for warning in report['parameters']['warnings']:
            print(warning, file=sys.stderr)
        return int(bool(report['summary']['fail'] or report['summary']['error']))
    except Exception as exc:
        # Dependency-specific I/O and codec exceptions all denote input/output
        # failure here. Pure-check exceptions are already isolated in qc/checks.
        print(f'vesuvius-qc : {type(exc).__name__} : {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
