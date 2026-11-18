"""Local chunk cache (T6): filled once, reused across stores, bounded, optional."""

import os
import time

import numpy as np
import pytest
import zarr
from zarr.storage import LocalStore, WrapperStore

from vesuvius_data_explorer.core import cache as cache_module
from vesuvius_data_explorer.core.cache import (
    MAX_AGE_S,
    cache_size,
    cached_store,
    clear_cache,
    prune,
    volume_cache_dir,
)
from vesuvius_data_explorer.core.volume import estimate_contrast, open_levels

pytest.importorskip("zarr.experimental.cache_store")


class CountingStore(WrapperStore):
    """Source store that records the data keys it is asked for."""

    def __init__(self, store, reads):
        super().__init__(store)
        self.reads = reads

    def _with_store(self, store):
        return type(self)(store, self.reads)

    async def get(self, key, prototype, byte_range=None):
        if not key.rsplit("/", 1)[-1].startswith((".z", "zarr.json")):
            self.reads.append(key)
        return await self._store.get(key, prototype, byte_range)


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "source.zarr"
    array = zarr.create_array(str(path), shape=(32, 32, 32), chunks=(16, 16, 16), dtype="uint8",
                              zarr_format=2)
    array[:] = np.arange(32**3, dtype=np.uint32).reshape(32, 32, 32) % 251
    return path


@pytest.fixture
def cache_root(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    monkeypatch.delenv("VESUVIUS_CACHE", raising=False)
    monkeypatch.delenv("VESUVIUS_CACHE_MAX_GB", raising=False)
    return tmp_path / "xdg" / "vesuvius-data-explorer" / "chunks"


def read_through_cache(source, uri, reads):
    store = cached_store(CountingStore(LocalStore(str(source), read_only=True), reads), uri)
    return zarr.open_array(store=store, mode="r")[:16, :16, :16]


def test_chunks_are_cached_on_disk_and_reused_by_a_new_store(source, cache_root):
    uri = "s3://bucket/volume.zarr"
    reads = []
    first = read_through_cache(source, uri, reads)
    assert reads == ["0.0.0"]
    folder = volume_cache_dir(uri)
    assert folder.parent == cache_root and (folder / "0.0.0").is_file()
    assert (folder / "source.txt").read_text().strip() == uri
    # A second store on the same folder (e.g. a new napari session) reads nothing from the source.
    reads.clear()
    second = read_through_cache(source, uri, reads)
    assert reads == [] and np.array_equal(first, second)
    assert cache_size() > 0  # stored as read from the source (compressed here)


def test_each_volume_has_its_own_folder(cache_root):
    assert volume_cache_dir("s3://b/a.zarr") != volume_cache_dir("s3://b/b.zarr")
    assert volume_cache_dir("s3://b/a.zarr/") == volume_cache_dir("s3://b/a.zarr")


def test_disabled_cache_returns_the_source_store(source, cache_root, monkeypatch):
    monkeypatch.setenv("VESUVIUS_CACHE", "0")
    store = LocalStore(str(source), read_only=True)
    assert cached_store(store, "s3://bucket/volume.zarr") is store
    assert not cache_root.exists()


def test_missing_cache_store_falls_back_with_a_french_warning(source, cache_root, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def no_cache_store(name, *args, **kwargs):
        if name == "zarr.experimental.cache_store":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_cache_store)
    store = LocalStore(str(source), read_only=True)
    with pytest.warns(UserWarning, match="Cache local indisponible"):
        assert cached_store(store, "s3://bucket/volume.zarr") is store


def test_prune_removes_expired_then_least_recently_used_files(tmp_path):
    root = tmp_path / "chunks"
    now = time.time()
    ages = {"old": 40 * 24 * 3600, "a": 300, "b": 200, "c": 100}  # seconds since last use
    for name, age in ages.items():
        path = root / "volume" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * 1000)
        os.utime(path, (now - age, now - age))
    (root / "volume" / "source.txt").write_text("s3://b/v.zarr")
    freed = prune(root, max_bytes=2000, now=now)
    assert freed == 2000  # "old" expired (> 30 days), then "a", the least recently used
    left = sorted(p.name for p in (root / "volume").iterdir())
    assert left == ["b", "c", "source.txt"]
    assert MAX_AGE_S == 30 * 24 * 3600


def test_clear_cache_frees_everything(source, cache_root):
    read_through_cache(source, "s3://bucket/volume.zarr", [])
    size = cache_size()
    assert size > 0 and clear_cache() == size
    assert cache_size() == 0 and not cache_root.exists()


def test_invalid_size_limit_warns_and_uses_the_default(monkeypatch):
    monkeypatch.setenv("VESUVIUS_CACHE_MAX_GB", "beaucoup")
    with pytest.warns(UserWarning, match="VESUVIUS_CACHE_MAX_GB"):
        assert cache_module.max_cache_bytes() == 10 * 2**30
    monkeypatch.setenv("VESUVIUS_CACHE_MAX_GB", "0.5")
    assert cache_module.max_cache_bytes() == 2**29


def test_local_volumes_are_opened_as_zarr_arrays_without_cache(source, cache_root):
    arrays, levels = open_levels(str(source))
    assert isinstance(arrays[0], zarr.Array) and levels[0].shape == (32, 32, 32)
    assert estimate_contrast(arrays) is not None
    assert not cache_root.exists()


def test_remote_concurrency_setting(monkeypatch):
    from vesuvius_data_explorer.core.volume import set_remote_concurrency

    previous = zarr.config.get("async.concurrency")
    try:
        monkeypatch.delenv("VESUVIUS_ZARR_CONCURRENCY", raising=False)
        assert set_remote_concurrency() == 64 and zarr.config.get("async.concurrency") == 64
        monkeypatch.setenv("VESUVIUS_ZARR_CONCURRENCY", "16")
        assert set_remote_concurrency() == 16
        monkeypatch.setenv("VESUVIUS_ZARR_CONCURRENCY", "zéro")
        with pytest.warns(UserWarning, match="VESUVIUS_ZARR_CONCURRENCY"):
            assert set_remote_concurrency() == 64
    finally:
        zarr.config.set({"async.concurrency": previous})
