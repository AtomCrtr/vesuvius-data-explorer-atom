# Discord draft

Hi! I’m working on Vesuvius Data Explorer, a CPU tool for checking the alignment of existing
tifxyz surfaces against the CT scan. It estimates signed drift, reliability and uncertainty by
tile and ranks regions for manual review. In napari, you can jump from the review list to the
corresponding CT slice. The CLI can also export a separate corrected tifxyz, with every point in
excluded tiles held fixed.

Try the CLI on a published segment:

```sh
vesuvius-qc carte 20250825181928 --catalogue --recaler -o map/
```

On PHerc0814 segment `20260226110425`, the estimated drift in one tile fell from +45.7 to
+16.7 µm. The CT sections show the corrected trace getting closer to the bright band in the
middle of that tile. This example uses the published segment as-is. A separate triptych shows
fibre recovery after adding a 0–40 µm drift deliberately. Coverage varies by segment, and
sheet-switch detection remains unvalidated on real scans.

If you have a traced segment with a suspected local drift, I’d be interested in whether the map
points you to the same region you’d pick by eye.

[Install, napari walkthrough and triptych](https://github.com/AtomCrtr/vesuvius-data-explorer-atom/blob/main/docs/en/alignment-map.md)
· [PHerc0814 CT cross-sections](https://github.com/AtomCrtr/vesuvius-data-explorer-atom/blob/main/docs/validation/t10-coupes-20260226110425.png)
