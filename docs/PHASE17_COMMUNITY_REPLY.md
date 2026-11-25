# Réponse à EconLearn sur ScrollPrize/villa#2627 (brouillon, non envoyé)

*Brouillon du 25 novembre 2026, en réponse au [commentaire d'EconLearn](https://github.com/ScrollPrize/villa/issues/2627) du 24 novembre, corrigé le 25. À poster par le PO après relecture. Liens épinglés sur `7ea4013`.*

---

Thanks for running this. It is the first replication of the order effect outside our pipeline, on a fragment we had not studied when you ran this, at the checkpoint's native ~2 µm and against independent truth (infrared-traced letters). A 0.60 → 0.94 swing on PHerc0343P is a much cleaner signal than anything we had on Frag4, whose input is out of recipe (3.24 µm, non-zero air).

**Naming, so we compare the same thing.** In our notes, `Z_out` is the order whose planes ascend toward air (papyrus → air) and `Z_in` the reverse. If your brightness read is right, your stacks as stored are `Z_in` and "layers reversed" is `Z_out`.

**Which Frag4 result to compare against.** Your edit is right that this is the opposite of the asymmetry in the issue body: there, only `Z_in` produced a *structured* map. But the follow-up comment above scored both orders against the Frag4 ink labels under a frozen protocol, and there it is `Z_out` that ranks ink (0.86 / 0.89), while `Z_in` is at chance. We later repeated this on new Frag4 ROIs and on Frag1, 2, 3, 5 and 6 with pre-registered hypotheses. `Z_out` ranks ink above chance on 5 of 6 fragments; Frag3 is the exception, where `Z_in` does slightly better ([phase 13](https://github.com/AtomCrtr/vesuvius-data-explorer-atom/blob/7ea40135ebe2f3815e3bc0bf38c1e7d19841c7df/docs/PHASE13_INK_GENERALIZATION.md), [phase 14](https://github.com/AtomCrtr/vesuvius-data-explorer-atom/blob/7ea40135ebe2f3815e3bc0bf38c1e7d19841c7df/docs/PHASE14_HELDOUT_ORDER.md)). So both readings of your edit hold. Compared with map structure, your result is the opposite of Frag4. Compared with ink labels, it goes the same way, *if* the air side is where you think it is. The ink comparison is the one that matters, so everything hinges on orientation.

**Checking the air side without brightness.** On Frag4, mean grey is a weak cue. Air is not dark there (about 0.48 after `>> 8`, against a papyrus mean of about 0.52). Since phase 13 we use a label-free rule, frozen before any score: take the median per-layer standard deviation inside the mask, over the same 64 px patches, and call the less textured depth end air. On Frag4, whose written face is known, it picks the right side by a factor of about 6 (end std 7,806 vs 1,349, uint16). Could you share the per-layer standard deviations on your evaluation regions for both stacks? That would let us compare your local texture profiles with ours.

**PHerc0500P2 may settle the physical training order.** The public training script whose identifiers match this checkpoint lists `500p2a` with `reverse_layers=True` ([script](https://github.com/ScrollPrize/villa/blob/c8f3ba45304f0a317a49a155929e30d294f201eb/deprecated/ink-detection/train_resnet3d_3d_decoder.py)). The training loader selects layers 01–62 and then reverses them. Your window is 02–63. The public stack contains both windows, but the script gives no native dimensions or file hashes for `500p2a`. Establishing that the two paths refer to the same render, with the same numbering, would let us connect the physical orientation to training for this segment. Do you know whether that stack is the `500p2a` training render?

**Our result on your stacks.** We froze a minimum twofold end-to-end texture ratio before reading any layer pixels. On PHerc0343P the mean of the per-layer median standard deviations was 3.60 at layers 02–14 and 21.02 at layers 51–63, a 5.83-fold ratio. Our rule places air at the low-numbered end, so your reversed order corresponds to papyrus → air on PHerc0343P. It also placed air at the low-numbered end on PHerc0500P2 (ratio 2.50). The physical order used during training still depends on identifying the training render.

Two smaller points:
- The 0.91 of the team's 2.2 µm map is scored against Domenico Russo's camera truth, and your 0.936 against traced letters. The truths differ, so the two numbers are not directly comparable.
- For your ROC-AUCs: how were the photo-clean negatives chosen, what is the ink prevalence, and do you have intervals (we use a block bootstrap, which is itself optimistic under spatial autocorrelation)?

No image, label crop or transcription attached (EduceLab-Scrolls licence).
