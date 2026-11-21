# Phase 14 · Z_out comme ordre par défaut : test sur trois fragments réservés

**Oui, selon le protocole.** Sur Frag2, Frag5 et Frag6, dont aucune étiquette n'avait été lue, l'ordre papyrus → air (Z_out) classe l'encre au-dessus du hasard, mieux que l'ordre inverse et mieux que les témoins non appris. Le critère pré-déclaré (H3 dans les trois fragments) est rempli. Résultat exploratoire : Frag2 a servi au concours Kaggle 2023, et l'exclusion de Frag5 et Frag6 de l'ascendance de A n'est pas attestée. Aucune lettre n'est annoncée.

## Chronologie

| Étape | Commit |
| --- | --- |
| Découverte sur les 19 ROI déjà étiquetées : aucun sélecteur sans étiquettes ne bat « toujours Z_out » | `5490336` · [script](validation/phase14_discovery.py) · [valeurs](validation/phase14-discovery.json) |
| Protocole figé (SHA-256 `ccfd56c7…d94b`, vérifié par le script, qui refuse toute version modifiée) | `5490336` · [protocole](validation/phase14-protocol.json) |
| Préparation sans étiquettes et inférence de A | `8f1af22` · [Frag2](validation/phase14-prepare-frag2.json) · [Frag5](validation/phase14-prepare-frag5.json) · [Frag6](validation/phase14-prepare-frag6.json) |
| Téléchargement des étiquettes, évaluation avec le script commité | commit suivant · [résultats](validation/phase14-eval.json) |

L'évaluation a été lancée avec la version commitée de `phase13_eval.py`. La version fusionnée avec `main` (`c2cef13`, d'un autre processus : vérification centralisée du protocole, bootstrap par matrices creuses) donne un JSON identique, en 11 s au lieu de plusieurs minutes.

## Découverte (données déjà vues)

| Règle | ROC-AUC moyenne sur 19 ROI |
| --- | ---: |
| Toujours Z_out | **0,675** |
| Toujours Z_in | 0,562 |
| Moyenne des rangs des deux ordres | 0,651 |
| Choisir l'ordre à la carte la plus structurée (écart-type, queue, cohérence) | 0,562 (7 bons choix sur 19) |
| Choisir l'ordre le plus corrélé à la surface | 0,610 |
| Oracle (meilleur ordre connu) | 0,713 |

## Contrôles sans étiquettes

| | Frag2 | Frag5 (70 keV) | Frag6 (53 keV) |
| --- | ---: | ---: | ---: |
| Écart-type moyen, couches 0–12 / 52–64 | 6 073 / 1 089 | 9 184 / 4 313 | 9 635 / 1 658 |
| Côté air | couches hautes | couches hautes | couches hautes |
| Couche de surface | z = 32 (PPM identité) | 65 couches, pas de PPM identité | 65 couches, pas de PPM identité |
| W2 : moyenne / écart-type (uint16) | 25 497 / 6 425 | 25 642 / 9 067 | 28 760 / 7 869 |
| Répétition de l'inférence | identique au bit près | identique | identique |

## Résultats (ROI regroupées, bootstrap apparié 64², 499 tirages)

| | Frag2 | Frag5 | Frag6 |
| --- | ---: | ---: | ---: |
| ROI incluses / préparées | 7 / 8 | 5 / 8 | 8 / 8 |
| Prévalence | 22,9 % | 21,7 % | 17,6 % |
| ROC-AUC Z_out [IC 95 %] | **0,630** [0,599 ; 0,658] | **0,730** [0,696 ; 0,760] | **0,768** [0,740 ; 0,794] |
| ROC-AUC Z_in | 0,494 | 0,458 | 0,528 |
| ROC-AUC B1 / B2 | 0,51 / 0,59 | 0,52 / 0,47 | 0,48 / 0,52 |
| PR-AUC Z_out − Z_in | +0,080 [0,055 ; 0,107] | +0,311 [0,250 ; 0,362] | +0,251 [0,198 ; 0,309] |
| ROC-AUC Z_out − meilleur témoin | +0,044 [0,004 ; 0,084] | +0,215 [0,177 ; 0,251] | +0,245 [0,212 ; 0,279] |
| H3 / H4 / H5 | oui / oui / oui | oui / oui / oui | oui / oui / oui |

## Lecture

- **Le défaut tient sur les fragments réservés.** Avec les phases 12 et 13, Z_out dépasse le hasard sur cinq fragments sur six (Frag1, Frag2, Frag4, Frag5, Frag6). Frag3 reste l'exception.
- **L'effet est modeste et inégal.** Sur Frag2, la marge sur la texture locale (B2 = 0,59) est faible : sa borne basse est de 0,004. Plusieurs ROI restent sous 0,5 (Frag2 ROI 7 : 0,49 ; Frag6 ROI 6 : 0,46), et Z_in l'emporte sur 4 des 7 ROI de Frag2, bien qu'il perde une fois les ROI regroupées.
- **Deux ROI sont presque parfaites** (Frag5 ROI 1 : 0,987 ; Frag6 ROI 7 : 1,000, avec seulement 7 346 pixels d'encre). Elles mériteraient un examen visuel en local, licence oblige, avant d'en tirer quoi que ce soit.
- **Une recommandation pratique, pas une preuve de détection.** Pour un nouveau fragment sans étiquettes, utiliser Z_out plutôt que Z_in est désormais justifié. Cela ne dit pas que A lit l'encre de façon fiable : les scores restent bas en valeur absolue (phase 12).

## Limites

- Frag2 a servi au concours Kaggle, et l'ascendance de A reste inconnue pour Frag5 et Frag6 ([villa#2627](https://github.com/ScrollPrize/villa/issues/2627), sans réponse).
- Les étiquettes de Frag2, Frag5 et Frag6 ne sont pas validées géométriquement contre l'IR. Sur Frag5 et Frag6, la couche de surface n'est vérifiée que par le nombre de couches.
- Les intervalles sont optimistes, car l'autocorrélation spatiale dépasse la taille des blocs.
- Frag5 a été scanné à 70 keV ; la fenêtre W2 compense l'intensité, pas le contraste propre à cette énergie.
