# Phase 12 : première évaluation d'encre de A sur Frag4, sous protocole gelé

## Résumé

- Les étiquettes d'encre de Frag4 ont été ouvertes après le gel du protocole (`5c0602f`) et du script d'évaluation (`f9c965d`, poussé avant le téléchargement).
- **Les hypothèses pré-déclarées H1 et H2 sont rejetées** : l'ordre air → papyrus (Z_in) est au niveau du hasard (ROC-AUC 0,49 et 0,40).
- **Exploratoire** : l'ordre inverse (Z_out) classe l'encre (ROC-AUC 0,86 et 0,89) sans jamais la détecter (aucun score > 0,5). Le résultat est stable entre les deux fenêtres, et l'intensité brute plafonne vers 0,64.
- Les métriques au pixel sont indéfinies : aucun trait d'encre n'est plus large que deux fois la tolérance de 301 µm.
- Correction déclarée : un bug dans le calcul de la bande de tolérance a été corrigé après le premier passage, et les rangs n'ont pas changé.

[Rapport](PHASE12_INK_EVALUATION.md) · [Complément à villa#2627, non envoyé](PHASE12_COMMUNITY_FOLLOWUP.md)

## Fichiers

| Fichier | Rôle |
| --- | --- |
| `docs/validation/phase12_ink_eval.py`, `phase12-ink-eval.json` | Évaluation sous protocole gelé |
| `docs/validation/phase12_baseline.py`, `phase12-baseline.json` | Contrôle a posteriori par l'intensité brute |
| `tests/test_phase12.py` | AP et ROC-AUC sur histogrammes comparées aux définitions exactes ; distance au bord ; métriques au pixel |

Aucune étiquette, image ni découpe de Frag4 n'est versée (licence EduceLab-Scrolls) : seulement des métriques agrégées.

## Vérification

- Windows natif, Python 3.11 : 363 réussis, 1 ignoré, 8 réseau désélectionnés ; `ruff check .` propre.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
