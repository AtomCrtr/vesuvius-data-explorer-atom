# Réponse courte à EconLearn sur ScrollPrize/villa#2627 (brouillon, non envoyé)

*Brouillon du 25 novembre 2026, en réponse à son commentaire du même jour, qui donne sa méthode. À poster par le PO après relecture.*

---

Thanks, this is exactly what we needed, and no apology needed for the detour.

**Tiling.** Your note on tiling matters. The stored-order run used stride 256 and the reversed run stride 128, so the 0.599 → 0.936 gap combines the order effect with the tiling effect. We will rerun both orders with identical tiling (256 px tiles, stride 128, Hann blend), plus both orders at stride 256, so the two effects can be separated.

**Your support.** We will rebuild it from your rules: an 8.64 µm truth grid, letters shrunk by 2 px, clean pixels at least 12 px from any letter and brighter than the infrared median, the mask shrunk by 10 px, and 256-level quantisation between the 0.1 and 99.9 percentiles. We will check that our rebuild reproduces your counts (247,538 ink, 2,021,316 clean, 4,292,390 valid) before scoring anything. We will also score both orders on our own support from earlier phases, with a 301 µm exclusion ring.

**Before the labels.** The protocol is committed first. The score maps are hashed before the labels or the infrared photo are opened. We will report paired intervals on the `Z_out` − `Z_in` difference, bootstrapped over ink components, alongside your placement test. This is not blind, since your numbers are known.

**SHA-256.** Yes please, the per-layer SHA-256 would help. We will publish ours for the same files, so anyone can match them against a training copy if the maintainers can say whether `500p2a` was built from this render.

Two details we will infer from your counts anyway, so a confirmation is enough if you have it at hand. We will try a small, pre-declared set of choices and keep the one that reproduces your six counts:

1. How did you go from the ~2.215 µm canvas to the 8.64 µm grid, for the labels and the mask, and for the score map (nearest, area average, other)?
2. Are the 10 px mask erosion and the infrared median computed on the 8.64 µm grid or on the canvas, and over which pixels is the median taken?
