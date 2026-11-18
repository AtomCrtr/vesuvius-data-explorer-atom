"""Batch QC (T7): every segment of a volume, failures isolated, JSON / CSV / HTML summary."""

import json

import numpy as np
import pytest
import zarr

from vesuvius_data_explorer.core.alignment import grid_normals
from vesuvius_data_explorer.core.catalog import Catalog, CatalogSegment, CatalogVolume
from vesuvius_data_explorer.qc.batch import run_batch, to_csv, to_html

SPACING = 24


@pytest.fixture
def setup(tmp_path):
    """Sheets every 24 voxels (bright at z = 0, 24, 48, 72) and three segments."""
    z = np.arange(96)[:, None, None]
    volume = (50 + 100 * np.exp(-(((z + 12) % SPACING - 12) ** 2) / 8.0)
              + np.random.default_rng(0).normal(0, 5, (96, 64, 64))).astype(np.float32)
    path = tmp_path / "sheets.zarr"
    root = zarr.open_group(str(path), mode="w", zarr_format=2)
    datasets = []
    level = volume
    for index in range(3):
        root.create_array(str(index), shape=level.shape, dtype="float32", chunks=(16, 32, 32))
        root[str(index)][:] = level
        datasets.append({"path": str(index), "coordinateTransformations": [
            {"type": "scale", "scale": [2.0**index] * 3}]})
        s = [n // 2 * 2 for n in level.shape]
        level = level[:s[0], :s[1], :s[2]].reshape(
            s[0] // 2, 2, s[1] // 2, 2, s[2] // 2, 2).mean(axis=(1, 3, 5))
    root.attrs["multiscales"] = [{"axes": ["z", "y", "x"], "datasets": datasets}]

    def segment(name, shift):
        row, col = np.mgrid[:30, :30].astype(float)
        points = np.stack([np.full_like(row, 48.0), 2 * row + 2, 2 * col + 2], axis=-1)
        points = points + shift * grid_normals(points)  # normal is -z: sheet at offset -shift
        folder = tmp_path / name
        folder.mkdir()
        for axis, file in enumerate("zyx"):
            np.save(folder / f"{file}.npy", points[..., axis])
        return CatalogSegment("S", name, name, "V1", str(folder), 1.0, None, False)

    volume_entry = CatalogVolume("S", "scroll", "V1", "sheets.zarr", str(path), "standard",
                                 5.0, 80.0, (96, 64, 64), "float32", "CC BY-NC 4.0", None, None)
    segments = (segment("aligned", 0), segment("shifted", 10),
                CatalogSegment("S", "missing", "missing", "V1", str(tmp_path / "absent"),
                               None, None, False))
    return Catalog((volume_entry,), "test", segments=segments)


def test_batch_grades_every_segment_and_isolates_failures(setup, tmp_path):
    seen = []
    summary = run_batch(setup, "V1", workers=2, reports_dir=tmp_path / "rapports",
                        progress=lambda done, total, row: seen.append((done, total)))
    rows = {row["segment"]: row for row in summary["rows"]}
    assert rows["missing"]["status"] == "error" and "Grille introuvable" in rows["missing"]["error"]
    # 10 voxels of 5 µm = 50 µm from the sheet: graded alert (T5.3).
    assert rows["shifted"]["checks"]["surface.alignment"]["status"] == "warn"
    assert rows["shifted"]["status"] == "warn"
    assert rows["aligned"]["checks"]["surface.alignment"]["status"] == "pass"
    assert rows["aligned"]["status"] == "pass"
    assert [row["segment"] for row in summary["rows"]] == ["missing", "shifted", "aligned"]
    assert summary["summary"]["segments"] == {"error": 1, "fail": 0, "warn": 1, "pass": 1,
                                              "skipped": 0}
    assert summary["summary"]["checks"]["surface.alignment"]["warn"] == 1
    assert sorted(seen) == [(1, 3), (2, 3), (3, 3)]
    assert sorted(p.name for p in (tmp_path / "rapports").iterdir()) == ["aligned.json",
                                                                          "shifted.json"]
    json.dumps(summary, allow_nan=False)


def test_batch_without_alignment_and_with_a_segment_limit(setup):
    summary = run_batch(setup, "V1", max_segments=2, alignment=False)
    assert summary["parameters"]["segments"] == 2
    for row in summary["rows"]:
        assert row["checks"]["surface.alignment"]["status"] == "skipped"


def test_batch_errors_are_french(setup):
    with pytest.raises(ValueError, match="Volume absent du catalogue"):
        run_batch(setup, "inconnu")
    empty = Catalog(setup.volumes, "test", segments=())
    with pytest.raises(ValueError, match="Aucun segment publié"):
        run_batch(empty, "V1")
    with pytest.raises(ValueError, match="tâches parallèles"):
        run_batch(setup, "V1", workers=0)


def test_csv_and_html_are_complete_and_escaped(setup):
    summary = run_batch(setup, "V1", alignment=False)
    summary["rows"][0]["error"] = "<script>alert(1)</script>"
    csv_text = to_csv(summary)
    assert csv_text.splitlines()[0].startswith("segment,statut,secondes")
    assert len(csv_text.splitlines()) == 4
    html = to_html(summary)
    assert "<script>alert" not in html and "&lt;script&gt;" in html
    assert "QC en lot — S V1" in html


def test_cli_lot_writes_the_three_summaries(setup, tmp_path, monkeypatch, capsys):
    from vesuvius_data_explorer.cli import main
    from vesuvius_data_explorer.core import catalog as catalog_module

    monkeypatch.setattr(catalog_module, "load_catalog", lambda *args, **kwargs: setup)
    output = tmp_path / "lot"
    assert main(["lot", "V1", "-o", str(output), "--workers", "2"]) == 1  # one error row
    assert {p.name for p in output.iterdir()} == {"synthese.json", "synthese.csv",
                                                  "synthese.html", "rapports"}
    err = capsys.readouterr().err
    assert "[3/3]" in err and "synthese.html" in err
    assert json.loads((output / "synthese.json").read_text())["volume"]["volume_id"] == "V1"
