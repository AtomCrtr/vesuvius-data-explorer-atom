# Phase 15 : audit a posteriori du résultat de la phase 14

## Résumé

- H3 tient pour chacun des 20 retraits d'une ROI, avec des pires bornes basses de 0,571, 0,567 et 0,710.
- Les deux ROI presque parfaites (Frag5 ROI 1, Frag6 ROI 7) ne sont pas des artefacts de bord : la ROC-AUC sur le cœur est identique. Chacune ne contient qu'une composante d'encre.
- Frag5 dépend d'une seule ROI (0,73 → 0,60 sans elle) : ses étiquettes n'ont que 17 composantes, dont la plus grande représente 18 % de l'encre.
- Le signal décroît entre 200 et 1000 µm de décalage, à l'échelle des traits étiquetés (0,4 à 0,6 mm de large). La ROC-AUC locale (médiane 0,585) reste sous la ROC-AUC globale.
- Analyse exploratoire : les étiquettes avaient déjà été lues en phase 14, et aucun protocole n'est modifié.

[Rapport](PHASE15_AUDIT.md)

## Fichiers

| Fichier | Rôle |
| --- | --- |
| `docs/validation/phase15_audit.py`, `phase15-audit.json` | Retrait d'une ROI, ROC-AUC locale et sur le cœur, courbe de décalage, biais de bord, granularité des étiquettes |
| `tests/test_phase15.py` | ROC-AUC locale insensible au contraste entre régions ; granularité d'un rectangle connu |

Aucune étiquette, image ni découpe EduceLab n'est versée : seulement des métriques agrégées. Les superpositions examinées restent dans `data/` (ignoré par Git).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
