"""Headless vesuvius-qc entry point; checks live exclusively in qc/."""
import argparse
import json
import sys
from pathlib import Path

from .core.volume import open_volume_store
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
        command.add_argument('--max-voxels', type=int, default=16777216)
        command.add_argument('--config')
        command.add_argument('-o', '--output')
        command.add_argument('--html')
        if kind == 'volume':
            command.add_argument('--level')
            command.add_argument('--samples', type=int, default=16)
            command.add_argument('--seed', type=int, default=0)
        else:
            command.add_argument('--window', type=int, default=256)
    try:
        args = parser.parse_args(argv)
        if args.output and args.html and Path(args.output).resolve() == Path(args.html).resolve():
            raise ValueError('Les sorties JSON et HTML doivent être différentes.')
        thresholds = load_thresholds(args.config)
        if args.kind == 'volume':
            root = open_volume_store(args.uri)
            report = run_volume(root, uri=args.uri, level=args.level, samples=args.samples,
                                seed=args.seed, max_voxels=args.max_voxels, thresholds=thresholds)
        else:
            report = run_surface(args.uri, window=args.window, max_voxels=args.max_voxels,
                                 thresholds=thresholds)
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
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'vesuvius-qc : {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
