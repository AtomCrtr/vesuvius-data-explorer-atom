"""In-memory cache of decoded chunks, for readers that request many overlapping boxes.

The alignment map (T10) reads one box per tile; neighbouring boxes share chunks, so without this
cache each chunk is fetched and decompressed several times. ``DecodedChunks`` wraps a 3D array
(Zarr, NumPy, Dask) and serves ``array[z0:z1, y0:y1, x0:x1]`` from whole chunks kept in a
thread-safe LRU of at most ``max_bytes``.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from itertools import product

import numpy as np

DEFAULT_DECODED_BYTES = 1 * 2**30


def _chunks(array) -> tuple[int, int, int]:
    chunks = getattr(array, "chunks", None)
    if chunks and all(isinstance(c, int) for c in chunks):
        return tuple(int(c) for c in chunks)
    if chunks and all(isinstance(c, tuple) for c in chunks):  # Dask: regular chunks assumed.
        return tuple(int(c[0]) for c in chunks)
    return (64, 64, 64)


class DecodedChunks:
    def __init__(self, array, max_bytes: int = DEFAULT_DECODED_BYTES):
        self.array = array
        self.shape = tuple(int(n) for n in array.shape)
        self.dtype = np.dtype(array.dtype)
        self.chunks = _chunks(array)
        self.max_bytes = max_bytes
        self._cache: OrderedDict = OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()
        self._loading: dict = {}
        self.decoded = 0  # Chunks read from the underlying array (for tests and reports).

    def _chunk(self, key):
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            event = self._loading.get(key)
            if event is None:
                event = self._loading[key] = threading.Event()
                owner = True
            else:
                owner = False
        if not owner:
            event.wait()
            with self._lock:
                if key in self._cache:
                    return self._cache[key]
            return self._chunk(key)  # Evicted meanwhile: read again.
        try:
            sl = tuple(slice(k * c, min((k + 1) * c, n))
                       for k, c, n in zip(key, self.chunks, self.shape))
            block = np.asarray(self.array[sl])
            with self._lock:
                self.decoded += 1
                self._cache[key] = block
                self._bytes += block.nbytes
                while self._bytes > self.max_bytes and len(self._cache) > 1:
                    _, old = self._cache.popitem(last=False)
                    self._bytes -= old.nbytes
            return block
        finally:
            with self._lock:
                self._loading.pop(key, None)
            event.set()

    def __getitem__(self, slices) -> np.ndarray:
        bounds = [(s.start or 0, self.shape[i] if s.stop is None else s.stop)
                  for i, s in enumerate(slices)]
        out = np.empty([b - a for a, b in bounds], dtype=self.dtype)
        ranges = [range(a // c, (b - 1) // c + 1) if b > a else range(0)
                  for (a, b), c in zip(bounds, self.chunks)]
        for key in product(*ranges):
            block = self._chunk(key)
            src, dst = [], []
            for (a, b), k, c in zip(bounds, key, self.chunks):
                lo, hi = max(a, k * c), min(b, (k + 1) * c)
                src.append(slice(lo - k * c, hi - k * c))
                dst.append(slice(lo - a, hi - a))
            out[tuple(dst)] = block[tuple(src)]
        return out


def sample_trilinear(array: DecodedChunks, coords: np.ndarray) -> np.ndarray:
    """Trilinear interpolation of ``array`` at (N, 3) voxel coordinates, reading only the chunks
    that hold the 8 neighbours of each sample (coordinates are clamped to the array, like
    ``ndimage.map_coordinates(..., mode="nearest")``)."""
    coords = np.asarray(coords, dtype=float)
    shape = np.asarray(array.shape)
    chunks = np.asarray(array.chunks)
    clamped = np.clip(coords, 0, shape - 1)
    base = np.minimum(np.floor(clamped).astype(np.int64), shape - 1)
    frac = clamped - base
    out = np.zeros(len(coords), dtype=np.float64)
    for corner in product((0, 1), repeat=3):
        corner = np.asarray(corner)
        index = np.minimum(base + corner, shape - 1)
        weight = np.prod(np.where(corner, frac, 1 - frac), axis=1)
        keys = index // chunks
        flat = np.ravel_multi_index(keys.T, tuple(-(-shape // chunks)))
        order = np.argsort(flat, kind="stable")
        unique, starts = np.unique(flat[order], return_index=True)
        bounds = list(starts[1:]) + [len(order)]
        for key_flat, start, stop in zip(unique, starts, bounds):
            members = order[start:stop]
            key = tuple(int(k) for k in keys[members[0]])
            block = array._chunk(key)
            local = index[members] - np.asarray(key) * chunks
            out[members] += weight[members] * block[local[:, 0], local[:, 1], local[:, 2]]
    return out
