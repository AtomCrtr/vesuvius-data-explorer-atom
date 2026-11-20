# Follow-up to ScrollPrize/villa#2627 (sent)

*Posted on 2026-11-21 with the project owner's approval: [comment](https://github.com/ScrollPrize/villa/issues/2627#issuecomment-7053242080), links pinned to commit `7c696e5`.*

---

**Follow-up: Frag4 ink labels, evaluated under a protocol frozen beforehand**

We opened the Frag4 (PHerc. Paris 1 Fr 39) ink labels only after committing the evaluation protocol (ROIs, intensity window, a 301 µm registration tolerance, metrics, hypotheses) and the evaluation script. Same checkpoint, same two ROIs, same inputs as above.

| | ROI 2 | ROI 5 |
| --- | ---: | ---: |
| Label prevalence | 3.6 % | 0.74 % |
| ROC-AUC, air → papyrus | 0.49 [0.39, 0.58] | 0.40 [0.27, 0.55] |
| ROC-AUC, papyrus → air | 0.86 [0.79, 0.90] | 0.89 [0.83, 0.94] |
| Average precision, papyrus → air | 0.121 (3.4 × prevalence) | 0.034 (4.5 × prevalence) |

- Our pre-registered hypotheses (the "air → papyrus" order ranks ink better than the reverse, and above chance) are **rejected**. The structured output we reported for that order does not follow the labels.
- The reverse order, whose output is nearly flat (no pixel above 0.5), **ranks** the labelled pixels well above chance. The pattern holds with both intensity windows and under label shifts of up to ±50 µm. It is an exploratory observation on two ROIs, not a detection, and was not a pre-registered hypothesis.
- As a post-hoc control, single CT planes reach a ROC-AUC of at most about 0.64 (ink slightly darker at the published surface), so the ranking is not just raw intensity.
- 95 % intervals come from 64 × 64 px block bootstrap and are optimistic given spatial autocorrelation. Frag4's absence from training is probable, not attested.

This makes the questions above more pressing, in particular which depth order and which normalisation produced the released weights. No image, label crop or transcription is attached (EduceLab-Scrolls licence).
