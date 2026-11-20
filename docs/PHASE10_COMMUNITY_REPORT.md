# Depth-order sensitivity of the canonical 2 µm ink detector on PHerc. 500P2

Technical draft for review. The strongest contribution is a reproducible intervention on a fixed checkpoint, accompanied by spatial and physical controls. [Vesuvius Explorer](https://github.com/AtomCrtr/vesuvius-data-explorer-atom)

## Question and design

On Atlas segment `20250919184428-0500P2-wrap01_0919`, public score maps A and B have an empty top-1% intersection. The published maps use different model recipes. This experiment tests how much changing the input depth order can move scores when the checkpoint, CT bytes, surface coordinates, normalization, tiling and assembly are held fixed. [Villa issue #1377 and maintainer response](https://github.com/ScrollPrize/villa/issues/1377)

We used the historical render on acquisition `20250526151718`, at 2.215 µm per voxel, and the public canonical ResNet-152 checkpoint, SHA-256 `36dd0de84b7b7aa6590184192c7415466cd8a1ba7c1e59f42c6373846373c3e0`. A+ uses depth indices `[28,90)` in ascending order. A− reverses those same 62 input planes. The recipe clips uint8 CT at 200 and divides by 200. Tile size is 256 × 256, stride 128, with Hann-weighted assembly. Both runs use deterministic FP32 inference on a Windows RTX 4080 Laptop GPU. Masks keep only nonzero CT support with positive assembly weight. The 90 tile positions include 32 reused, previously verified tiles, 54 new nonempty tiles and four empty tiles. Eight new tiles reproduced bit for bit across two CUDA processes, including logits and sampled scores. [Canonical checkpoint release](https://huggingface.co/scrollprize/ink_canonical_2um/commit/e154062e55513a1d4110f40fceeddb90eaa0f022) · [Input plan](validation/phase8-input-plan.json) · [CUDA repeat](validation/phase8-cuda-repeat-windows.json)

## Results

- The checked phase 7 crop of A+ matched the published A TIFF within one 8-bit level. Spearman between A+ and A− on that crop was −0.444. A distant window reached 0.809. [Phase 7 comparison](PHASE7_MODEL_COMPARISON.md)
- Across **790,200 valid pixels** of the historical render, mean absolute score change was **0.247**, with a **[0.209, 0.283]** 95% block-resampling interval using 64² blocks. Pearson was −0.016 and Spearman 0.021. Filling the excluded background with shared zeros raised Spearman to 0.870 in a diagnostic calculation. The top 0.1%, 1% and 5% sets were disjoint on valid support. At 10%, they shared 3,005 of 79,020 selected pixels per map. [Spatial report](validation/phase8-spatial-windows.json)
- The 61 admitted cells of a fixed 128 × 128 grid had mean absolute changes from 0.003 to 0.786. The difference persisted more than 16 pixels inside the support, with mean 0.255. Support fraction and median distance to the edge had modest regional associations with the change, with Spearman 0.396 and 0.388 respectively. The bootstrap summarizes spatial sensitivity within one fragment and one surface. [Map and methods](PHASE8_SPATIAL_ROBUSTNESS.md)
- Raw CT resampling favored increasing rendered depth along `−N` at four phase 7 and six phase 8 witnesses. The anatomical side of `wrap01_0919` remains unknown. The phase 9 optical investigation found no independently verified match for field `500P2_230925_N2`. Distances of at least 4.42 mm refer to the sampled historical `wrap01_0919` nodes and the two tested frontal mesh revisions. They leave other surfaces and the location of N2 open. [Orientation controls](PHASE8_PHYSICAL_ORIENTATION.md) · [Optical investigation](PHASE9_CT_OPTICAL_REGISTRATION.md)

The experiment establishes a depth-order effect on A's scores for this render. The exact public B checkpoint remains unavailable to us, so the contribution of order to the production A/B difference is unresolved. Ink ground truth, score calibration and generalization are unresolved for this case. There is no papyrological reading in this report.

## Relation to prior work

The A/B observation and a translation control already appear in Villa #1377 and its linked benchmark. The rendering convention and depth reversal options are documented in Villa. The PHerc. 1667 baseline card records a training-segment convention requiring reversed order during inference. The official prize notes also describe a depth-count experiment on a 9 µm model. The addition supported here is the paired intervention **with an identical public A checkpoint and identical source**, a full-render map with a valid-support sensitivity analysis, repeated CUDA logits, and an independent raw-CT sign check for the exact render. Within the reviewed sources, these results extend #1377. A reproducibility note or technical follow-up to that issue is a suitable format after approval and a review of the artifacts permitted for sharing. [Villa renderer](https://github.com/ScrollPrize/villa/blob/530584554c031c982ba3aa243e1ea39c4bef9818/volume-cartographer/apps/src/vc_render_tifxyz.cpp#L1084) · [Published PHerc. 1667 baseline](https://huggingface.co/scrollprize/PHerc.1667-iteration-0/blame/main/README.md) · [Vesuvius Challenge depth-count experiment listing](https://scrollprize.org/winners)

## Reproduction

Use the phase 8 input plan and documented CUDA environment and source directories. The baseline run reuses fingerprinted phase 7 tiles. The scripts record source, checkpoint, raw scores and the validity mask. The reporting code and references are stored beside the measurements. [Environment and inputs](VESUVIUS_PHASE8.md#reproduction)

```powershell
$gpuPython = 'data/phase6-cuda/Scripts/python.exe'
$qaPython = '.venv/Scripts/python.exe'
& $gpuPython docs/validation/phase8_cuda.py data/phase8 --prepare
& $gpuPython docs/validation/phase8_cuda.py data/phase8
& $gpuPython docs/validation/phase8_cuda.py data/phase8 --repeat
& $qaPython docs/validation/phase8_spatial.py data/phase8 docs/validation/phase8-spatial-windows.json
& $qaPython docs/validation/phase8_orientation.py data/phase8 docs/validation/phase8-orientation-windows.json
```

The public draft can be accompanied by the recipe, hashes, summary statistics and acquisition references. Any distribution of CT, photography or labeled imagery follows the terms of its own source. [Data attribution](https://github.com/ScrollPrize/open-data#support-and-citation)
