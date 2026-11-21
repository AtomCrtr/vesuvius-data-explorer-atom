# Phase 14 : Z_out validé comme ordre par défaut sur trois fragments réservés

## Résumé

- Découverte sur les 19 ROI déjà étiquetées : aucun critère sans étiquettes (dispersion, queue, cohérence spatiale, corrélation à la surface) ne bat la règle fixe « toujours Z_out ».
- Protocole figé (`5490336`) avant toute lecture de Frag2, Frag5 et Frag6. Manifestes sans étiquettes commités (`8f1af22`) avant le téléchargement des étiquettes.
- ROC-AUC de Z_out regroupée : **0,63** sur Frag2, **0,73** sur Frag5 et **0,77** sur Frag6. H3, H4 et H5 tiennent sur les trois fragments : le critère pré-déclaré est rempli.
- Résultat exploratoire : Frag2 est un fragment Kaggle, et l'ascendance de A n'est pas documentée pour Frag5 et Frag6.
- `phase13_eval.py --protocol` réutilise le script de la phase 13 et refuse un protocole modifié.
- Le test napari instable en CI est corrigé : la fixture `async_loading` attend la fin des threads Qt.

[Rapport](PHASE14_HELDOUT_ORDER.md)

## Fichiers

| Fichier | Rôle |
| --- | --- |
| `docs/validation/phase14_discovery.py`, `phase14-discovery.json` | Criblage des sélecteurs sur les ROI vues |
| `docs/validation/phase14-protocol.json`, `phase14-prepare-*.json`, `phase14-eval.json` | Protocole, manifestes, résultats |
| `docs/validation/phase13_eval.py` | `--protocol`, empreinte vérifiée, fragments réservés ajoutés |
| `tests/test_phase13.py`, `tests/conftest.py` | Refus d'un protocole modifié ; attente des threads Qt avant le contrôle de fuite napari |

Aucune étiquette, image ni découpe EduceLab n'est versée : seulement des métriques agrégées.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
