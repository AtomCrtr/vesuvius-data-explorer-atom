# Phase 13 : le classement de l'encre par Z_out ne se généralise pas aux trois fragments

## Résumé

- Le protocole et le script ont été figés (`c9f6398`) avant tout score de la phase et avant le téléchargement des étiquettes de Frag1 et Frag3. Les manifestes de préparation sans étiquettes ont été commités avant l'évaluation (`b4129f6`).
- Contrôles sans étiquettes : la règle de sens place l'air du côté des couches hautes dans les trois fragments (Frag4 en contrôle positif), la surface est à z = 32, et la fenêtre W2 de Frag4 reproduit celle de la phase 11.
- ROC-AUC regroupée de Z_out : **0,82** sur Frag4 (nouvelles ROI), **0,67** sur Frag1 et **0,52** sur Frag3. H3, H4 et H5 tiennent sur Frag4 et Frag1, aucune sur Frag3 (Z_in y fait mieux). **Généralisation non établie.**
- Résultat exploratoire : Frag1 et Frag3 sont des fragments d'entraînement Kaggle 2023, et leur exclusion de l'ascendance de A n'est pas attestée.

[Rapport](PHASE13_INK_GENERALIZATION.md)

## Fichiers

| Fichier | Rôle |
| --- | --- |
| `docs/validation/phase13-protocol.json`, `phase13_eval.py` | Protocole figé ; préparation générique (sens, fenêtre, ROI) et évaluation regroupée avec bootstrap apparié |
| `docs/validation/phase13-prepare-*.json`, `phase13-eval.json` | Manifestes sans étiquettes, résultats |
| `tests/test_phase13.py` | Bootstrap apparié et témoins non appris |

L'inférence réutilise `phase11_z_frag4.run` sans modification. Aucune étiquette, image ni découpe EduceLab n'est versée : seulement des métriques agrégées.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
