"""Official catalogue: parsing of the real metadata.json layout, local cache, network fallback."""

import gzip
import json
import os
import time

import pytest

from vesuvius_data_explorer.core import catalog as catalog_module
from vesuvius_data_explorer.core.catalog import format_um, load_catalog, parse_catalog

S3 = {"type": "s3", "url": "s3://vesuvius-challenge-open-data", "usage": "public-read"}
HTTPS = {"type": "https", "url": "https://data.aws.ash2txt.org", "usage": "public-read"}


def _volume(volume_id, entries, **props):
    properties = {
        "pixel_size_um": 2.399,
        "energy_keV": 78.0,
        "shape": [33592, 15761, 15761],
        "data_format": "uint8",
        "superseded_by": None,
        "license": {"name": "CC BY-NC 4.0", "url": "https://creativecommons.org/"},
    }
    properties.update(props)
    data = [
        {"type": kind, "origins": [{"path": path, "access_roots": roots} for path, roots in origins]}
        for kind, origins in entries
    ]
    return {"id": volume_id, "properties": properties, "data": data}


def fake_metadata():
    """Same layout as the real catalogue (see docs/investigations/I1-ecosysteme-donnees.md)."""
    return {
        "samples": {
            "PHerc0332": {
                "sample": {"id": "PHerc0332", "properties": {"type": "scroll"}},
                "volumes": {
                    "20251211183505": _volume(
                        "20251211183505",
                        [
                            ("ome-zarr", [("PHerc0332/volumes/a-2.399um-masked.zarr/", [S3])]),
                            # Derived artefact, not a volume pyramid.
                            ("surface-prediction-zarr", [("PHerc0332/pred.zarr/", [S3])]),
                        ],
                    ),
                    "20231027191953": _volume(
                        "20231027191953",
                        [("ome-zarr", [("samples/PHerc0332/volumes/b.zarr/", [HTTPS])])],
                        pixel_size_um=3.24,
                        shape=None,
                    ),
                },
            },
            "PHercParis4": {
                "sample": {"id": "PHercParis4", "properties": {"type": "scroll"}},
                "volumes": {
                    "20260310170716": _volume(
                        "20260310170716",
                        [
                            # Two copies of the same data: the public S3 one is preferred.
                            ("ome-zarr", [
                                ("samples/PHercParis4/volumes/c.zarr/", [HTTPS]),
                                ("PHercParis4/volumes/c.zarr/", [S3]),
                            ]),
                            ("ome-zarr-vcd3d", [("PHercParis4/volumes/c.vcd3d.zarr/", [S3])]),
                        ],
                        pixel_size_um=45.532,
                        energy_keV=74,
                    ),
                    "20260102150214": _volume(
                        "20260102150214",
                        [("ome-zarr", [("PHercParis4/volumes/d.zarr/", [S3])])],
                        superseded_by={"volume_id": "20260930100252", "reason": "remasked"},
                    ),
                    "20990101000000": _volume(
                        "20990101000000",
                        [("ome-zarr", [
                            ("x/e.zarr/", [{**HTTPS, "url": "https://evil.example"}]),
                            ("x/f.zarr/", [{**S3, "usage": "private"}]),
                        ])],
                    ),
                },
            },
            "Empty": {"sample": {"id": "Empty", "properties": {}}, "volumes": {}},
            "Broken": "not a sample",
        }
    }


def test_parse_keeps_openable_volume_copies_with_physical_metadata():
    catalog = parse_catalog(fake_metadata())
    assert catalog.samples() == ["PHerc0332", "PHercParis4"]
    by_name = {volume.name: volume for volume in catalog.volumes}
    assert set(by_name) == {"a-2.399um-masked.zarr", "b.zarr", "c.zarr", "c.vcd3d.zarr", "d.zarr"}

    scan = by_name["a-2.399um-masked.zarr"]
    assert scan.uri == "s3://vesuvius-challenge-open-data/PHerc0332/volumes/a-2.399um-masked.zarr"
    assert scan.sample_type == "scroll"
    assert scan.pixel_size_um == 2.399 and scan.energy_kev == 78.0
    assert scan.shape == (33592, 15761, 15761) and scan.dtype == "uint8"
    assert scan.license == "CC BY-NC 4.0" and scan.codec == "standard"
    assert scan.label == "20251211183505 — 2,399 µm — 78 keV"

    https = by_name["b.zarr"]
    assert https.uri == "https://data.aws.ash2txt.org/samples/PHerc0332/volumes/b.zarr"
    assert https.shape is None

    assert by_name["c.zarr"].uri == "s3://vesuvius-challenge-open-data/PHercParis4/volumes/c.zarr"
    vcd3d = by_name["c.vcd3d.zarr"]
    assert vcd3d.codec == "vc-delta3d" and vcd3d.label.endswith("[vc-delta3d]")

    old = by_name["d.zarr"]
    assert old.superseded_by == "20260930100252" and old.superseded_reason == "remasked"
    assert old.label.endswith("(remplacé)")


def test_volumes_of_orders_standard_copy_first_and_find_ignores_trailing_slash():
    catalog = parse_catalog(fake_metadata())
    names = [volume.name for volume in catalog.volumes_of("PHercParis4")]
    assert names == ["d.zarr", "c.zarr", "c.vcd3d.zarr"]
    found = catalog.find("s3://vesuvius-challenge-open-data/PHercParis4/volumes/c.zarr/")
    assert found is not None and found.codec == "standard"
    assert catalog.find("s3://elsewhere/c.zarr") is None


@pytest.mark.parametrize("data", [None, [], {"models": {}}, {"samples": []}])
def test_malformed_catalogue_is_reported_in_french(data):
    with pytest.raises(ValueError, match="Catalogue mal formé"):
        parse_catalog(data)


def test_format_um_uses_a_french_decimal_comma():
    assert format_um(2.399) == "2,399"
    assert format_um(8.0) == "8"


def test_local_catalogue_file_plain_or_gzip(tmp_path):
    raw = json.dumps(fake_metadata()).encode()
    plain = tmp_path / "metadata.json"
    plain.write_bytes(raw)
    packed = tmp_path / "metadata.json.gz"
    packed.write_bytes(gzip.compress(raw))
    assert len(load_catalog(str(plain)).volumes) == 5
    assert len(load_catalog(str(packed)).volumes) == 5
    with pytest.raises(FileNotFoundError, match="Catalogue introuvable"):
        load_catalog(str(tmp_path / "absent.json"))


@pytest.fixture
def remote(monkeypatch):
    """Count downloads of a gzip-served catalogue; ``fail`` simulates a network failure."""
    state = {"calls": 0, "fail": False}

    def fetch(uri):
        state["calls"] += 1
        if state["fail"]:
            raise OSError("network down")
        return gzip.compress(json.dumps(fake_metadata()).encode())

    monkeypatch.setattr(catalog_module, "_fetch", fetch)
    return state


def test_remote_catalogue_is_downloaded_once_then_served_from_cache(remote, tmp_path):
    first = load_catalog(cache_dir=tmp_path)
    second = load_catalog(cache_dir=tmp_path)
    assert remote["calls"] == 1
    assert first.volumes == second.volumes and not second.stale
    # The cache keeps the served gzip bytes, not the 4x larger decoded JSON.
    assert (tmp_path / "metadata.json").read_bytes()[:2] == b"\x1f\x8b"
    assert not list(tmp_path.glob("*.tmp"))


def test_expired_cache_or_refresh_downloads_again(remote, tmp_path):
    load_catalog(cache_dir=tmp_path)
    load_catalog(cache_dir=tmp_path, refresh=True)
    assert remote["calls"] == 2
    old = time.time() - 2 * catalog_module.DEFAULT_MAX_AGE_S
    os.utime(tmp_path / "metadata.json", (old, old))
    load_catalog(cache_dir=tmp_path)
    assert remote["calls"] == 3


def test_network_failure_falls_back_to_an_older_cached_copy(remote, tmp_path):
    load_catalog(cache_dir=tmp_path)
    remote["fail"] = True
    catalog = load_catalog(cache_dir=tmp_path, refresh=True)
    assert catalog.stale and len(catalog.volumes) == 5


def test_network_failure_without_cache_is_reported_in_french(remote, tmp_path):
    remote["fail"] = True
    with pytest.raises(ConnectionError, match="Catalogue officiel inaccessible"):
        load_catalog(cache_dir=tmp_path)


def test_corrupt_cache_is_downloaded_again(remote, tmp_path):
    (tmp_path / "metadata.json").write_bytes(b"\x1f\x8bnot gzip")
    catalog = load_catalog(cache_dir=tmp_path)
    assert remote["calls"] == 1 and len(catalog.volumes) == 5


def test_unwritable_cache_only_costs_a_later_download(remote, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    assert len(load_catalog(cache_dir=blocker / "cache").volumes) == 5
    assert len(load_catalog(cache_dir=blocker / "cache").volumes) == 5
    assert remote["calls"] == 2


def test_default_cache_dir_follows_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert catalog_module.default_cache_dir() == tmp_path / "vesuvius-data-explorer"


@pytest.mark.network
def test_real_catalogue_lists_known_volumes(tmp_path):
    catalog = load_catalog(cache_dir=tmp_path)
    scan = next(v for v in catalog.volumes if v.volume_id == "20251211183505")
    assert scan.sample_id == "PHerc0332" and scan.pixel_size_um == pytest.approx(2.399)
    assert scan.uri.startswith("s3://vesuvius-challenge-open-data/PHerc0332/volumes/")
    scroll1 = next(v for v in catalog.volumes if v.volume_id == "20230205180739")
    assert scroll1.uri.startswith("https://data.aws.ash2txt.org/")
    assert any(v.codec == "vc-delta3d" for v in catalog.volumes)
