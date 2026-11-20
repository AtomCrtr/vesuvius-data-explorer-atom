"""Batch QC (T7): every catalogued segment of one volume, one summary.

The volume is opened once (Zarr arrays and local chunk cache, T6) and shared by worker
threads; each segment gets the full ``run_surface`` report (holes, bounds against the
catalogue coverage, stretch, folds, graded alignment). A failure on one segment is recorded
in its row and never stops the batch.
"""

from __future__ import annotations

import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html import escape
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from ..core.catalog import Catalog
from ..core.geometry import verified_sampling
from ..core.tifxyz import DEFAULT_MAX_BYTES
from ..core.volume import open_levels
from .engine import run_surface
from .thresholds import load_thresholds

CHECKS = ("surface.holes", "surface.bounds", "surface.stretch", "surface.normal_flips",
          "surface.alignment", "surface.valid")
STATUS_RANK = {"error": 0, "fail": 1, "warn": 2, "pass": 3, "skipped": 4}


def _row(segment, report=None, error=None, seconds=0.0) -> dict[str, Any]:
    row = {"segment": segment.segment_id, "name": segment.name, "uri": segment.uri,
           "overlap_ratio": segment.overlap_ratio, "seconds": round(seconds, 1)}
    if error is not None:
        row.update(status="error", error=error, checks={})
        return row
    results = {r["check_id"]: r for r in report["results"]}
    row["checks"] = {check: {"status": results[check]["status"],
                             "value": results[check]["value"],
                             "message": results[check]["message"]}
                     for check in CHECKS if check in results}
    row["grid_shape"] = report["parameters"]["grid_shape"]
    row["stride"] = report["parameters"]["stride"]
    row["status"] = min((c["status"] for c in row["checks"].values()),
                        key=STATUS_RANK.__getitem__, default="skipped")
    return row


def run_batch(catalog: Catalog, volume_id: str, *, max_segments: int | None = None,
              workers: int = 4, alignment: bool = True, max_bytes: int = DEFAULT_MAX_BYTES,
              thresholds=None, reports_dir: str | Path | None = None,
              progress: Callable[[int, int, dict], None] | None = None,
              open_volume=open_levels) -> dict[str, Any]:
    """QC of the current catalogued segments of ``volume_id``; returns the summary.

    ``reports_dir`` receives one full JSON report per segment. ``progress(done, total, row)``
    is called after each segment. ``open_volume`` is injectable for tests.
    """
    if isinstance(workers, bool) or not isinstance(workers, int) or workers < 1:
        raise ValueError("Le nombre de tâches parallèles doit être un entier positif.")
    volume = next((v for v in catalog.volumes
                   if v.volume_id == volume_id and v.codec == "standard"), None)
    if volume is None:
        raise ValueError(f"Volume absent du catalogue (copie standard) : {volume_id}")
    segments = catalog.segments_for(volume_id)
    if max_segments is not None:
        segments = segments[:max_segments]
    if not segments:
        raise ValueError(f"Aucun segment publié dans le repère du volume {volume_id}.")
    thresholds = thresholds if thresholds is not None else load_thresholds()
    started = perf_counter()
    arrays, levels = open_volume(volume.uri)
    shapes = [level.shape for level in levels]
    shared = (arrays, shapes) if alignment else None
    sampling = verified_sampling(volume.uri, levels) if alignment else None
    folder = Path(reports_dir) if reports_dir is not None else None
    if folder is not None:
        folder.mkdir(parents=True, exist_ok=True)

    def one(segment):
        begin = perf_counter()
        try:
            report = run_surface(segment.uri, max_bytes=max_bytes, thresholds=thresholds,
                                 volume_shape=shapes[0], overlap_ratio=segment.overlap_ratio,
                                 volume=shared, pixel_size_um=volume.pixel_size_um,
                                 sampling=sampling)
        except Exception as error:  # recorded per segment: the batch goes on
            return _row(segment, error=f"{type(error).__name__} : {error}",
                        seconds=perf_counter() - begin)
        if folder is not None:
            (folder / f"{segment.segment_id}.json").write_text(
                json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                encoding="utf-8")
        return _row(segment, report, seconds=perf_counter() - begin)

    rows = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for row in pool.map(one, segments):
            rows.append(row)
            if progress is not None:
                progress(len(rows), len(segments), row)
    counts = {status: sum(row["status"] == status for row in rows) for status in STATUS_RANK}
    per_check = {check: {status: sum(row["checks"].get(check, {}).get("status") == status
                                     for row in rows) for status in STATUS_RANK}
                 for check in CHECKS}
    return {
        "kind": "vesuvius-qc-batch",
        "version": "1.0",
        "tool": {"name": "vesuvius-data-explorer", "version": version("vesuvius-data-explorer")},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "duration_s": round(perf_counter() - started, 1),
        "volume": {"sample_id": volume.sample_id, "volume_id": volume.volume_id,
                   "uri": volume.uri, "pixel_size_um": volume.pixel_size_um,
                   "shape": list(shapes[0])},
        "parameters": {"segments": len(segments), "max_segments": max_segments,
                       "alignment": alignment, "max_bytes": max_bytes, "workers": workers,
                       "thresholds": {key: dict(value) for key, value in thresholds.items()}},
        "summary": {"segments": counts, "checks": per_check},
        "rows": sorted(rows, key=lambda r: (STATUS_RANK[r["status"]], r["segment"])),
    }


def to_csv(summary: dict) -> str:
    """One line per segment: worst status, then status and value of every check."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["segment", "statut", "secondes", *(f"{c} statut" for c in CHECKS),
                     *(f"{c} valeur" for c in CHECKS), "erreur", "uri"])
    for row in summary["rows"]:
        checks = row.get("checks", {})
        writer.writerow([row["segment"], row["status"], row["seconds"],
                         *(checks.get(c, {}).get("status", "") for c in CHECKS),
                         *("" if checks.get(c, {}).get("value") is None
                           else f"{checks[c]['value']:.4g}" for c in CHECKS),
                         row.get("error", ""), row["uri"]])
    return out.getvalue()


COLORS = {"fail": "#ffd0cc", "error": "#ffd0cc", "warn": "#fff0ba", "pass": "#ccebd6",
          "skipped": "#e4e4e4"}


def to_html(summary: dict) -> str:
    """Self-contained French HTML page; every value is escaped."""
    volume = summary["volume"]
    counts = " · ".join(f"{escape(k)} : {v}" for k, v in summary["summary"]["segments"].items())
    head = "".join(f"<th>{escape(c.removeprefix('surface.'))}</th>" for c in CHECKS)
    lines = []
    for row in summary["rows"]:
        cells = []
        for check in CHECKS:
            result = row.get("checks", {}).get(check)
            if result is None:
                cells.append("<td></td>")
                continue
            value = "" if result["value"] is None else f"{result['value']:.3g}"
            cells.append(f'<td style="background:{COLORS[result["status"]]}" '
                         f'title="{escape(result["message"], quote=True)}">'
                         f'{escape(result["status"])} {escape(value)}</td>')
        error = escape(row.get("error", ""))
        lines.append(f'<tr><td style="background:{COLORS[row["status"]]}">'
                     f'{escape(row["segment"])}</td><td>{escape(row["status"])}</td>'
                     + "".join(cells) + f"<td>{row['seconds']}</td><td>{error}</td></tr>")
    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        f'<title>QC en lot — {escape(volume["volume_id"])}</title>'
        '<style>body{font-family:sans-serif;margin:1.5em;color:#18232b}'
        'table{border-collapse:collapse}td,th{border:1px solid #bbb;padding:3px 6px;'
        'font-size:13px}th{background:#eee}</style></head><body>'
        f'<h1>QC en lot — {escape(volume["sample_id"])} {escape(volume["volume_id"])}</h1>'
        f'<p>{escape(volume["uri"])} · voxel {escape(str(volume["pixel_size_um"]))} µm · '
        f'{summary["parameters"]["segments"]} segment(s) en {summary["duration_s"]} s · '
        f'{escape(summary["created_at"])}</p><p>{counts}</p>'
        '<p>Survoler une cellule affiche le message du contrôle.</p>'
        f'<table><tr><th>segment</th><th>statut</th>{head}<th>s</th><th>erreur</th></tr>'
        + "".join(lines) + "</table></body></html>\n")
