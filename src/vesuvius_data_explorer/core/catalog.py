"""Official Vesuvius Challenge catalogue ("Vesuvius Atlas", ``metadata.json``).

The catalogue describes every sample, volume and derived artefact of the open-data bucket,
including the physical voxel size (``pixel_size_um``) that OME metadata does not carry. Only
the parts needed to choose and open a volume are parsed here; see
docs/investigations/I1-ecosysteme-donnees.md.
"""

from __future__ import annotations

import gzip
import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .volume import ALLOWED_HTTPS_HOSTS

CATALOG_URI = "s3://vesuvius-challenge-open-data/metadata.json"
DEFAULT_MAX_AGE_S = 24 * 3600
# Artefact types holding a volume pyramid, and the codec each one needs.
VOLUME_DATA_TYPES = {"ome-zarr": "standard", "ome-zarr-vcd3d": "vc-delta3d"}


@dataclass(frozen=True)
class CatalogVolume:
    """One openable copy of a catalogued volume."""

    sample_id: str
    sample_type: str | None
    volume_id: str
    name: str
    uri: str
    codec: str  # "standard" or "vc-delta3d"
    pixel_size_um: float | None
    energy_kev: float | None
    shape: tuple[int, int, int] | None
    dtype: str | None
    license: str | None
    superseded_by: str | None
    superseded_reason: str | None

    @property
    def label(self) -> str:
        """Short French label for a selection list."""
        parts = [self.volume_id]
        if self.pixel_size_um is not None:
            parts.append(f"{format_um(self.pixel_size_um)} µm")
        if self.energy_kev is not None:
            parts.append(f"{self.energy_kev:g} keV")
        label = " — ".join(parts)
        if self.codec != "standard":
            label += f" [{self.codec}]"
        if self.superseded_by:
            label += " (remplacé)"
        return label


@dataclass(frozen=True)
class Catalog:
    volumes: tuple[CatalogVolume, ...]
    source: str
    stale: bool = False  # True when the network failed and an older cached copy was used

    def samples(self) -> list[str]:
        return sorted({volume.sample_id for volume in self.volumes})

    def volumes_of(self, sample_id: str) -> list[CatalogVolume]:
        return [volume for volume in self.volumes if volume.sample_id == sample_id]

    def find(self, uri: str) -> CatalogVolume | None:
        key = uri.strip().rstrip("/")
        return next((volume for volume in self.volumes if volume.uri == key), None)


def format_um(value: float) -> str:
    """French decimal notation: 2.399 -> '2,399'."""
    return f"{value:g}".replace(".", ",")


def _uri(path: str, roots: list[dict[str, Any]]) -> str | None:
    """Openable URI for a catalogue path: public S3 first, then official HTTPS."""
    candidates = []
    for root in roots or []:
        if root.get("usage") != "public-read" or not isinstance(root.get("url"), str):
            continue
        base = root["url"].rstrip("/")
        if root.get("type") == "s3" and base.startswith("s3://"):
            candidates.append((0, base))
        elif root.get("type") == "https" and urlsplit(base).hostname in ALLOWED_HTTPS_HOSTS:
            candidates.append((1, base))
    if not candidates:
        return None
    _, base = min(candidates)
    return f"{base}/{path.strip('/')}"


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _shape(value: Any) -> tuple[int, int, int] | None:
    if isinstance(value, list) and len(value) == 3 and all(isinstance(v, int) for v in value):
        return tuple(value)
    return None


def parse_catalog(data: Any, source: str = CATALOG_URI, stale: bool = False) -> Catalog:
    """Openable volume copies of a decoded ``metadata.json``, in a stable order."""
    if not isinstance(data, dict) or not isinstance(data.get("samples"), dict):
        raise ValueError("Catalogue mal formé : clé « samples » absente.")
    volumes = []
    for sample_id, sample in data["samples"].items():
        if not isinstance(sample, dict):
            continue
        sample_props = (sample.get("sample") or {}).get("properties") or {}
        for volume_id, volume in (sample.get("volumes") or {}).items():
            if not isinstance(volume, dict):
                continue
            props = volume.get("properties") or {}
            superseded = props.get("superseded_by") or {}
            license_ = props.get("license") or {}
            for data_entry in volume.get("data") or []:
                codec = VOLUME_DATA_TYPES.get(data_entry.get("type"))
                if codec is None:
                    continue
                # Several origins of one entry are copies of the same data: keep the best one.
                uris = [
                    (_uri(origin.get("path", ""), origin.get("access_roots")), origin)
                    for origin in data_entry.get("origins") or []
                    if isinstance(origin.get("path"), str)
                ]
                uris = [(uri, origin) for uri, origin in uris if uri]
                if not uris:
                    continue
                uri, origin = min(uris, key=lambda item: not item[0].startswith("s3://"))
                volumes.append(
                    CatalogVolume(
                        sample_id=str(sample_id),
                        sample_type=sample_props.get("type"),
                        volume_id=str(volume_id),
                        name=origin["path"].strip("/").rsplit("/", 1)[-1],
                        uri=uri,
                        codec=codec,
                        pixel_size_um=_number(props.get("pixel_size_um")),
                        energy_kev=_number(props.get("energy_keV")),
                        shape=_shape(props.get("shape")),
                        dtype=props.get("data_format"),
                        license=license_.get("name") if isinstance(license_, dict) else None,
                        superseded_by=superseded.get("volume_id")
                        if isinstance(superseded, dict) else None,
                        superseded_reason=superseded.get("reason")
                        if isinstance(superseded, dict) else None,
                    )
                )
    volumes.sort(key=lambda v: (v.sample_id, v.volume_id, v.codec != "standard", v.name))
    return Catalog(tuple(volumes), source=source, stale=stale)


def default_cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(Path.home(), ".cache")
    return Path(base) / "vesuvius-data-explorer"


def _decode(raw: bytes) -> Any:
    if raw[:2] == b"\x1f\x8b":  # The bucket serves the catalogue gzip-encoded.
        raw = gzip.decompress(raw)
    return json.loads(raw)


def _fetch(uri: str) -> bytes:
    import fsspec

    options = {"anon": True} if uri.startswith("s3://") else {}
    with fsspec.open(uri, "rb", **options) as handle:
        return handle.read()


def load_catalog(
    source: str = CATALOG_URI,
    *,
    cache_dir: str | os.PathLike | None = None,
    max_age_s: float = DEFAULT_MAX_AGE_S,
    refresh: bool = False,
) -> Catalog:
    """Load the catalogue, from a local file or a remote URI through a local cache.

    A remote catalogue (about 9 MB compressed) is downloaded at most once per ``max_age_s``
    unless ``refresh`` is set. If the download fails, an older cached copy is used and the
    result is marked ``stale``.
    """
    if "://" not in source:
        path = Path(source)
        if not path.is_file():
            raise FileNotFoundError(f"Catalogue introuvable : {source}")
        return parse_catalog(_decode(path.read_bytes()), source=str(path))
    cache = Path(cache_dir) if cache_dir is not None else default_cache_dir()
    cached = cache / "metadata.json"
    if not refresh and cached.is_file() and time.time() - cached.stat().st_mtime < max_age_s:
        catalog = _read_cache(cached, source, stale=False)
        if catalog is not None:
            return catalog
    try:
        raw = _fetch(source)
        data = _decode(raw)
    except Exception as error:
        catalog = _read_cache(cached, source, stale=True)
        if catalog is not None:
            return catalog
        raise ConnectionError(
            "Catalogue officiel inaccessible : vérifier l'accès au réseau, ou indiquer le chemin "
            "du volume à la main."
        ) from error
    catalog = parse_catalog(data, source=source)
    _write_cache(cached, raw)
    return catalog


def _read_cache(cached: Path, source: str, stale: bool) -> Catalog | None:
    """Cached catalogue, or None when absent or unreadable (it is then downloaded again)."""
    try:
        return parse_catalog(_decode(cached.read_bytes()), source=source, stale=stale)
    except (OSError, ValueError, EOFError):  # json and gzip errors are ValueError/EOFError/OSError
        return None


def _write_cache(cached: Path, raw: bytes) -> None:
    """Keep the bytes as served (gzip, about 4x smaller); atomic replace for concurrent readers."""
    temporary = None
    try:
        cached.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=cached.parent, delete=False, suffix=".tmp") as handle:
            temporary = handle.name
            handle.write(raw)
        os.replace(temporary, cached)
    except OSError:
        # A read-only or full cache only costs a later download.
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
