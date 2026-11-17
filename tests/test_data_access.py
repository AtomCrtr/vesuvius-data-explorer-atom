"""T4.1: official HTTPS hosts, translated not-found errors and unknown codecs."""

import json
import warnings

import numpy as np
import pytest
import zarr
from zarr.storage import LocalStore

from vesuvius_data_explorer.core import volume
from vesuvius_data_explorer.core.volume import list_levels, open_volume_store

SCROLL1 = ("https://data.aws.ash2txt.org/samples/PHercParis4/volumes/"
           "20230205180739-7.910um-54keV-masked.zarr")


def _pyramid(path, zarr_format=2):
    root = zarr.open_group(str(path), mode="w", zarr_format=zarr_format)
    datasets = []
    for index, side in enumerate((32, 16)):
        array = root.create_array(str(index), shape=(side,) * 3, chunks=(8,) * 3, dtype="uint8")
        array[:] = 7
        datasets.append({"path": str(index), "coordinateTransformations": [
            {"type": "scale", "scale": [2.0 ** index] * 3}]})
    root.attrs["multiscales"] = [{"axes": ["z", "y", "x"], "datasets": datasets}]
    return root


@pytest.fixture
def fake_http(monkeypatch, tmp_path):
    """Serve ``FsspecStore.from_url`` from a local directory and record the calls."""
    calls = []

    def from_url(url, storage_options=None, read_only=False):
        calls.append((url, storage_options, read_only))
        return LocalStore(str(tmp_path / "served.zarr"), read_only=True)

    monkeypatch.setattr(zarr.storage.FsspecStore, "from_url", staticmethod(from_url))
    return tmp_path / "served.zarr", calls


def test_official_https_host_is_opened_read_only(fake_http):
    path, calls = fake_http
    _pyramid(path)
    levels = list_levels(open_volume_store(SCROLL1 + "/"))
    assert [level.key for level in levels] == ["0", "1"]
    assert calls == [(SCROLL1, None, True)]


@pytest.mark.parametrize("url", [
    "https://example.org/volume.zarr",
    "http://data.aws.ash2txt.org/samples/x.zarr",
    "https://data.aws.ash2txt.org.evil.example/x.zarr",
])
def test_other_https_hosts_and_plain_http_are_refused(url, fake_http):
    _, calls = fake_http
    with pytest.raises(ValueError, match="URL HTTPS officielle.*data.aws.ash2txt.org"):
        open_volume_store(url)
    assert calls == []


def test_missing_remote_volume_is_a_french_not_found(fake_http):
    path, _ = fake_http
    path.mkdir()
    with pytest.raises(FileNotFoundError, match="Volume introuvable : https://data"):
        open_volume_store(SCROLL1)


def _with_codec(path, codec):
    """A zarr v3 OME pyramid whose arrays declare ``codec`` (data never decoded)."""
    root = _pyramid(path, zarr_format=3)
    root.attrs["ome"] = {"version": "0.5", "multiscales": root.attrs["multiscales"]}
    for key in ("0", "1"):
        meta_path = path / key / "zarr.json"
        meta = json.loads(meta_path.read_text())
        meta["codecs"] = [{"name": "bytes"}, {"name": codec, "configuration": {}}]
        meta_path.write_text(json.dumps(meta))


def test_vc_delta3d_without_package_gives_install_hint_not_bad_metadata(tmp_path):
    try:
        import vc_delta3d  # noqa: F401
        pytest.skip("vc-delta3d est installé : le codec est connu.")
    except ImportError:
        pass
    _with_codec(tmp_path / "v.zarr", "vc-delta3d")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with pytest.raises(ValueError, match=r"« vc-delta3d ».*\[vcdelta3d\]"):
            list_levels(open_volume_store(str(tmp_path / "v.zarr")))
    assert not [w for w in caught if "mal formées" in str(w.message)]


@pytest.mark.parametrize("message", [
    "Unknown codec: 'vc-delta3d'",                                  # zarr 3.1
    "An implementation for codec 'vc-delta3d' is not available.",   # zarr 3.4
])
def test_codec_name_is_read_from_both_zarr_message_formats(message):
    error = type("UnknownCodecError", (ValueError,), {})(message)
    assert "« vc-delta3d »" in str(volume._codec_error(error))
    assert "[vcdelta3d]" in str(volume._codec_error(error))


def test_unknown_codec_without_metadata_gives_generic_hint(tmp_path):
    path = tmp_path / "v.zarr"
    _with_codec(path, "codec-inexistant")
    root = zarr.open_group(str(path), mode="r+")
    root.attrs.clear()
    with pytest.raises(ValueError, match="« codec-inexistant ».*paquet Python"):
        list_levels(open_volume_store(str(path)))


def test_vc_delta3d_volume_round_trip_when_installed(tmp_path):
    pytest.importorskip("vc_delta3d")
    from vc_delta3d.zarr3 import Delta3DCodec
    from zarr.codecs import BytesCodec

    data = np.random.default_rng(0).integers(0, 255, (64, 64, 64), dtype=np.uint8)
    root = zarr.open_group(str(tmp_path / "c.zarr"), mode="w", zarr_format=3)
    array = root.create_array("0", shape=data.shape, dtype="uint8", shards=(64, 64, 64),
                              chunks=(32, 32, 32), serializer=BytesCodec(endian="little"),
                              compressors=Delta3DCodec(predictor="fast"))
    array[:] = data
    root.attrs["ome"] = {"version": "0.5", "multiscales": [{"axes": ["z", "y", "x"], "datasets": [
        {"path": "0", "coordinateTransformations": [{"type": "scale", "scale": [1, 1, 1]}]}]}]}
    arrays, levels = volume.open_multiscale(str(tmp_path / "c.zarr"))
    roi = volume.read_slice(arrays[0], "z", 10, 0, 0, width=64)
    np.testing.assert_array_equal(roi, data[10])


@pytest.mark.network
def test_scroll1_over_official_https():
    levels = list_levels(open_volume_store(SCROLL1))
    assert len(levels) == 6 and levels[0].shape == (14258, 7888, 8096)


@pytest.mark.network
def test_real_vcd3d_volume_when_installed():
    """A catalogued vc-delta3d copy (PHercParis4, 45.5 µm) decodes like any other volume."""
    pytest.importorskip("vc_delta3d")
    uri = ("s3://vesuvius-challenge-open-data/PHercParis4/volumes/"
           "20260310170716-45.532um-11.0m-74keV-masked-fast-q1-c64-v0.3.2.vcd3d.zarr")
    arrays, levels = volume.open_multiscale(uri)
    assert levels[0].shape == (4071, 2264, 2264)
    z, y, x = levels[-1].shape
    roi = volume.read_slice(arrays[-1], "z", z // 2, y // 2 - 32, x // 2 - 32, width=64)
    assert roi.shape == (64, 64) and roi.max() > 0
