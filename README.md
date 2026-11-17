# 📜 Vesuvius Data Explorer

**Open-source Python + Streamlit prototype for bounded exploration of Herculaneum scroll CT data and surface-coordinate diagnostics.**

[Official Vesuvius Challenge data](https://scrollprize.org/data) · [Data browser](https://scrollprize.org/data_browser) · [S3 layout documentation](https://github.com/ScrollPrize/open-data)

> **Independent community project.** Not affiliated with or endorsed by the Vesuvius Challenge. This project is not a virtual unwrapping system, a reading of ancient text, or an ink detector.

## Features in v0.1

- 🧪 A self-contained **synthetic demo** for immediate use (no external downloads).
- 🧊 Read a **local / public S3 OME-Zarr** 3D CT volume, select multiscale resolution, and stream a small slice ROI (max. 512 × 512) rather than the entire volume.
- 🖼️ Axial, coronal, sagittal 2D views; intensity percentiles, standard deviation and missing-pixel rate.
- 📐 Explore local **TIFXYZ-like** coordinate-grid patches (`x/y/z.npy` or memory-mappable `x/y/z.tif`) with missing-point %, median/p95 neighbor distances, and a heuristic for normal-direction inconsistency.
- ✅ Deterministic unit tests and GitHub Actions workflow.

### Run locally

Requires **Python 3.11+**.

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell:
# .venv\Scripts\Activate.ps1
python -m pip install -e .
streamlit run app.py
```

Start with **Démonstration synthétique** to see the app without any external data.

### Use real volumes

1. Visit the [official data browser](https://scrollprize.org/data_browser) or [S3 documentation](https://github.com/ScrollPrize/open-data).
2. Choose a **real sample**, and copy the full S3 path to an existing `.zarr` volume; the project intentionally does **not** hardcode a speculative sample URL.
3. In the app, select **OME-Zarr local / S3**, paste an URI such as `s3://vesuvius-challenge-open-data/<sample>/volumes/<scan>.zarr` (replace angle-bracket placeholders with actual artifact names), and start with the **coarsest** pyramid level.
4. Choose a slice and a 64–256 px window for a lighter remote request.

Public S3 access is configured with `anon=True`. A small requested ROI may still require downloading the complete compressed Zarr chunks intersecting it. Network access is needed for S3. Actual download size depends on chunk layout and selected pyramid level; no remote connection is attempted in demo mode. The app does not download the entire scan by design.

### Coordinate grids (surface geometry)

Select **Surfaces TIFXYZ**. You may work with the demo or an existing *small* local directory containing:

```
my-segment/
  x.npy   # or x.tif
  y.npy   # or y.tif
  z.npy   # or z.tif
```

For large TIFFs the prototype requires memory-mappable pages, to avoid silently loading huge compressed files. Convert a **small** crop to `.npy` using a dedicated tiling tool if necessary. Metrics use coordinate units from the source; they are **not in millimeters by default**. The normal flip ratio compares normals with a global patch reference and can flag natural bending, so it is **not a conclusive fold-over detector**.

### Limitations and scientific integrity

- Synthetic demos are labelled as synthetic, and must **not** be cited as real CT evidence.
- No segmentation training, ink recognition, papyrus text extraction, full surface quality validation or whole-scroll unwrapping in v0.1.
- `read_slice` bounds the **returned image** to ≤512×512, but Zarr chunk fetches can exceed that window.
- The full original CT datasets and any third-party licensed imagery **are not included** in this repository.
- Read the [data license and attribution requirements](https://scrollprize.org/data) before reusing real scans. The official portal notes CC BY-NC 4.0 unless otherwise stated, plus dataset-specific acknowledgements.

### Roadmap

- [ ] Dataset chooser based on the official catalog / stable artifact IDs
- [ ] ROI export with provenance JSON (sample, scan, Zarr level, ROI coordinates)
- [ ] Better surface QA: local normal consistency, self-intersections, topology, and validation on real labeled patches
- [ ] Chunk-aware latency/size instrumentation and cache measurements
- [ ] Reproducible scientific notebook with a genuinely licensed small sample

### Tests

```bash
python -m pip install -e '.[dev]'
pytest -q
```

### Attribution and references

- Vesuvius Challenge — [Data Formats](https://scrollprize.org/data)
- ScrollPrize — [Open Data documentation](https://github.com/ScrollPrize/open-data)
- ScrollPrize — [villa / vesuvius](https://github.com/ScrollPrize/villa)

Cite **the correct original dataset** for any published results (legacy EduceLab-Scrolls vs newer Vesuvius Challenge datasets), following the official [citation guidance](https://scrollprize.org/data). Code is MIT-licensed; this does **not** change the licenses of upstream datasets.
