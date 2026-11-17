"""Opt-in public S3 metadata check; never substitute a guessed artifact URI."""

import os
from urllib.parse import urlsplit

import pytest

from vesuvius_data_explorer.volume import list_levels, open_volume_store


@pytest.mark.network
def test_public_vesuvius_volume():
    uri = os.environ.get("VESUVIUS_TEST_ZARR", "").strip()
    if not uri:
        pytest.skip("VESUVIUS_TEST_ZARR absente : aucun volume réel configuré.")
    parsed = urlsplit(uri)
    assert parsed.scheme == "s3" and parsed.netloc == "vesuvius-challenge-open-data", (
        "VESUVIUS_TEST_ZARR doit désigner un volume S3 public du bucket officiel."
    )
    assert parsed.path.strip("/"), "Un chemin de volume est requis, pas la racine du bucket."
    print(f"VESUVIUS_TEST_ZARR={uri}")
    levels = list_levels(open_volume_store(uri))
    assert levels
    assert all(len(level.shape) == 3 and min(level.shape) > 0 for level in levels)
    assert all(len(level.chunks) == 3 and min(level.chunks) > 0 for level in levels)
