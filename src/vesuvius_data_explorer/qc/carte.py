"""Alignment map of one segment, written in community formats (T10).

``run_map`` measures the map, lists the regions to review and, on request, writes a snapped copy
of the segment; ``write_outputs`` saves TIFF maps, ``zones.json``, ``carte.json`` and an HTML
report with the coloured map and flattened renders before / after snapping.
"""

from __future__ import annotations

import base64
import io
import json
from datetime import datetime, timezone
from html import escape
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np

from ..core.alignment import level_factors
from ..core.alignment_map import (
    DEFAULT_MAX_DRIFT_UM,
    DEFAULT_MAX_SHIFT_UM,
    DEFAULT_MIN_RELIABILITY,
    DEFAULT_SMOOTHING,
    DEFAULT_TILE,
    alignment_map,
    drift_voxels,
    field_on_grid,
    reliable_tiles,
    review_zones,
    snap_field,
    snap_points,
    switch_tiles,
)
from ..core.flatten import flatten, sharpness
from ..core.tifxyz import TifxyzSurface, load_tifxyz, write_tifxyz

DEFAULT_MAP_MAX_BYTES = 512 * 2**20
RENDER_SIDE = 1024  # Pixels of the flattened renders (per side, at most).


def _finite(value):
    if value is None:
        return None
    value = float(value)
    return value if np.isfinite(value) else None


def render_crop(surface: TifxyzSurface, amap, level: int, shapes) -> tuple[slice, slice]:
    """Grid window of at most RENDER_SIDE pixels per side, centred on the most reliable tiles."""
    factor = float(level_factors(shapes)[level].mean())
    up = max(1, int(round(surface.step_voxels / factor)))
    side = max(2, RENDER_SIDE // up + 1)
    weight = np.nan_to_num(amap.reliability, nan=0.0, posinf=1e6)
    r, c = np.unravel_index(int(np.argmax(weight)), weight.shape)
    centre = ((r + 0.5) * amap.tile, (c + 0.5) * amap.tile)
    rows, cols = surface.points.shape[:2]
    r0 = int(np.clip(centre[0] - side // 2, 0, max(rows - side, 0)))
    c0 = int(np.clip(centre[1] - side // 2, 0, max(cols - side, 0)))
    return slice(r0, min(r0 + side, rows)), slice(c0, min(c0 + side, cols))


def run_map(segment_uri: str, arrays, shapes, *, pixel_size_um=None, snap=False,
            tile=DEFAULT_TILE, max_bytes=DEFAULT_MAP_MAX_BYTES,
            max_drift_um=DEFAULT_MAX_DRIFT_UM, min_reliability=DEFAULT_MIN_RELIABILITY,
            smoothing=DEFAULT_SMOOTHING, max_shift_um=DEFAULT_MAX_SHIFT_UM, render=True,
            volume_uri=None) -> dict[str, Any]:
    """Measure the map of ``segment_uri``; returns a result dict (arrays included)."""
    started = perf_counter()
    surface = load_tifxyz(segment_uri, max_bytes=max_bytes)
    if snap and surface.stride > 1:
        raise ValueError("Recalage impossible sur une grille décimée : augmenter --max-bytes "
                         f"(grille de {surface.grid_shape[0]} × {surface.grid_shape[1]} points).")
    amap = alignment_map(surface, arrays, shapes, pixel_size_um=pixel_size_um, tile=tile)
    zones = review_zones(amap, pixel_size_um=pixel_size_um, max_drift_um=max_drift_um,
                         min_reliability=min_reliability)
    scale = pixel_size_um if pixel_size_um and pixel_size_um > 0 else None
    result: dict[str, Any] = {"surface": surface, "map": amap, "zones": zones, "scale": scale}
    snapped_points = None
    if snap:
        max_shift = max_shift_um / (pixel_size_um if pixel_size_um else 1.0)
        field = snap_field(amap, min_reliability=min_reliability, smoothing=smoothing,
                           max_shift=max_shift)
        grid = field_on_grid(field, amap, surface.points.shape[:2])
        snapped_points = snap_points(surface.points, grid)
        result.update(field=field, field_grid=grid, snapped_points=snapped_points)
    if render:
        crop = render_crop(surface, amap, amap.level, shapes)
        before = flatten(surface.points[crop], arrays, shapes, level=amap.level,
                         step_voxels=surface.step_voxels)
        result.update(crop=crop, render_before=before)
        if snapped_points is not None:
            result["render_after"] = flatten(snapped_points[crop], arrays, shapes,
                                             level=amap.level, step_voxels=surface.step_voxels)
    result["summary"] = summarize(result, segment_uri=segment_uri, volume_uri=volume_uri,
                                  max_drift_um=max_drift_um, min_reliability=min_reliability,
                                  smoothing=smoothing, seconds=perf_counter() - started)
    return result


def summarize(result, *, segment_uri, volume_uri, max_drift_um, min_reliability, smoothing,
              seconds) -> dict[str, Any]:
    amap, scale = result["map"], result["scale"]
    unit = scale or 1.0
    reliable = reliable_tiles(amap, min_reliability)
    drift = drift_voxels(amap)[reliable] * unit
    measured = int((amap.points > 0).sum())
    summary: dict[str, Any] = {
        "tool": "vesuvius-data-explorer",
        "version": version("vesuvius-data-explorer"),
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "segment": segment_uri,
        "volume": volume_uri,
        "pixel_size_um": scale,
        "unite": "µm" if scale else "voxels",
        "grid_shape": list(result["surface"].grid_shape),
        "stride": result["surface"].stride,
        "tile": amap.tile,
        "level": amap.level,
        "half_range_voxels": amap.half_range,
        "voxels_read": amap.voxels_read,
        "seconds": round(seconds, 1),
        "tiles": {"total": int(amap.offset.size), "measured": measured,
                  "determined": int(np.isfinite(amap.offset).sum()),
                  "reliable": int(reliable.sum()),
                  "switch": int(switch_tiles(amap).sum())},
        "reference": None if amap.reference is None else amap.reference * unit,
        "spacing": None if amap.spacing is None else amap.spacing * unit,
        "drift_reliable": None if len(drift) == 0 else {
            "median": float(np.median(drift)),
            "abs_median": float(np.median(np.abs(drift))),
            "p95_abs": float(np.percentile(np.abs(drift), 95))},
        "uncertainty_median": _finite(np.nanmedian(amap.uncertainty[reliable]) * unit)
        if reliable.any() else None,
        "parameters": {"max_drift": max_drift_um, "min_reliability": min_reliability,
                       "smoothing": smoothing},
        "zones": {kind: sum(z["type"] == kind for z in result["zones"])
                  for kind in ("saut_de_feuille", "derive", "sans_feuille")},
        "warnings": list(result["surface"].warnings) + list(amap.warnings),
    }
    if "field" in result:
        moved = result["field_grid"][np.isfinite(result["surface"].points).all(axis=2)]
        summary["snap"] = {"abs_median": float(np.median(np.abs(moved))) * unit,
                           "abs_max": float(np.max(np.abs(moved))) * unit}
    if "render_before" in result:
        summary["render"] = {"before": sharpness(result["render_before"])}
        if "render_after" in result:
            summary["render"]["after"] = sharpness(result["render_after"])
    return summary


def _png(image: np.ndarray) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.fromarray(image).save(buffer, format="PNG")
    return buffer.getvalue()


def grey_png(image: np.ndarray) -> bytes:
    valid = np.isfinite(image)
    out = np.zeros(image.shape, dtype=np.uint8)
    if valid.any():
        low, high = np.percentile(image[valid], [1, 99])
        scaled = (image - low) / max(high - low, 1e-9)
        out[valid] = (np.clip(scaled[valid], 0, 1) * 255).astype(np.uint8)
    return _png(out)


def drift_png(amap, scale, *, limit_um=DEFAULT_MAX_DRIFT_UM, cell=16,
              min_reliability=DEFAULT_MIN_RELIABILITY) -> bytes:
    """Tile map: blue = sheet below the surface along the normal, red = above, white = usual
    offset; light grey = unreliable, dark grey = not measured; black frame = sheet switch."""
    unit = scale or 1.0
    drift = drift_voxels(amap) * unit
    t = np.clip(np.nan_to_num(drift) / limit_um, -1, 1)
    rgb = np.stack([np.where(t > 0, 1, 1 + t), 1 - np.abs(t), np.where(t < 0, 1, 1 - t)], -1)
    rgb = (rgb * 255).astype(np.uint8)
    rgb[~reliable_tiles(amap, min_reliability)] = (200, 200, 200)
    rgb[amap.points == 0] = (90, 90, 90)
    image = np.kron(rgb, np.ones((cell, cell, 1), dtype=np.uint8))
    for r, c in zip(*np.nonzero(switch_tiles(amap))):
        block = image[r * cell:(r + 1) * cell, c * cell:(c + 1) * cell]
        block[:2], block[-2:], block[:, :2], block[:, -2:] = 0, 0, 0, 0
    return _png(image)


def write_outputs(result: dict[str, Any], folder: str | Path) -> Path:
    import tifffile

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    amap, summary = result["map"], result["summary"]
    for name, data in (("decalage", drift_voxels(amap)), ("fiabilite", amap.reliability),
                       ("incertitude", amap.uncertainty)):
        unit = result["scale"] if name != "fiabilite" and result["scale"] else 1.0
        tifffile.imwrite(folder / f"{name}.tif", (data * unit).astype(np.float32))
    (folder / "zones.json").write_text(json.dumps(result["zones"], indent=2, ensure_ascii=False)
                                       + "\n", encoding="utf-8")
    (folder / "carte.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False,
                                                  allow_nan=False) + "\n", encoding="utf-8")
    if "snapped_points" in result:
        surface = result["surface"]
        meta = dict(surface.meta)
        meta["recalage"] = {"outil": "vesuvius-data-explorer " + summary["version"],
                            "source": surface.source, "date": summary["created"],
                            "parametres": summary["parameters"]}
        write_tifxyz(folder / "recale", result["snapped_points"], meta)
    (folder / "rapport.html").write_text(render_report(result), encoding="utf-8")
    return folder


def _img(data: bytes, alt: str) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f'<img alt="{escape(alt)}" src="data:image/png;base64,{encoded}">'


def render_report(result: dict[str, Any]) -> str:
    summary, amap = result["summary"], result["map"]
    unit = summary["unite"]

    def fmt(value, digits=1):
        return "—" if value is None else f"{value:.{digits}f}"

    tiles = summary["tiles"]
    drift = summary["drift_reliable"] or {}
    rows = [
        ("Tuiles mesurées / fiables", f"{tiles['measured']} / {tiles['reliable']} "
                                      f"(sur {tiles['total']})"),
        ("Décalage habituel du segment", f"{fmt(summary['reference'])} {unit}"),
        ("Espacement des feuilles", f"{fmt(summary['spacing'])} {unit}"),
        ("Dérive médiane absolue (tuiles fiables)", f"{fmt(drift.get('abs_median'))} {unit}"),
        ("Dérive absolue, 95e centile", f"{fmt(drift.get('p95_abs'))} {unit}"),
        ("Incertitude médiane", f"{fmt(summary['uncertainty_median'])} {unit}"),
        ("Zones : saut de feuille / dérive / sans feuille",
         " / ".join(str(summary["zones"][k]) for k in ("saut_de_feuille", "derive",
                                                       "sans_feuille"))),
        ("Lecture", f"niveau {summary['level']}, {summary['voxels_read'] / 2**20:.0f} Mi-voxels, "
                    f"{summary['seconds']} s"),
    ]
    if "snap" in summary:
        rows.append(("Recalage : déplacement médian / max",
                     f"{fmt(summary['snap']['abs_median'])} / {fmt(summary['snap']['abs_max'])} "
                     f"{unit}"))
    table = "".join(f"<tr><th>{escape(k)}</th><td>{escape(v)}</td></tr>" for k, v in rows)
    zones = "".join(
        f"<tr><td>{z['rang']}</td><td>{escape(z['type'])}</td><td>{z['tuiles']}</td>"
        f"<td>{z['lignes'][0]}–{z['lignes'][1]}</td><td>{z['colonnes'][0]}–{z['colonnes'][1]}</td>"
        f"<td>{escape(str(z['centre_zyx']))}</td><td>{fmt(z['derive_mediane'])}</td></tr>"
        for z in result["zones"][:50])
    renders = ""
    if "render_before" in result:
        renders = "<h2>Rendu aplati</h2><div class=row><figure>" + _img(
            grey_png(result["render_before"]), "avant") + "<figcaption>Segment publié"
        if "render_after" in result:
            renders += "</figcaption></figure><figure>" + _img(
                grey_png(result["render_after"]), "après") + "<figcaption>Après recalage"
        renders += "</figcaption></figure></div>"
    warnings = "".join(f"<li>{escape(w)}</li>" for w in summary["warnings"])
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>Carte d'alignement</title><style>
body{{font-family:system-ui,sans-serif;margin:24px;max-width:1100px}}
table{{border-collapse:collapse;margin:8px 0}}th,td{{border:1px solid #ccc;padding:4px 8px;
text-align:left}}img{{max-width:100%;image-rendering:pixelated;border:1px solid #888}}
.row{{display:flex;gap:16px;flex-wrap:wrap}}figure{{margin:0;flex:1;min-width:300px}}
</style></head><body>
<h1>Carte d'alignement</h1>
<p>Segment : <code>{escape(summary['segment'])}</code><br>
Volume : <code>{escape(str(summary['volume']))}</code></p>
<table>{table}</table>
<h2>Carte de dérive</h2>
<p>Une case par tuile de {amap.tile} × {amap.tile} points. Blanc : décalage habituel du segment ;
bleu ou rouge : la feuille s'éloigne d'un côté ou de l'autre (saturé à
{summary['parameters']['max_drift']} {unit}) ; gris clair : mesure peu fiable ; gris foncé : non
mesuré ; cadre noir : saut de feuille.</p>
{_img(drift_png(amap, result['scale'], limit_um=summary['parameters']['max_drift'],
               min_reliability=summary['parameters']['min_reliability']), 'carte de dérive')}
{renders}
<h2>Zones à revoir</h2>
<table><tr><th>Rang</th><th>Type</th><th>Tuiles</th><th>Lignes</th><th>Colonnes</th>
<th>Centre (z, y, x)</th><th>Dérive médiane ({unit})</th></tr>{zones}</table>
{f'<h2>Avertissements</h2><ul>{warnings}</ul>' if warnings else ''}
<p><small>vesuvius-data-explorer {escape(summary['version'])}, {escape(summary['created'])}.
Mesure exploratoire : voir docs/tasks/T10-carte-alignement.md.</small></p>
</body></html>
"""
