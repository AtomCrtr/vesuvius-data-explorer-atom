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
   at 50 µm. Every point of an excluded tile stays fixed. The displacement tapers on the moving
   side of each boundary. `--cible` sets the target offset (µm) to correct a global shift too.

## Initial validation (8 published segments, 3 resolutions)

| Test | Result |
|---|---|
| Slow drift imposed (0 to 40 µm ramp), recovered within 2 sampling steps on reliable tiles | **96 %** of 1,649 tiles (88 % to 100 % per segment) |
| Median drift after snapping a drifted segment | **3.5 to 5.8 µm** (sampling step ≈ 9 µm) |
| Snapping a published segment lowers reliability | never (8 / 8) |
| Map time, from S3, download included | 10 to 80 s per segment |

With strict tile freezing, the median residual after snapping the ramp was **4.4 to 8.8 µm**,
below one sampling step on all seven measurable segments. Median reliability of the published
surfaces fell on five of the eight segments, by up to 0.20 on the score's scale.
[Rerun data](../validation/t10-validation-gel-strict.json)

On the published PHerc0814 segment `20260226110425`, local drift fell from +45.7 to +16.7 µm
in the illustrated tile. All 6,686 valid points in excluded tiles kept their coordinates.
[CT cross-sections and reproduction steps](../validation/T10-carte-alignement.md#dérive-naturelle-sur-pherc0814)

## Limits

- About one tile in three is reliable; the map says nothing precise about the others.
- **Sheet switches are not detected as such on real data.** A phase method (wrapped drift,
  residues on 2 × 2 loops) works on synthetic sheets, but on real scrolls the sheets are not
  regularly spaced at tile scale and the spacing cannot be measured. A real switch shows up as an
  unreliable region or a strong drift.
- Published segments are already well placed: snapping moves them by a few µm at most and gives
  no measurable gain in fibre sharpness; the gain is clear on a deliberately drifted segment.
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
