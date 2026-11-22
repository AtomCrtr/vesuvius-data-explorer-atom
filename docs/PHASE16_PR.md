# Phase 16 : pas réel de la PPM contre pas nominal (T2)

## Résumé

- Protocole figé avant toute préparation au pas réel (`3dae2c2`), manifestes de préparation sans étiquettes (`05ea510`), puis évaluation avec le script commité.
- Décision : **pas nominal conservé**. Écart moyen de ROC-AUC(Z_out) −0,009 [−0,022 ; +0,004] sur 37 ROI (bootstrap par ROI) ; Frag2 à −0,023, sous le seuil de −0,02.
- Le pas médian de la PPM vaut 0,94 à 1,05 voxel par pixel UV, sauf Frag6 ROI 2 (1,21). Malgré une correction aussi faible, la ROC-AUC d'une ROI varie de ±0,09 : une valeur par ROI n'est qu'indicative.
- Exploratoire : étiquettes des six fragments déjà lues en phases 12 à 14.

[Rapport](PHASE16_REAL_PITCH.md)

## Fichiers

| Fichier | Rôle |
| --- | --- |
| `docs/validation/phase16-protocol.json`, `phase16_scale.py` | Protocole figé, préparation au pas réel et rapport |
| `docs/validation/phase16-prepare-frag*.json` | Pas mesuré par ROI, empreintes des volumes préparés (sans étiquettes) |
| `docs/validation/phase16-eval.json` | Résultats par ROI et critère primaire |
| `tests/test_phase16.py` | Pas d'une PPM synthétique non isométrique ; identité avec la phase 13 au pas nominal ; grille d'étiquettes |

Aucune étiquette, image ni découpe EduceLab n'est versée : seulement des métriques agrégées.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
