# Depth order changes what the canonical 2 µm ink model sees: a paired intervention on two fragments

*Sent on 2026-11-21 as [ScrollPrize/villa#2627](https://github.com/ScrollPrize/villa/issues/2627). Replaces the phase 10 draft, which omitted that PHerc. 500P2 is very likely in the model's training data.*

**Summary.** With the public `ink_canonical_2um` checkpoint held fixed, reversing only the order of the 62 input planes decorrelates its scores (Spearman ≈ 0) and makes the top-1% pixel sets disjoint, on PHerc. 500P2 and on Frag4 (PHerc. Paris 1 Fr 39). On Frag4, whose written face is known, the model gives structured output only when the planes run from air into the papyrus. This is a sensitivity result. It is not an ink evaluation and says nothing about which order finds ink.

## Setup

- Checkpoint `r152_3ddec_v2_l5_epoch13.ckpt`, SHA-256 `36dd0de8…73c3e0`, architecture from Villa `ink-detection/optimized_inference` at `baf5e605`. Clip 200, divide by 200, 256 px tiles, stride 128, Hann blending, FP32 with deterministic cuDNN on an RTX 4080 Laptop GPU. Repeated tiles reproduce bit for bit.
- The only manipulation is the direction of the depth axis of the same input array.

## Results

| | PHerc. 500P2 `wrap01_0919` (2.215 µm render) | Frag4, 2 ROIs (3.24 µm resampled to 2.215 µm) |
| --- | --- | --- |
| Valid pixels | 790,200 | 876,272 per ROI |
| Spearman between orders | 0.021 | 0.029 and −0.080 |
| Mean \|Δscore\| [95 % block CI] | 0.247 [0.209, 0.283] | 0.086 [0.066, 0.105] and 0.047 [0.037, 0.059] |
| Shared top-1 % pixels | 0 | 0 and 0 |
| Pixels > 0.5, per order | both orders produce structure | 0 % vs 8.3 % and 0 % vs 2.6 % |

On Frag4 the "air → papyrus" order yields structured scores (p99 0.71–0.84); the reverse yields a near-constant ≈ 0.12. The smaller mean change on Frag4 reflects that flat output.

## Caveats, stated up front

- **PHerc. 500P2 is very likely in the training set.** The public training script whose identifiers match this checkpoint (checkpoint name, `pred_shape` [4608, 13824], and 8,089 steps × 14 epochs = global step 113,246) lists `500p2a` with `reverse_layers=True`, and a segment named `-1`. The 500P2 numbers are therefore in-distribution. Frag4 and all `Frag*` are absent from that list, but label lineage and pretraining are undocumented.
- **Frag4 input is out of recipe.** DLS 54 keV uint16 converted with `>> 8` leaves air at ≈ 0.48 after normalisation (≈ 0 on 500P2); the flattened grid is not isometric (3.05–4.09 µm per pixel). As a control we repeated the run with a CT-only linear window matching the input mean and standard deviation to a verified 500P2 tile (0.379, 0.148): the pattern is unchanged (Spearman 0.027 and −0.006, top-1 % disjoint, pixels > 0.5: 0 % vs 6.0 % and 0 % vs 2.3 %). The non-isometric pitch is not corrected.
- Two fragments, one model, a few windows. Block bootstrap intervals are optimistic because spatial autocorrelation exceeds the block size.
- We did not open Frag4 ink labels: our IR-to-CT registration check (≈ 50 µm median along a shared crack, IR native pixel ≈ 20 µm) did not meet the threshold we had set in advance.

## Relation to prior work

Villa #1377 reported the disjoint A/B top-1 % sets on this segment; the maintainer's reply attributed it to different models and data. Villa #1765 / #1766 showed that the depth **window** must be centred on the surface to reproduce published maps. This note isolates the depth **order** with everything else fixed, adds a second fragment with a known written face, and points out the asymmetric response there. The training script itself sets `reverse_layers` per segment, so the expected order is a per-dataset convention that is easy to get wrong when running the model on new data.

## Questions for maintainers

1. Is the listed `TRAIN_FRAGMENT_IDS` the exact data of the released checkpoint? Were Frag4/PHerc. Paris 1 or its derived pseudo-labels used anywhere in its lineage, including `r3d152_KM_200ep.pth`?
2. Training uses `A.Normalize(mean=0, std=1)` (divisor 255 by default) while inference divides by 200; which one produced the released weights' `BatchNorm` statistics?
3. Which depth order should be used for an exposed fragment surface?

Code, hashes and summary statistics: [Vesuvius Explorer](https://github.com/AtomCrtr/vesuvius-data-explorer-atom), `docs/PHASE11_Z_GENERALIZATION.md`, `docs/PHASE8_SPATIAL_ROBUSTNESS.md`. No CT, photograph or score image is attached: Frag4 is EduceLab-Scrolls data (Parsons et al. 2023, arXiv:2304.02084) and is not redistributed.
