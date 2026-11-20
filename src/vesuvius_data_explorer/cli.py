"""Headless vesuvius-qc entry point; checks live exclusively in qc/."""
import argparse
import json
import sys
from pathlib import Path

from .core.geometry import verified_sampling
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
    batch = commands.add_parser('lot', help='tous les segments du catalogue publiés pour un volume')
    batch.add_argument('volume_id', help='identifiant du volume dans le catalogue officiel')
    batch.add_argument('-o', '--output', required=True, help='dossier de sortie')
    batch.add_argument('--max-segments', type=int, default=None)
    batch.add_argument('--workers', type=int, default=4)
    batch.add_argument('--sans-alignement', action='store_true',
                       help="ne pas mesurer l'alignement (plus rapide, moins de lectures)")
    batch.add_argument('--max-bytes', type=int, default=DEFAULT_MAX_BYTES)
    batch.add_argument('--config')
    batch.add_argument('--catalogue', help='fichier metadata.json local (sinon catalogue officiel)')
    carte = commands.add_parser('carte', help="carte d'alignement d'un segment (T10), recalage "
                                "sur demande")
    carte.add_argument('segment', help="URI du segment tifxyz, ou son identifiant avec --catalogue")
    carte.add_argument('-o', '--output', required=True, help='dossier de sortie')
    carte.add_argument('--volume', help='URI du volume (sinon retrouvé dans le catalogue)')
    carte.add_argument('--pixel-size-um', type=float, default=None)
    carte.add_argument('--catalogue', nargs='?', const='', default=None,
                       help="retrouver le segment, son volume et la taille de voxel dans le "
                       "catalogue officiel (ou un metadata.json local)")
    carte.add_argument('--recaler', action='store_true',
                       help='écrire une copie recalée du segment dans <dossier>/recale')
    carte.add_argument('--tuile', type=int, default=8, help='points par côté de tuile')
    carte.add_argument('--max-bytes', type=int, default=512 * 2**20)
    carte.add_argument('--derive-max', type=float, default=30.0,
                       help='dérive signalée au-delà de cette valeur (µm)')
    carte.add_argument('--sans-rendu', action='store_true', help='pas de rendu aplati')
    carte.add_argument('--cible', type=float, default=None,
                       help="décalage visé par le recalage (µm) ; par défaut, le décalage "
                       "habituel du segment (une dérive d'ensemble est alors conservée)")
    carte.add_argument('--deplacement-max', type=float, default=50.0,
                       help='au-delà (µm), une tuile n\'est pas déplacée mais signalée')
    ink = commands.add_parser('encre', help="comparer deux cartes d'encre déjà calculées")
    ink.add_argument('manifest', help='manifeste TOML du benchmark')
    ink.add_argument('-o', '--output', required=True, help='nouveau dossier de sortie')
    try:
        args = parser.parse_args(argv)
        if args.kind == 'encre':
            from .qc.ink import run_ink_benchmark

            run_ink_benchmark(args.manifest, args.output)
            return 0
        if args.kind == 'lot':
            return _batch(args)
        if args.kind == 'carte':
            return _carte(args)
        if args.output and args.html and Path(args.output).resolve() == Path(args.html).resolve():
            raise ValueError('Les sorties JSON et HTML doivent être différentes.')
        thresholds = load_thresholds(args.config)
        if args.kind == 'volume':
            root = open_volume_store(args.uri, cache=True)
            report = run_volume(root, uri=args.uri, level=args.level, samples=args.samples,
                                seed=args.seed, max_voxels=args.max_voxels, thresholds=thresholds)
        else:
            volume = None
            sampling = None
            if args.volume:
                arrays, levels = open_levels(args.volume)
                volume = (arrays, [level.shape for level in levels])
                sampling = verified_sampling(args.volume, levels)
            report = run_surface(args.uri, max_bytes=args.max_bytes, window=args.window,
                                 max_voxels=args.max_voxels, thresholds=thresholds,
                                 volume=volume, pixel_size_um=args.pixel_size_um, sampling=sampling)
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


def _carte(args):
    from .qc.carte import run_map, write_outputs

    segment_uri, volume_uri, pixel = args.segment, args.volume, args.pixel_size_um
    if args.catalogue is not None:
        from .core.catalog import load_catalog

        catalog = load_catalog(args.catalogue) if args.catalogue else load_catalog()
        segment = next((s for s in catalog.segments if s.segment_id == args.segment
                        and not s.superseded and (volume_uri is None or
                        any(v.uri == volume_uri and v.volume_id == s.target_volume_id
                            for v in catalog.volumes))), None)
        if segment is None:
            raise ValueError(f'Segment absent du catalogue : {args.segment}')
        volume = next(v for v in catalog.volumes
                      if v.volume_id == segment.target_volume_id and v.codec == 'standard')
        segment_uri, volume_uri = segment.uri, volume.uri
        pixel = pixel if pixel is not None else volume.pixel_size_um
    if not volume_uri:
        raise ValueError('Volume inconnu : donner --volume ou --catalogue.')
    arrays, levels = open_levels(volume_uri)
    result = run_map(segment_uri, arrays, [level.shape for level in levels], pixel_size_um=pixel,
                     snap=args.recaler, tile=args.tuile, max_bytes=args.max_bytes,
                     max_drift_um=args.derive_max, max_shift_um=args.deplacement_max,
                     target_um=args.cible, render=not args.sans_rendu,
                     volume_uri=volume_uri, sampling=verified_sampling(volume_uri, levels))
    folder = write_outputs(result, args.output)
    summary = result['summary']
    print(f"{summary['tiles']['reliable']} tuile(s) fiable(s) sur {summary['tiles']['measured']}"
          f" mesurée(s) ; zones : " + ', '.join(f'{k} {v}' for k, v in summary['zones'].items())
          + f" ; rapport dans {folder / 'rapport.html'}", file=sys.stderr)
    for warning in summary['warnings']:
        print(warning, file=sys.stderr)
    return 0


def _batch(args):
    from .core.catalog import load_catalog
    from .qc.batch import run_batch, to_csv, to_html

    output = Path(args.output)
    catalog = load_catalog(args.catalogue) if args.catalogue else load_catalog()

    def progress(done, total, row):
        print(f'[{done}/{total}] {row["segment"]} : {row["status"]} ({row["seconds"]} s)',
              file=sys.stderr, flush=True)

    summary = run_batch(catalog, args.volume_id, max_segments=args.max_segments,
                        workers=args.workers, alignment=not args.sans_alignement,
                        max_bytes=args.max_bytes, thresholds=load_thresholds(args.config),
                        reports_dir=output / 'rapports', progress=progress)
    (output / 'synthese.json').write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    (output / 'synthese.csv').write_text(to_csv(summary), encoding='utf-8')
    (output / 'synthese.html').write_text(to_html(summary), encoding='utf-8')
    counts = summary['summary']['segments']
    print(f"{summary['parameters']['segments']} segment(s) en {summary['duration_s']} s : "
          + ', '.join(f'{k} {v}' for k, v in counts.items() if v)
          + f" ; synthèse dans {output / 'synthese.html'}", file=sys.stderr)
    return int(bool(counts['fail'] or counts['error']))


if __name__ == '__main__':
    raise SystemExit(main())
