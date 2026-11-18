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
   at 50 µm; other tiles do not move. `--cible` sets the offset to reach (µm) instead of the
   segment's usual one, to remove a global shift too.

## Validation (8 published segments, 3 resolutions)

| Test | Result |
|---|---|
| Slow drift imposed (0 to 40 µm ramp), recovered within 2 sampling steps on reliable tiles | **96 %** of 1,649 tiles (88 % to 100 % per segment) |
| Median drift after snapping a drifted segment | **3.5 to 5.8 µm** (sampling step ≈ 9 µm) |
| Snapping a published segment lowers reliability | never (8 / 8) |
| Map time, from S3, download included | 10 to 80 s per segment |

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

## Licence

Code: MIT. Vesuvius Challenge data and the images derived from it: CC BY-NC 4.0 unless stated
otherwise; cite the exact dataset ([guidelines](https://scrollprize.org/data)).
