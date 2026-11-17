# 📜 Vesuvius Data Explorer

**Interface-independent Python core for bounded exploration of Herculaneum scroll CT data and surface-coordinate diagnostics, with an optional Streamlit demo.**

napari is the primary exploration interface ([ADR 0001](docs/adr/0001-napari-interface-principale.md)).
The existing Streamlit demo is frozen; the QC CLI is a separate task.

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
python -m pip install -e '.[streamlit]'
streamlit run app.py
```

Start with **Démonstration synthétique** to see the app without any external data.

For the core only, use `python -m pip install -e .`. This installs NumPy, Zarr, fsspec,
s3fs, tifffile and Dask, without Streamlit, matplotlib, napari or Qt.

### Explorer avec napari

```bash
python -m pip install -e '.[napari]'
napari -w vesuvius-data-explorer
```

Dans le widget **Vesuvius — Ouvrir un volume**, saisir le chemin d'un dossier local
`/chemin/volume.zarr` ou une URI S3 publique puis cliquer sur **Ouvrir**. Un dossier local
`.zarr` peut aussi être glissé dans napari. Le protocole lecteur npe2 est synchrone :
les métadonnées et la petite coupe de contraste peuvent donc retarder un glisser-déposer ;
utiliser le widget pour une ouverture en arrière-plan. Les URI S3 passent uniquement par le widget ;
les URL HTTPS ne sont pas prises en charge.

Exemple réel vérifié dans le [bucket public officiel](https://github.com/ScrollPrize/open-data),
pour le volume PHerc0332 (l'accès et les noms peuvent évoluer) :

```text
s3://vesuvius-challenge-open-data/PHerc0332/volumes/20251211183505-2.399um-0.2m-78keV-masked.zarr
```

Dans le widget, l'ouverture des métadonnées et l'estimation du contraste s'exécutent
dans un thread de travail.
Le bouton reste désactivé pendant cette étape. Le plugin active la préférence napari
**Render Layers Asynchronously** pour empêcher les lectures de vue sur le thread graphique ;
elle peut être désactivée dans les Préférences, au prix de lectures alors bloquantes. Le tableau affiche niveau, forme, dtype, chunks,
échelle et taille estimée avant compression. Le calque unique conserve les tableaux Dask
multi-échelles, l'échelle du niveau le plus fin en **(z, y, x)**, l'URI source et le résumé.
Le contraste est explicite : percentiles 1/99 d'une seule coupe centrale du niveau le plus
grossier, bornée à 512 × 512 ; les valeurs non finies sont ignorées et une coupe vide ou
constante utilise les bornes du dtype. Ajuster ensuite le contraste dans napari si nécessaire.

Limites connues : les chunks téléchargés peuvent dépasser la fenêtre de contraste ; le premier
rendu et la navigation demandent des lectures supplémentaires selon la vue et le réseau.
En 3D, napari affiche le niveau le plus grossier du multi-échelles. La fluidité 2D dépend de
la taille des chunks, du GPU et de la connexion. Qt et un environnement graphique local sont
nécessaires ; l'installation du cœur seul reste sans dépendance graphique.

### Use the core without a GUI

```python
import json
import os

from vesuvius_data_explorer.core.volume import open_multiscale, read_slice, volume_summary

# Set this variable to a local Zarr path or an exact public S3 URI from the official catalog.
arrays, levels = open_multiscale(os.environ["VESUVIUS_TEST_ZARR"])
print(json.dumps(volume_summary(levels), indent=2))
roi = read_slice(arrays[-1], axis="z", index=0, start_a=0, start_b=0, width=64)
```

`open_multiscale` returns Dask arrays and frozen `Level` records, from finest to coarsest
(descending voxel count). Opening, listing levels and summarizing read metadata only; they
do not read voxel chunks. `read_slice` computes only the requested 2D window, at most 512×512.
Calling `.compute()` on an entire Dask level explicitly materializes that entire level;
slice it first. Storage chunks intersecting a small ROI can still be larger than the ROI.

Shapes, chunks and scales use **(z, y, x)**. Both **OME-NGFF 0.4** (root `multiscales`)
and **OME-NGFF 0.5** (`ome.multiscales`) metadata layouts are supported. The `ome` namespace
takes precedence when present; an invalid namespace warns and falls back to group arrays,
rather than silently selecting conflicting 0.4 metadata. `scale` combines each dataset's
`coordinateTransformations` with any pyramid-level scale; its units remain those of the source
metadata. Explicitly
different axis orders are rejected. If axes are absent, the legacy ZYX convention is assumed.
Missing multiscale metadata falls back to group arrays (including numeric `0`, `1`, `2`),
with scale `(1.0, 1.0, 1.0)`. Numeric fallback without metadata and malformed metadata emit
French warnings; unit scales are not physical measurements and do not establish voxel spacing.
The first OME pyramid is used when several exist.
Both Zarr v2 and v3 stores are supported through the Zarr 3 Python API.

`volume_summary` returns `level_count` and a `levels` list containing `key`, `shape`, `dtype`,
`chunks`, `scale` and `estimated_bytes` (voxel count × dtype item size, before compression).
The old `vesuvius_data_explorer.volume`, `.surface` and `.demo` imports remain as deprecated
compatibility reexports; new code should import from `.core`.

### Use real volumes

1. Visit the [official data browser](https://scrollprize.org/data_browser) or [S3 documentation](https://github.com/ScrollPrize/open-data).
2. Choose a **real sample**, and copy the full S3 path to an existing `.zarr` volume; the project intentionally does **not** hardcode a speculative sample URL.
3. In the app, select **OME-Zarr local / S3**, paste the exact URI copied from the official source, and start with the **coarsest** pyramid level.
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
ruff check .
```

The default suite uses synthetic data and temporary local Zarr stores, with no network
access required. Les tests de widget sont ignorés si napari est absent (`pytest.importorskip`).
Un job CI `napari` séparé installe `.[napari,dev]` et `pytest-qt`, valide le manifeste npe2
et exécute la suite avec Qt sous affichage virtuel Xvfb (le backend offscreen de PyQt6 ne fournit pas toujours
un contexte OpenGL). Pour le reproduire :

```bash
python -m pip install -e '.[napari,dev]' pytest-qt
npe2 validate vesuvius-data-explorer
QT_QPA_PLATFORM=xcb xvfb-run -a pytest -q
```

The `network` marker is excluded by default, even if the environment
variable below is set. The lightweight CI job installs only `.[dev]` and runs both commands above.

To opt into the real public S3 metadata test:

1. Find an existing volume in the [official data browser](https://scrollprize.org/data_browser)
   and consult the [official S3 layout documentation](https://github.com/ScrollPrize/open-data).
2. Copy its complete `s3://` URI in the public `vesuvius-challenge-open-data` bucket.
   The example in the napari section was verified in that bucket; verify availability
   again when choosing a sample.
3. In Bash, enter that exact URI when prompted:

   ```bash
   read -r -p 'Exact public S3 Zarr URI: ' VESUVIUS_TEST_ZARR
   export VESUVIUS_TEST_ZARR
   pytest -q -m network -rs -s
   ```

The test reads only `VESUVIUS_TEST_ZARR`, checks metadata via `list_levels`, and prints the
configured URI for provenance. If it is absent or empty, the test is skipped. An invalid
URI, inaccessible store or unreadable volume fails an explicitly requested network run;
it is never replaced with a guessed URI. No voxel chunks are intentionally read by this test.

### Attribution and references

- Vesuvius Challenge — [Data Formats](https://scrollprize.org/data)
- ScrollPrize — [Open Data documentation](https://github.com/ScrollPrize/open-data)
- ScrollPrize — [villa / vesuvius](https://github.com/ScrollPrize/villa)

Cite **the correct original dataset** for any published results (legacy EduceLab-Scrolls vs newer Vesuvius Challenge datasets), following the official [citation guidance](https://scrollprize.org/data). Code is MIT-licensed; this does **not** change the licenses of upstream datasets.
