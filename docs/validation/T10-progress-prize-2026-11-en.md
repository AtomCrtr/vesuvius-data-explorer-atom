# Progress Prize submission draft — November 2026

Form: November 2026 Progress Prizes. Name, team, e-mail and Discord name are filled in by the
team lead. Links point to `main`: merge the T10 branch before submitting.

## URL of the contribution

- https://github.com/AtomCrtr/vesuvius-data-explorer-atom (MIT)
- https://github.com/AtomCrtr/vesuvius-data-explorer-atom/blob/main/docs/en/alignment-map.md

## What is your contribution?

`vesuvius-qc carte` finds where a traced tifxyz segment drifts off its papyrus sheet and
corrects the drift where the CT signal is reliable. It measures signed drift, reliability and
uncertainty tile by tile (8 × 8 grid points) from the CT alone, on CPU, without a trained
model. With `--recaler` it writes a separate snapped tifxyz. Reliable tiles move along their
normals, and every point of every other tile stays bit-identical. It also writes a ranked list
of regions for human review, also available in napari.

**(1) Scroll data.** Published segments and CT volumes from the open data bucket. All 19
published segments of PHerc0814 volume `20250804134230` (9.362 µm), and 16 segments on 11
volumes at about 1.1, 2.4 and 8.6–9.4 µm for the imposed-drift validation.

**(2) Why it matters.** Traced surfaces often sit tens of µm off their sheet in places. Renders
and ink models sample a few dozen layers around the surface, so a 30 µm offset is several layers
at these voxel sizes. The tool corrects this locally and leaves uncertain regions untouched for
an annotator, ranked by severity, so review time goes where the CT cannot decide.

**(3) What it enables.** A per-tile drift map with an uncertainty for any existing tifxyz, plus
a correction that is restricted to tiles the CT supports, documented by provenance in
`meta.json`, and reproducible. ScrollFiesta's `tifxyz_snap` also fits tifxyz segments to the
sheet. This tool adds the measured uncertainty, the frozen regions and the review list.

**(4) Evidence.** Each selection rule and criterion was committed before its run.
- Natural drift: all 19 PHerc0814 segments. Of the 1,648 snapped tiles with drift above 25 µm,
  94.7 % improved, and the median drift fell from 31.3 to 14.4 µm. The illustrated tile is the
  one with the largest drift *before* snapping. The CT cross-sections show the trace moving
  towards the sheet without jumping to another one, and fibres stay visible on the output
  surface.
- Imposed 0–40 µm ramp on a new sample of 8 segments: recovered on 89–100 % of reliable tiles,
  and the residual after snapping is 3.8–5.2 µm (below one sampling step).
- Limits, stated in the report: the median reliability of snapped tiles dropped slightly on 4 of
  8 new segments, which fails our own criterion. Snapped and frozen tiles meet at a step of up
  to 50 µm. There is no measurable sharpness gain on already well-placed segments. Sheet
  switches are not detected as such on real data.

Report, data and scripts:
https://github.com/AtomCrtr/vesuvius-data-explorer-atom/blob/main/docs/validation/T10-carte-alignement.md
