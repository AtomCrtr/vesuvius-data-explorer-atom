# Vesuvius Data Explorer

Explore and quality-check the CT scans of the Herculaneum scrolls published by the
[Vesuvius Challenge](https://scrollprize.org), without downloading whole volumes.
*Explorer et contrôler la qualité des scans des rouleaux d'Herculanum ; interface en français.*

## What it does

- **Open a scan from the official catalogue** (sample → volume, voxel size in µm), or any local,
  public S3 or official HTTPS OME-Zarr volume. Lazy multiscale reading with a local chunk cache.
- **Volume quality control**: level consistency, saturation, empty areas, contrast, with every
  anomaly drawn on the image and one click to navigate to it.
- **VC3D segments (tifxyz)**: overlay the segment trace on the current slice, interior holes, folds,
  stretch, points outside the volume, and a calibrated **surface-to-sheet alignment** measure.
- **Command line** `vesuvius-qc`, including a batch check of every catalogued segment of a volume
  with an HTML / CSV / JSON summary.

## Getting started

```bash
pip install "vesuvius-data-explorer[napari]"
napari -w vesuvius-data-explorer
```

Then **Load the official catalogue**, choose a sample and a volume, and **Open**. See the
[user guide (French)](https://github.com/AtomCrtr/vesuvius-data-explorer-atom/blob/main/docs/guide.md).

Independent community project, not affiliated with the Vesuvius Challenge. Code under MIT; the
scans keep their own licence (CC BY-NC 4.0 unless stated otherwise).
