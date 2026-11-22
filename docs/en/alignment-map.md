# Alignment map and snapping of tifxyz segments

*English documentation of task T10. French version: [guide](../guide.md#8-carte-dalignement-et-recalage-dun-segment),
[technical reference](../reference.md#carte-dalignement-t10),
[validation report](../validation/T10-carte-alignement.md).*

**Where does a traced surface leave its papyrus sheet, by how much, and how sure are we?**
`vesuvius-qc carte` answers this tile by tile for any VC3D tifxyz segment, from the CT signal
alone: no GPU, no trained model. On request, it writes a snapped copy of the segment.

![Published segment (top), the same segment moved 0 to 40 µm along its normals (middle), and
after snapping (bottom): the fibres come back on the right](../validation/t10-triptyque-20250825181928.png)

<sub>PHerc0500P2, segment `20250825181928`, 2.215 µm. Data: Vesuvius Challenge, CC BY-NC 4.0.</sub>

## Install and run

```bash
pip install "vesuvius-data-explorer @ git+https://github.com/AtomCrtr/vesuvius-data-explorer-atom.git"

# A catalogued segment: volume and voxel size are looked up in the official catalogue
vesuvius-qc carte 20250825181928 --catalogue --recaler -o map/

# Any segment and volume (local, S3 or HTTPS)
vesuvius-qc carte SEGMENT.tifxyz --volume VOLUME.zarr --pixel-size-um 2.4 -o map/
```

Outputs in `map/`:

| File | Content |
|---|---|
| `rapport.html` | colour map, flattened renders before / after, regions to review |
| `decalage.tif`, `fiabilite.tif`, `incertitude.tif` | float32, one value per tile: drift (µm), reliability, uncertainty (µm) |
| `zones.json` | regions to review, most severe first: type, tiles, rows / columns in the tifxyz grid, 3D centre (z, y, x) |
| `carte.json` | key figures and parameters |
| `recale/` (`--recaler`) | snapped tifxyz (`x/y/z.tif`, `meta.json` with provenance); the original is never modified |

In napari, overlay a segment in **Vesuvius — Surfaces** and click **Cartographier la dérive**
(Map drift). The coloured trace follows the current slice and is also visible in 3D. Grey marks
tiles with weak or missing measurements. Selecting a review region centres the slice on it.

## Method

1. **Tiles.** The grid is cut into tiles of 8 × 8 points (about 160 level-0 voxels). For each
   tile, the volume is sampled along the normals of its points, ±200 µm, at the coarsest level
   whose voxel is ≤ 10 µm, and averaged into one profile.
2. **Sheet.** The nearest local maximum to the surface, brighter than the profile median,
   refined by a parabola. Unlike the brightest point of a window, it does not jump to a
   neighbouring sheet.
3. **Reliability** = peak height / standard error of the mean profile; a tile is *reliable* at 3
   or more. **Uncertainty**: delta-method propagation of the profile variance to the peak
   position (falls as 1/√N).
4. **Drift** is measured relative to the segment's usual offset. Published segments sit about
   10 µm from the bright centre of their sheet, most likely because they follow one face of it:
   this is not an error to correct.
5. **Regions to review**: reliable drift beyond 30 µm, and measured tiles without a reliable sheet.
6. **Snapping**: weighted least squares with a smoothness term on the reliable tiles only, capped
   at 50 µm. Every point of an excluded tile stays fixed and every point of a snapped tile moves
   by its full value, so the mesh steps at the boundary (at most the 50 µm cap). `--cible` sets
   the target offset (µm) to correct a global shift too.

## Natural drift on every published PHerc0814 segment

Selection rule committed before the run: all 19 published segments of PHerc0814 volume
`20250804134230` (9.362 µm), default settings, and every snapped tile whose drift exceeded
25 µm. The illustrated tile is the one with the largest drift *before* snapping, chosen without
looking at the result.

| | Before | After snapping |
|---|---:|---:|
| Tiles with \|drift\| > 25 µm (19 / 19 segments) | 1,648 | — |
| Median \|drift\| | **31.3 µm** | **14.4 µm** |
| Tiles whose drift decreased | — | **94.7 %** |
| Tiles back under 25 µm | — | 82 % (7 % overshoot to the other side) |
| Median reliability of these tiles | 4.60 | 4.50 |

![Two CT cross-sections through segment 20250925204843, tile (20, 57): the published trace (cyan)
and the snapped trace (orange)](../validation/t10-coupes-20250925204843.png)

The snapped trace moves about 18 µm towards the bright band and stays on the same sheet. The
lower section shows the step at the tile boundary (column 159 to 160): points of the
neighbouring tile are frozen. Fibres remain visible on the snapped surface; the flattened render
shows no clear gain in sharpness. [Flattened render](../validation/t10-rendu-20250925204843.png) ·
[Data](../validation/t10-derive-naturelle.json) · [Script](../validation/T10_derive_naturelle.py)

<sub>PHerc0814, segment `20250925204843`. Data: Vesuvius Challenge, CC BY-NC 4.0.</sub>

## Validation with imposed drift (16 published segments, 3 resolutions)

Criteria frozen before each campaign. Sample B (8 new segments) is the confirmation sample;
sample A (the original 8) had been used for diagnosis.
[Report (French)](../validation/T10-carte-alignement.md#7-correctif-de-la-transition-et-critère-2b-révisé)

| Test | Sample B | Sample A |
|---|---|---|
| 0–40 µm ramp recovered within 2 sampling steps on ≥ 80 % of reliable tiles | 7 / 7 measurable segments (89 % to 100 %) | 7 / 7 |
| Median drift after snapping the ramp, below one sampling step (≈ 9 µm) | 7 / 7 (3.8 to 5.2 µm) | 7 / 7 (2.9 to 5.8 µm) |
| Points of non-snapped tiles bit-identical | 8 / 8 | 8 / 8 |
| Median reliability of snapped tiles does not drop | **failed: 4 / 8 dropped** (−0.05 to −0.13) | 5 / 7 (−0.005, −0.011) |
| Mesh step between neighbouring points, p95 / max | ≤ 1.7 / up to 49.6 µm | ≤ 1.9 / up to 48.1 µm |
| Full run per segment (4 maps and renders), from S3, download included | 52 s to 3.4 min | 25 s to 4.2 min |

A first version tapered the correction over half a tile. Reliable tiles are mostly isolated, so
they received about half their correction, with a gradient that blurred their profile. Each
snapped tile now moves as a block; the cost is the step above. The remaining reliability drops
may come from steps of 40–50 µm tilting the normals at tile edges: not yet tested.

## Limits

- About one tile in three is reliable; the map says nothing precise about the others.
- **Sheet switches are not detected as such on real data.** A phase method (wrapped drift,
  residues on 2 × 2 loops) works on synthetic sheets, but on real scrolls the sheets are not
  regularly spaced at tile scale and the spacing cannot be measured. A real switch shows up as an
  unreliable region or a strong drift.
- Published segments are mostly well placed: snapping moves the median point by a few µm and
  gives no measurable gain in fibre sharpness; the gain is clear on a deliberately drifted
  segment. Locally, strong natural drift is common and is reduced (table above).
- Snapped and frozen tiles meet at a step of up to the 50 µm cap.
- The first map of a large segment downloads every chunk the surface crosses (up to several GB
  for uncompressed HTTPS volumes such as Scroll 1); later runs use the local cache.

## Related tools

| Tool | Workflow | Where the alignment map fits |
|---|---|---|
| ScrollFiesta | Builds, assembles and flattens meshes. Its `tifxyz_snap` command can also fit existing tifxyz segments to the recto edge in raw CT. | T10 reports signed drift, reliability and uncertainty by tile and ranks regions for visual review. Its optional correction targets the segment's usual offset by default and freezes excluded tiles. [ScrollFiesta tools](https://github.com/Hob3rMallow/scrollfiesta_public#supported-executables) |
| Benjamin Hamm's nnInteractive refinement | Refines a voxel mask into individual sheet labels with a CUDA checkpoint and automatically generated prompts. | T10 takes a traced tifxyz surface and CT volume as inputs and returns a map and an optional corrected tifxyz using the CPU. [nnInteractive sheet refinement](https://github.com/hammb/vesuvius-surface-detection-nninteractive-refinement#nninteractive-sheet-refinement) |
| William Stevens's patch-based unwrapping | Removes patches whose 2D overlaps imply inconsistent 3D positions, then assembles compatible patches into flattened components. | T10 measures local CT alignment of an existing trace for review. The current real-data validation covers local drift recovery. Sheet-switch detection remains unvalidated. [Progress Prize results](https://scrollprize.org/winners) |

This comparison describes inputs, outputs and use cases. Relative accuracy and runtime require a
benchmark on shared inputs.

## Licence

Code: MIT. Vesuvius Challenge data and the images derived from it: CC BY-NC 4.0 unless stated
otherwise; cite the exact dataset ([guidelines](https://scrollprize.org/data)).
