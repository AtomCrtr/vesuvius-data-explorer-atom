# Réponse courte à EconLearn sur ScrollPrize/villa#2627 (brouillon, non envoyé)

*Brouillon actualisé le 27 novembre 2026 après la comparaison à tuilage identique. À poster par le PO après relecture.*

---

Thanks for rerunning both layer orders on the same pixels with identical tiling.

**Tiling.** On PHerc0343P the matched runs at stride 256 give 0.598 for stored order and 0.919 for reversed order, a difference of 0.321. Our protocol also evaluates both orders at stride 128 with Hann blending. With all four runs, we can estimate how much the order effect changes with tiling and put a paired interval on that difference.

**Your support.** We will rebuild it from your rules for the 8.64 µm grid and check it against the counts you gave on 25 November (247,538 ink, 2,021,316 clean, 4,292,390 valid on PHerc0343P) before scoring. The matched subset from 27 November (227,278 ink, 1,827,547 clean) gives us a separate reference. We will also score both orders on our own support from earlier phases, with a 301 µm exclusion ring.

**Before the labels.** The protocol is committed first. The score maps are hashed before the labels or the infrared photo are opened. We will report paired intervals on the `Z_out` − `Z_in` difference, bootstrapped over ink components, alongside your placement test. This is not blind, since your numbers are known.

**SHA-256.** Yes please, the per-layer SHA-256 would help. We will publish ours for the same files, so anyone can match them against a training copy if the maintainers can say whether `500p2a` was built from this render.

Two details we will infer from your counts anyway, so a confirmation is enough if you have it at hand. We will try a small, pre-declared set of choices and keep the one that reproduces your five counts:

1. How did you go from the ~2.215 µm canvas to the 8.64 µm grid, for the labels and the mask, and for the score map (nearest, area average, other)?
2. Are the 10 px mask erosion and the infrared median computed on the 8.64 µm grid or on the canvas, and over which pixels is the median taken?
