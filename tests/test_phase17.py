"""Offline controls for the phase 17 protocol and PNG readers."""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image


@pytest.fixture
def phase(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "docs/validation"))
    import phase17_orientation
    return phase17_orientation


@pytest.mark.parametrize("low_noise, expected", [(1, "low"), (8, "indéterminé")])
def test_orientation_with_brighter_air(phase, low_noise, expected):
    checker = np.indices((64, 64)).sum(0) % 2
    mapping = dict(zip([*range(13), *range(52, 65)], [*range(2, 15), *range(51, 64)]))
    samples = {k: {(0, 0): 180 + low_noise*checker if k < 15 else 40 + 10*checker}
               for k in mapping.values()}
    result = phase.summarize(samples, np.ones((64, 64), bool), [(16, 16)], mapping, 2)
    assert result["air"] == expected
    assert result["ratio"] == pytest.approx(10 / low_noise)


def test_frozen_protocol(phase, tmp_path):
    path = tmp_path / phase.PROTOCOL.name
    path.write_bytes(phase.PROTOCOL.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert phase.read_protocol(path)["minimum_ratio"] == 2
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError):
        phase.read_protocol(path)


def test_row_and_full_png(phase, tmp_path):
    plane = np.random.default_rng(0).integers(256, size=(128, 156), dtype=np.uint8)
    path = tmp_path / "test.png"
    Image.fromarray(plane).save(path)
    boxes = [(0, 92), (62, 13), (64, 0)]
    full = phase.full_patches(path, boxes)
    streamed = phase.stream_patches(path, boxes)
    for r, c in boxes:
        np.testing.assert_array_equal(streamed[r, c], full[r, c])
        np.testing.assert_array_equal(streamed[r, c], plane[r:r+64, c:c+64])
