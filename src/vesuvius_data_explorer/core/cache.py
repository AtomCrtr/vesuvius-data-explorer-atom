"""Persistent local cache of remote volume chunks (T6).

Vesuvius volumes are stored as uncompressed 128³ chunks of 2 MiB; a 2D view reads chunks 128
slices deep, so the next slices, a repeated QC or a repeated alignment measure reuse the same
chunks. They are kept on disk, one folder per volume URI, under
``$XDG_CACHE_HOME/vesuvius-data-explorer/chunks`` (``~/.cache`` by default).

Built on ``zarr.experimental.cache_store.CacheStore`` (an experimental Zarr API): if it is
missing or changes, the cache is disabled with a French warning and reads go to the source.
``CacheStore`` keeps its LRU book-keeping in memory only and per volume, so size and age limits
are also enforced on disk for all volumes together: when a cached volume is opened, and again
during the session after every ``PRUNE_EVERY_FRACTION`` of the limit read through the cache.
Deleting a cached file under a live ``CacheStore`` is safe: the read falls back to the source.

Environment: ``VESUVIUS_CACHE=0`` disables the cache; ``VESUVIUS_CACHE_MAX_GB`` sets the size
limit for all volumes (10 GiB by default).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import time
from pathlib import Path
from typing import Any
from warnings import warn

DEFAULT_MAX_GB = 10.0
MAX_AGE_S = 30 * 24 * 3600
SOURCE_FILE = "source.txt"
PRUNE_EVERY_FRACTION = 0.05  # Re-check the global limit after 5 % of it has been read.


def default_cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(Path.home(), ".cache")
    return Path(base) / "vesuvius-data-explorer"


def chunk_cache_root() -> Path:
    return default_cache_dir() / "chunks"


def cache_enabled() -> bool:
    return os.environ.get("VESUVIUS_CACHE", "1").strip() != "0"


def max_cache_bytes() -> int:
    raw = os.environ.get("VESUVIUS_CACHE_MAX_GB")
    try:
        value = float(raw) if raw is not None else DEFAULT_MAX_GB
    except ValueError:
        value = -1.0
    if not value > 0:
        warn(f"VESUVIUS_CACHE_MAX_GB invalide ({raw!r}) : limite de {DEFAULT_MAX_GB:g} Gio "
             "utilisée.", stacklevel=2)
        value = DEFAULT_MAX_GB
    return int(value * 2**30)


def volume_cache_dir(uri: str, root: Path | None = None) -> Path:
    key = uri.strip().rstrip("/")
    return (root or chunk_cache_root()) / hashlib.sha256(key.encode()).hexdigest()[:16]


def _files(root: Path) -> list[tuple[Path, os.stat_result]]:
    found = []
    for path in root.rglob("*"):
        try:
            if path.is_file() and path.name != SOURCE_FILE:
                found.append((path, path.stat()))
        except OSError:
            continue
    return found


def cache_size(root: Path | None = None) -> int:
    root = root or chunk_cache_root()
    return sum(stat.st_size for _, stat in _files(root)) if root.exists() else 0


def prune(root: Path | None = None, max_bytes: int | None = None, max_age_s: float = MAX_AGE_S,
          now: float | None = None) -> int:
    """Delete expired files, then the least recently used ones until under ``max_bytes``.

    Recency is the later of access and modification times (access times may be disabled on
    the file system). Returns the number of bytes freed.
    """
    root = root or chunk_cache_root()
    if not root.exists():
        return 0
    max_bytes = max_cache_bytes() if max_bytes is None else max_bytes
    now = time.time() if now is None else now
    entries = sorted(_files(root), key=lambda item: max(item[1].st_atime, item[1].st_mtime))
    total = sum(stat.st_size for _, stat in entries)
    freed = 0
    for path, stat in entries:
        expired = now - stat.st_mtime > max_age_s
        if not expired and total <= max_bytes:
            continue
        try:
            path.unlink()
        except OSError:
            continue
        total -= stat.st_size
        freed += stat.st_size
    for folder in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
        try:
            folder.rmdir()  # Only empty folders go.
        except OSError:
            pass
    return freed


def clear_cache(root: Path | None = None) -> int:
    """Remove every cached volume; returns the number of bytes freed."""
    root = root or chunk_cache_root()
    freed = cache_size(root)
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    return freed


def cached_store(store: Any, uri: str, root: Path | None = None) -> Any:
    """``store`` behind a persistent chunk cache for ``uri``, or ``store`` itself if disabled."""
    if not cache_enabled():
        return store
    try:
        from zarr.experimental.cache_store import CacheStore
        from zarr.storage import LocalStore
    except ImportError:
        warn("Cache local indisponible avec cette version de Zarr (CacheStore absent) : "
             "lectures directes depuis la source.", stacklevel=2)
        return store
    root = root or chunk_cache_root()
    limit = max_cache_bytes()
    prune(root, limit)
    folder = volume_cache_dir(uri, root)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / SOURCE_FILE).write_text(uri.strip().rstrip("/") + "\n", encoding="utf-8")
        cache = CacheStore(store, cache_store=LocalStore(str(folder)),
                           max_age_seconds=MAX_AGE_S, max_size=limit)
        return _pruning(cache, root, limit)
    except (OSError, TypeError, ValueError) as error:
        warn(f"Cache local indisponible ({error}) : lectures directes depuis la source.",
             stacklevel=2)
        return store


_READ_SINCE_PRUNE = {"bytes": 0}


def _pruning(cache: Any, root: Path, limit: int) -> Any:
    """``cache`` wrapped so that reads periodically enforce the global size limit on disk.

    Several volumes opened in one session each have their own ``CacheStore`` (and its own
    in-memory limit): without this, the cache could grow to one limit per volume.
    """
    import asyncio

    from zarr.storage import WrapperStore

    threshold = max(int(limit * PRUNE_EVERY_FRACTION), 1)

    class PruningStore(WrapperStore):
        def _with_store(self, store):
            return type(self)(store)

        def with_read_only(self, read_only=False):
            return self._with_store(self._store.with_read_only(read_only))

        async def get(self, key, prototype, byte_range=None):
            value = await self._store.get(key, prototype, byte_range)
            if value is not None:
                _READ_SINCE_PRUNE["bytes"] += len(value)
                if _READ_SINCE_PRUNE["bytes"] >= threshold:
                    _READ_SINCE_PRUNE["bytes"] = 0
                    await asyncio.to_thread(prune, root, limit)
            return value

    return PruningStore(cache)
