# Phase 16 · Pas réel de la PPM contre pas nominal (tâche T2)

**Non, selon le protocole : on garde le pas nominal de 3,24 µm.** Rééchantillonner chaque ROI au pas médian de la PPM ne change pas le classement de l'encre par A : écart moyen de ROC-AUC(Z_out) −0,009 [−0,022 ; +0,004] sur 37 ROI, et Frag2 passe sous le seuil de −0,02. Résultat exploratoire : les étiquettes des six fragments avaient été lues en phases 12 à 14.

## Chronologie

| Étape | Commit |
| --- | --- |
| Protocole figé avant toute préparation au pas réel (règle de pas, inclusion, statistique, décision) | `3dae2c2` · [protocole](validation/phase16-protocol.json) · [script](validation/phase16_scale.py) |
| Préparation sans étiquettes, 46 ROI | `05ea510` · manifestes `validation/phase16-prepare-frag*.json` |
| Inférence de A (deux ordres), poids `36dd0de8…`, manifestes locaux identiques aux manifestes commités | hors Git (`data/phase16`) |
| Évaluation avec le script commité | ce commit · [résultats](validation/phase16-eval.json) |

## Pas mesuré

Le pas médian de la PPM est compris entre 0,94 et 1,05 voxel par pixel UV pour 45 ROI sur 46. Frag6 ROI 2 fait exception (1,21 en lignes, |cos| médian 0,13). La correction d'échelle vaut donc en général 2 à 6 %.

## Résultats (critère primaire)

| | ROI incluses | Écart moyen ROC-AUC(Z_out), réel − nominal | ROC-AUC(Z_out) regroupée au pas réel [IC 95 %] |
| --- | ---: | ---: | --- |
| Frag4 | 2 / 6 | +0,033 | 0,855 [0,807 ; 0,904] |
| Frag1 | 8 / 8 | −0,014 | 0,665 [0,636 ; 0,692] |
| Frag3 | 7 / 8 | −0,015 | 0,506 [0,477 ; 0,533] |
| Frag2 | 7 / 8 | **−0,023** | 0,605 [0,575 ; 0,632] |
| Frag5 | 5 / 8 | +0,007 | 0,755 [0,722 ; 0,787] |
| Frag6 | 8 / 8 | −0,008 | 0,762 [0,732 ; 0,789] |
| **Toutes** | **37** | **−0,009 [−0,022 ; +0,004]** (bootstrap par ROI, 9 999 tirages, graine 216) | |

Règle figée : adopter le pas réel si la borne basse est > 0 et si aucun fragment n'a un écart moyen < −0,02. Aucune des deux conditions n'est remplie.

Secondaires, sans décision : écart moyen de ROC-AUC(Z_in) +0,019 ; part des pixels avec Z_out > 0,5 inchangée (−0,0004) ; Spearman entre la distorsion du pas et l'écart : 0,17.

## Lecture

- **Le pas nominal n'était pas une source d'erreur.** Les maillages publiés sont presque isométriques à l'échelle d'une ROI. La correction est faible et ne change pas le classement.
- **Le résultat utile est l'instabilité des ROI prises une à une.** Un changement d'échelle de 2 à 6 % fait varier la ROC-AUC d'une ROI de −0,09 à +0,08 (Frag5 ROI 7 : 0,746 → 0,658 ; ROI 5 : 0,627 → 0,711). Une ROC-AUC par ROI reste donc indicative, ce qui confirme la consigne de la phase 15 : compter les ROI ou les traits d'encre, et regrouper.
- **Seule ROI vraiment déformée : Frag6 ROI 2.** Elle gagne +0,048. Avec un seul cas, impossible de conclure ; la corrélation avec la distorsion reste faible (0,17).
- Les ROC-AUC regroupées au pas réel reproduisent le classement des fragments des phases 13 et 14 : Frag3 reste au niveau du hasard.

## Limites

- Exploratoire : étiquettes déjà lues, et mêmes ROI que les phases 13 et 14.
- Seul le pas médian par ROI est corrigé ; le cisaillement et les variations à l'intérieur d'une ROI ne le sont pas.
- Le script affiche un avertissement de conversion NaN dans `binned`. Les pixels concernés sont exclus par le masque `valid` (Z_out et Z_in finis), ce qui laisse les métriques inchangées.
