"""Validate bounded public Vesuvius CT and TIFXYZ samples on Python and Rust."""

import argparse
import hashlib
import io
import os
from pathlib import Path
from time import perf_counter, thread_time
from unittest.mock import patch
from urllib.request import Request, urlopen

import dask.array as da
import numpy as np
import tifffile
import zarr
from rust_real_bench import dump
from scipy.ndimage import map_coordinates
from zarr.storage import FsspecStore

from vesuvius_data_explorer.core.alignment import grid_normals, level_factors
from vesuvius_data_explorer.core.chunkcache import DecodedChunks, _rust_sampler, sample_trilinear
from vesuvius_data_explorer.core.flatten import flatten
from vesuvius_data_explorer.core.tifxyz import load_tifxyz
from vesuvius_data_explorer.core.volume import open_levels, read_slice

S3 = "s3://vesuvius-challenge-open-data/PHercParis4/"
VOLUME = S3 + "volumes/20260310170716-45.532um-11.0m-74keV-masked"
V3 = VOLUME + "-fast-q1-c64-v0.3.2.vcd3d.zarr"
MASKED16 = ("https://data.aws.ash2txt.org/samples/PHercParis4/volumes/"
            "20230205180739-7.910um-54keV-masked.zarr")
TIFF = ("https://dl.ash2txt.org/full-scrolls/Scroll1/PHercParis4.volpkg/"
        "volumes/20230205180739")
MESH = S3 + "segments/20231005123336/mesh/20231005123336-on-"
SURFACE16 = MESH + "20230205180739-7.91um.tifxyz"
SURFACE_V3 = MESH + "20260310170716-45.532um-t2.tifxyz"


def digest(array):
    return hashlib.sha256(np.ascontiguousarray(array).view("u1")).hexdigest()


def tiff_range(url, start, stop):
    request = Request(url, headers={"Range": f"bytes={start}-{stop - 1}"})
    with urlopen(request, timeout=30) as response:
        expected = f"bytes {start}-{stop - 1}/"
        if response.status != 206 or not response.headers["Content-Range"].startswith(expected):
            raise ValueError(f"Server did not honor TIFF range: {url}")
        data = response.read(stop - start + 1)
        if len(data) != stop - start:
            raise ValueError(f"Incomplete TIFF range: {url}")
        return data, response.headers.get("ETag")


def read_uint16(lo, shape):
    z, y, x = lo
    nz, ny, nx = shape
    block = np.empty(shape, dtype=np.uint16)
    sources = []
    for i in range(nz):
        url = f"{TIFF}/{z + i:05d}.tif"
        header, etag = tiff_range(url, 0, 4096)
        with tifffile.TiffFile(io.BytesIO(header)) as tiff:
            page = tiff.pages[0]
            if (page.shape != (7888, 8096) or page.dtype != np.uint16 or not page.is_contiguous
                    or page.compression != 1 or page.predictor != 1
                    or page.tags.valueof("Orientation", 1) != 1):
                raise ValueError(f"Unexpected CT TIFF layout: {url}")
            start = page.dataoffsets[0] + y * page.shape[1] * 2
            end = start + ny * page.shape[1] * 2
            raw, body_etag = tiff_range(url, start, end)
            if etag != body_etag:
                raise ValueError(f"CT TIFF changed mid-read: {url}")
            rows = np.frombuffer(raw, dtype=tiff.byteorder + "u2").reshape(ny, page.shape[1])
            block[i] = rows[:, x:x+nx]
        sources.append({"url": url, "etag": etag, "data_range": [start, end],
                        "sha256_crop": digest(block[i])})
    return block, sources


def source_patch(surface, block_shape):
    """Choose a complete 2×2 UV cell fitting a bounded CT box with interpolation halo."""
    from numpy.lib.stride_tricks import sliding_window_view

    cells = sliding_window_view(surface.points, (2, 2), axis=(0, 1))
    low = cells.min(axis=(-1, -2))
    high = cells.max(axis=(-1, -2))
    valid = np.isfinite(low).all(axis=-1) & (low >= 2).all(axis=-1)
    valid &= ((high - low) <= np.asarray(block_shape) - 6).all(axis=-1)
    valid &= (high <= np.array([14369, 7888, 8096]) - 3).all(axis=-1)
    vu = np.argwhere(valid)
    v, u = vu[np.argmin(np.linalg.norm(vu - np.asarray(valid.shape) / 2, axis=1))]
    points = surface.points[v:v+2, u:u+2]
    center = np.rint(points.mean(axis=(0, 1))).astype(int)
    origin = np.maximum(center - np.asarray(block_shape) // 2, 0)
    return (int(v), int(u)), points, tuple(int(n) for n in origin)


def compare_render(arrays, levels, points, step, level):
    shapes = [item.shape for item in levels]
    renders = []
    for backend in ("0", "1"):
        with patch.dict(os.environ, {"VESUVIUS_RUST_SAMPLER": backend}):
            start = perf_counter()
            image = flatten(points, arrays, shapes, level=level, step_voxels=step,
                            normal_offsets=(-1.0, 0.0, 1.0))
            renders.append({"image": image, "ms": (perf_counter() - start) * 1000})
    py, rust = (row["image"] for row in renders)
    assert py.shape == rust.shape and py.dtype == rust.dtype == np.float32
    assert np.isfinite(py).any()
    np.testing.assert_array_equal(np.isnan(py), np.isnan(rust))
    np.testing.assert_allclose(py, rust, atol=0.004, rtol=0)
    return {"shape": py.shape, "finite": int(np.isfinite(py).sum()), "dtype": str(py.dtype),
            "range": [float(np.nanmin(py)), float(np.nanmax(py))],
            "sha256_python": digest(py), "sha256_rust": digest(rust),
            "max_error_ct": float(np.nanmax(np.abs(py - rust))),
            "python_ms": renders[0]["ms"], "rust_ms": renders[1]["ms"]}


def verify_tiff_origin(block, low):
    """Use the published masked copy to check the original TIFF frame in the crop."""
    arrays, levels = open_levels(MASKED16, cache=False)
    z, y, x = (int(n) for n in low)
    depth, height, width = block.shape
    radius = 128
    slab = arrays[0][z-radius:z+depth+radius, y:y+height, x:x+width]
    scores = []
    for offset in range(-radius, radius + 1):
        ref = slab[radius+offset:radius+offset+depth]
        mask = ref > 0
        if mask.sum() > 100:
            score = float(np.corrcoef(block[mask], ref[mask])[0, 1])
            scores.append({"offset_z": offset, "pearson": score, "voxels": int(mask.sum())})
    best = max(scores, key=lambda row: row["pearson"])
    assert best["offset_z"] == 0 and best["pearson"] > 0.995
    ref = slab[radius:radius+depth]
    mask = ref > 0
    orientations = {name: float(np.corrcoef(flipped[mask], ref[mask])[0, 1])
                    for name, flipped in (("flip_x", block[..., ::-1]),
                                          ("flip_y", block[:, ::-1, :]),
                                          ("swap_yx", block.swapaxes(1, 2)))}
    assert best["pearson"] > max(orientations.values())
    return {"masked_reference": MASKED16, "masked_shape_zyx": levels[0].shape,
            "best_offset": best, "axial_offsets": scores, "xy_controls": orientations,
            "slab_sha256": digest(slab)}


def uint16_case(work):
    from vc_delta3d.zarr3 import Delta3DCodec
    from zarr.codecs import BytesCodec

    surface = load_tifxyz(SURFACE16)
    shape = (32, 48, 48)
    uv, points, low = source_patch(surface, shape)
    block, sources = read_uint16(low, shape)
    assert block.max() > 255 and block.min() < block.max()
    path = work / "uint16.zarr"
    pyramid = zarr.open_group(str(path), mode="w", zarr_format=3)
    levels_spec = []
    reference = [block, block[::2, ::2, ::2]]
    for index, pixels in enumerate(reference):
        key = str(index)
        factor = 2**index
        pyramid.create_array(key, data=pixels, chunks=tuple(c // factor for c in (8, 16, 16)),
                             shards=tuple(c // factor for c in (16, 32, 32)),
                             serializer=BytesCodec(endian="little"),
                             compressors=Delta3DCodec(predictor="fast", quant=1))
        levels_spec.append({"path": key, "coordinateTransformations": [
            {"type": "scale", "scale": [factor] * 3}]})
    pyramid.attrs["ome"] = {"version": "0.5", "multiscales": [
        {"axes": [{"name": axis, "type": "space"} for axis in "zyx"], "datasets": levels_spec}]}
    pyramid.attrs["source_crop_origin_zyx"] = low
    arrays, levels = open_levels(str(path))
    assert tuple(pyramid.attrs["source_crop_origin_zyx"]) == low
    rows = []
    for index, (array, level, pixels) in enumerate(zip(arrays, levels, reference)):
        assert array.shards == tuple(c // 2**index for c in (16, 32, 32))
        assert level.dtype == "uint16" and level.shape == pixels.shape
        assert level.scale == (float(2**index),) * 3
        np.testing.assert_array_equal(array[:], pixels, strict=True)
        i = 16 // 2**index
        roi = read_slice(da.from_zarr(array), "y", i, i - 2, i - 2, 5, 7)
        np.testing.assert_array_equal(roi, pixels[i-2:i+3, i, i-2:i+5], strict=True)
        # Fractional points on both sides of chunk boundaries, checked independently.
        coords = np.array(list(np.ndindex(2, 2, 2)), dtype=float)
        coords += np.asarray(array.chunks, dtype=float) - 1.25
        exact = map_coordinates(pixels.astype(np.float64), coords.T, order=1, mode="nearest")
        for backend in ("0", "1"):
            with patch.dict(os.environ, {"VESUVIUS_RUST_SAMPLER": backend}):
                sampled = sample_trilinear(DecodedChunks(array), coords)
                np.testing.assert_allclose(sampled, exact, rtol=0, atol=1e-8)
        rows.append({"level": index, "shape": level.shape, "dtype": level.dtype,
                     "scale": level.scale, "chunks": level.chunks, "shards": array.shards,
                     "sha256": digest(pixels), "roi_sha256": digest(roi),
                     "render": compare_render(arrays, levels, points - low, surface.step_voxels,
                                              index)})
    return {"surface": SURFACE16, "surface_meta": surface.meta, "surface_uv": uv,
            "surface_zyx": points.tolist(), "surface_sha256": digest(points),
            "origin_zyx": low, "shape": shape, "tiffs": sources,
            "range": [int(block.min()), int(block.max())], "levels": rows,
            "tiff_frame": verify_tiff_origin(block, low)}


def published_v3_case():
    arrays, levels = open_levels(V3, cache=False)
    standard, reference_levels = open_levels(VOLUME + ".zarr", cache=False)
    surface = load_tifxyz(SURFACE_V3)
    assert levels[0].shape == (4071, 2264, 2264) and levels[0].dtype == "uint8"
    assert levels[0].chunks == (64, 64, 64) and arrays[0].shards == (1024,) * 3
    assert len(levels) == 8
    events = []
    original = FsspecStore.get
    phase = ""

    async def trace(store, key, prototype, byte_range=None):
        if len(events) >= 400:
            raise RuntimeError("Chunk/range budget exceeded")
        start = perf_counter()
        value = await original(store, key, prototype, byte_range)
        events.append({"phase": phase, "key": key, "range": repr(byte_range),
                       "bytes": len(value) if value is not None else 0,
                       "ms": (perf_counter() - start) * 1000})
        return value

    rows = []
    with patch.object(FsspecStore, "get", trace):
        for index, center in ((0, (3072, 1024, 1024)), (1, (1536, 512, 512)),
                              (3, (384, 128, 128))):
            array, level = arrays[index], levels[index]
            center = np.array(center)
            region = tuple(slice(c - 3, c + 5) for c in center)
            phase = f"v3_l{index}_direct"
            voxels = array[region]
            phase = f"v3_l{index}_dask"
            graph = da.from_zarr(array)
            assert tuple(c[0] for c in graph.chunks) == level.chunks
            np.testing.assert_array_equal(graph[region].compute(), voxels, strict=True)
            assert voxels.max() > 0 and level.scale == (float(2**index),) * 3
            phase = f"v2_l{index}"
            ref = standard[index][region]
            np.testing.assert_array_equal(ref, voxels, strict=True)
            assert reference_levels[index].shape == level.shape
            rows.append({"level": index, "boundary_zyx": center.tolist(), "shape": level.shape,
                         "chunks": level.chunks, "shards": array.shards, "scale": level.scale,
                         "dtype": level.dtype, "sha256": digest(voxels),
                         "decoded_range": [int(voxels.min()), int(voxels.max())]})

        target = np.asarray((3072, 1024, 1024))
        v, u = np.unravel_index(np.nanargmin(
            np.linalg.norm(surface.points[1:-1, 1:-1] - target, axis=-1)),
            (surface.grid_shape[0] - 2, surface.grid_shape[1] - 2))
        patch_points = surface.points[v:v+3, u:u+3]
        assert np.isfinite(grid_normals(patch_points)).all()
        for row in rows:
            index = row["level"]
            phase = f"v3_l{index}_surface"
            row["render"] = compare_render(arrays, levels, patch_points, surface.step_voxels, index)
            factor = level_factors([n.shape for n in levels])[index]
            expected = np.asarray(levels[index].scale) / levels[0].scale
            legacy = (patch_points + 0.5) / factor - 0.5
            ngff = patch_points / expected
            row["max_legacy_vs_ngff_voxel"] = np.abs(legacy - ngff).max(axis=(0, 1)).tolist()
    return {"volume": V3, "reference": VOLUME + ".zarr", "surface": SURFACE_V3,
            "surface_meta": surface.meta, "surface_uv": [int(v), int(u)],
            "surface_zyx": patch_points.tolist(), "surface_sha256": digest(patch_points),
            "levels": rows, "reads": events}


def main():
    from vc_delta3d.zarr3 import Delta3DCodec

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    if _rust_sampler() is None:
        raise RuntimeError("Build/install the optional Rust wheel before running parity")
    zarr.config.set({"async.concurrency": 64})
    result = {"zarr": zarr.__version__, "numpy": np.__version__, "float32_atol_ct": 0.004,
              "float64_atol_ct": 1e-8, "rtol": 0}
    original_decode = Delta3DCodec._decode_sync
    events = []
    start = perf_counter()

    def decode(codec, encoded, spec):
        begin, cpu = perf_counter(), thread_time()
        values = original_decode(codec, encoded, spec)
        events.append({"start_ms": (begin - start) * 1000, "wall_ms": (perf_counter() - begin) * 1000,
                       "thread_cpu_ms": (thread_time() - cpu) * 1000,
                       "encoded_bytes": len(encoded), "shape": spec.shape})
        return values

    with patch.object(Delta3DCodec, "_decode_sync", decode):
        result["uint16"] = {**uint16_case(args.work), "codec_decode": events.copy()}
        dump(args.output, result)
        events.clear()
        result["published_v3"] = {**published_v3_case(), "codec_decode": events}
        dump(args.output, result)


if __name__ == "__main__":
    main()
