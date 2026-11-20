# Phase 11 : revue complète et premier contrôle multimodal sur Frag4

## Résumé

- Revue technique et scientifique des phases 1 à 10 ([CLAUDE_FULL_REVIEW.md](CLAUDE_FULL_REVIEW.md)) : aucun défaut bloquant dans le code ; P0 scientifique, le checkpoint A a très probablement été entraîné sur PHerc0500P2.
- Frag4 / PHercParis1Fr39 : inventaire, chaîne CT → maillage → volume de surface validée sous 0,25 voxel, recalage IR mesuré (≈ 50 µm médian, seuil non atteint), compatibilité et indépendance de A documentées.
- Sensibilité de A à l'ordre Z reproduite sur Frag4, sans étiquettes ; évaluation d'encre bloquée par les critères pré-déclarés.
- Décisions appliquées : tolérance de recalage 301 µm, fenêtre d'intensité W2 fixée sur le CT, protocole d'évaluation gelé ([PHASE11_DECISIONS.md](PHASE11_DECISIONS.md)).
- Note communautaire corrigée et envoyée : [ScrollPrize/villa#2627](https://github.com/ScrollPrize/villa/issues/2627).

## Modifications du code

| Fichier | Changement |
| --- | --- |
| `src/vesuvius_data_explorer/core/volume.py` | `dl.ash2txt.org` ajouté aux hôtes HTTPS autorisés |
| `src/vesuvius_data_explorer/core/tifxyz.py` | Message d'erreur dérivé de la liste d'hôtes |
| `src/vesuvius_data_explorer/core/alignment.py` | Convention de signe de `grid_normals` documentée |
| `tests/test_data_access.py`, `tests/test_alignment.py`, `tests/test_phase11.py` | 4 nouveaux tests |
| `docs/validation/phase11_*.py` | 5 scripts de mesure, JSON de résultats |

Aucune donnée Frag4 n'est versée (licence EduceLab-Scrolls).

## Vérification

- Windows natif, Python 3.11 : 360 réussis, 1 ignoré, 8 réseau désélectionnés ; `ruff check .` propre.
- `VESUVIUS_RUST_SAMPLER=1` : 65 tests ciblés réussis.
- Inférence CUDA FP32 déterministe, répétition au bit près.

## Points d'attention pour la revue

- Les mesures B2/B3 ont subi des déviations de protocole déclarées (détecteurs changés après résultats intermédiaires, sans étiquette).
- Les étiquettes d'encre de Frag4 restent fermées ; le protocole gelé doit être appliqué tel quel en phase 12.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
