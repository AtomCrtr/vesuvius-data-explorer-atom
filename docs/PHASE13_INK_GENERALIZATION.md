# Phase 13 · Le classement de l'encre par Z_out se généralise-t-il ?

**Non, pas au sens du protocole.** La généralisation exigeait H3 dans les trois fragments ; elle tient sur Frag4 et Frag1, pas sur Frag3. Résultat exploratoire : Frag1 et Frag3 sont des fragments d'entraînement du concours Kaggle 2023, et leur exclusion de l'ascendance de A n'est pas attestée. Aucune lettre n'est annoncée.

## Chronologie

| Étape | Commit |
| --- | --- |
| Protocole et script figés, aucun score de phase 13, étiquettes de Frag1/Frag3 absentes | `c9f6398` · [protocole](validation/phase13-protocol.json) (SHA-256 `d5de92ab…1017`) · [script](validation/phase13_eval.py) |
| Préparation sans étiquettes (sens, fenêtre, ROI) et inférence de A dans les deux ordres | `b4129f6` · [Frag4](validation/phase13-prepare-frag4.json) · [Frag1](validation/phase13-prepare-frag1.json) · [Frag3](validation/phase13-prepare-frag3.json) |
| Téléchargement des étiquettes de Frag1 et Frag3, évaluation | commit suivant · [résultats](validation/phase13-eval.json) |

Aucune règle n'a été modifiée après l'ouverture des étiquettes.

## Contrôles sans étiquettes

| | Frag4 (contrôle positif) | Frag1 | Frag3 |
| --- | ---: | ---: | ---: |
| Écart-type moyen, couches 0–12 / 52–64 | 7 806 / 1 349 | 8 112 / 930 | 7 120 / 1 183 |
| Côté air retenu | couches hautes | couches hautes | couches hautes |
| z de la PPM identité | 32 | 32 | 32 |
| W2 : moyenne / écart-type (uint16) | 26 402 / 7 416 (= phase 11) | 24 207 / 8 242 | 26 453 / 6 415 |
| Répétition de l'inférence | identique au bit près | identique | identique |

Z_out désigne donc partout l'ordre physique papyrus → air.

## Hypothèses (ROI regroupées par fragment, bootstrap apparié par blocs de 64², 499 tirages)

| | Frag4, nouvelles ROI | Frag1 | Frag3 |
| --- | ---: | ---: | ---: |
| ROI incluses / préparées | 2 / 6 | 8 / 8 | 7 / 8 |
| Prévalence | 4,5 % | 23,0 % | 18,8 % |
| ROC-AUC Z_out [IC 95 %] | **0,818** [0,747 ; 0,891] | **0,673** [0,644 ; 0,699] | 0,520 [0,491 ; 0,548] |
| ROC-AUC Z_in | 0,603 [0,497 ; 0,705] | 0,504 [0,478 ; 0,531] | 0,580 [0,550 ; 0,610] |
| ROC-AUC B1 / B2 (non appris) | 0,48 / 0,53 | 0,52 / 0,49 | 0,50 / 0,52 |
| PR-AUC Z_out − Z_in | +0,223 [0,076 ; 0,407] | +0,205 [0,164 ; 0,244] | **−0,036** [−0,058 ; −0,016] |
| ROC-AUC Z_out − meilleur témoin | +0,290 [0,210 ; 0,372] | +0,158 [0,125 ; 0,188] | −0,003 [−0,039 ; 0,031] |
| **H3** (Z_out au-dessus du hasard) | oui | oui | **non** |
| **H4** (Z_out > Z_in en PR-AUC) | oui | oui | **non** (inverse) |
| **H5** (Z_out > témoins non appris) | oui | oui | non |

## Lecture

- **Frag4.** Le classement observé en phase 12 se retrouve sur deux nouvelles ROI : ROC-AUC 0,88 et 0,81. Les quatre autres ROI ne contiennent aucune étiquette d'encre et sont exclues par la règle : les étiquettes publiées ne couvrent qu'une partie du fragment.
- **Frag1.** L'effet est significatif mais modéré (0,67) et inégal d'une ROI à l'autre (0,48 à 0,81). Z_in est au niveau du hasard en moyenne, avec trois ROI sous 0,4 (0,30 ; 0,34 ; 0,39).
- **Frag3.** Z_out ne classe pas l'encre (0,52), et Z_in fait légèrement mieux (0,58). La ROI 7 donne 0,91 pour Z_in contre 0,76 pour Z_out. L'ordre qui « marche » change donc selon le fragment, voire selon la ROI.
- **Témoins non appris.** L'intensité de surface (B1) et la texture locale (B2) restent proches de 0,5 partout. Ce que A exploite n'est donc pas ce signal simple, mais ce signal ne lui permet pas de choisir un ordre stable.
- **Conséquence pratique.** Aucun des deux ordres ne peut être recommandé pour un fragment nouveau sans étiquettes. Cela renforce la question posée aux mainteneurs ([villa#2627](https://github.com/ScrollPrize/villa/issues/2627)) sur l'ordre et la normalisation d'entraînement.

## Limites

- Frag1 et Frag3 ont servi au concours Kaggle 2023 : une fuite par le pré-entraînement ou par des pseudo-étiquettes est possible et pourrait favoriser un ordre.
- Les étiquettes de Frag1 et Frag3 ne sont pas validées géométriquement contre l'IR, contrairement à celles de Frag4 (phase 11).
- Les intervalles sont optimistes, car l'autocorrélation spatiale dépasse la taille des blocs (142 µm). Sur Frag4, seules 2 ROI sont incluses.
- La normalisation reste celle de W2 ; le pas latéral non isométrique n'est pas corrigé (tâche T2).
- Les pixels hors couverture des tuiles (NaN) produisent un avertissement de conversion ; ils sont exclus des pixels valides et sans effet sur les métriques.

## Suite proposée

1. Attendre la réponse des mainteneurs sur l'ordre et la normalisation avant toute autre conclusion sur A.
2. Tester l'hypothèse d'un ordre propre à chaque fragment : pré-enregistrer un critère sans étiquettes (par exemple la structure des scores) qui prédirait l'ordre utile, puis le vérifier sur Frag2, Frag5 et Frag6.
3. Ne plus utiliser les ROI déjà vues de Frag1, Frag3 et Frag4 comme données de confirmation.
