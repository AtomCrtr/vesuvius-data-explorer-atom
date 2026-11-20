# Phase 12 · Première évaluation d'encre de A sur Frag4 (exploratoire)

**Résultat exploratoire ; exclusion directe de Frag4 de l'entraînement de A probable, non attestée.** Aucune lettre n'est annoncée.

## Chronologie

| Étape | Commit | Preuve |
| --- | --- | --- |
| Protocole gelé, étiquettes non téléchargées | `5c0602f` | [phase12-protocol.json](validation/phase12-protocol.json), SHA-256 `dd780774…5174e` |
| Script d'évaluation et règles d'interprétation commités, étiquettes toujours absentes | `f9c965d` | [phase12_ink_eval.py](validation/phase12_ink_eval.py) |
| Téléchargement de `PHercParis1Fr39_54keV_inklabels.png` (98 366 octets, SHA-256 `a6f39eb5…18fc`), évaluation | commit suivant | [phase12-ink-eval.json](validation/phase12-ink-eval.json) |

Le script vérifie le SHA-256 du protocole et ceux des cartes de scores de la phase 11. Ni les ROI, ni la fenêtre, ni la tolérance, ni les seuils, ni les ordres n'ont changé.

**Correction déclarée.** Le premier passage contenait un bug dans le calcul de la bande de tolérance : `minimum(edt(étiquette), edt(non-étiquette))` vaut 0 partout, si bien que la bande ne contenait aucun pixel. La distance au bord est la somme de ces deux distances. La règle écrite n'a pas changé ; un test couvre désormais ce calcul. Les métriques de rang et les hypothèses sont identiques entre les deux passages (premier passage conservé localement : `data/phase11/phase12-ink-eval-run1.json`).

## Hypothèses pré-déclarées : rejetées

Fenêtre principale W2, PR-AUC (précision moyenne), intervalles par blocs de 64², 499 tirages.

| ROI | Prévalence | PR-AUC Z_in [IC 95 %] | PR-AUC Z_out [IC 95 %] | H1 : Z_in > Z_out | H2 : Z_in > prévalence + demi-largeur |
| --- | ---: | ---: | ---: | :---: | :---: |
| 2 | 3,6 % | 0,032 [0,014 ; 0,052] | 0,121 [0,054 ; 0,198] | non | non |
| 5 | 0,74 % | 0,006 [0,002 ; 0,011] | 0,034 [0,008 ; 0,085] | non | non |

**H1 et H2 sont rejetées.** L'ordre « air → papyrus » (Z_in), le seul qui produisait des scores structurés en phase 11, ne classe pas l'encre mieux que le hasard.

## Ce que montrent les deux ordres

| | ROI 2 | ROI 5 |
| --- | ---: | ---: |
| ROC-AUC Z_in, W2 | 0,49 [0,39 ; 0,58] | 0,40 [0,27 ; 0,55] |
| ROC-AUC Z_out, W2 | **0,86** [0,79 ; 0,90] | **0,89** [0,83 ; 0,94] |
| ROC-AUC Z_out, `>> 8` | 0,82 [0,75 ; 0,88] | 0,89 [0,84 ; 0,93] |
| PR-AUC Z_out / prévalence, W2 | 3,4 × | 4,5 × |
| Part des scores Z_out > 0,5 | 0 % | 0 % |

- **Z_out classe l'encre, mais sans jamais la détecter.** Ses scores sont presque constants (≈ 0,12) et jamais supérieurs à 0,5. Seul l'ordre relatif des pixels contient de l'information. Au seuil de 0,5, la sortie ne prédit aucun pixel d'encre.
- **Ce n'est pas une hypothèse pré-déclarée.** Z_out figurait parmi les ordres mesurés, mais aucune hypothèse ne le concernait. Ce résultat appelle une confirmation sur d'autres ROI et d'autres fragments.
- **Robustesse.** Le résultat est stable entre les fenêtres W2 et `>> 8`, et sur la ROI 2 pour des décalages de ±100 µm (PR-AUC de 0,098 à 0,121). Sur la ROI 5, la PR-AUC varie de 0,017 à 0,045 à ±50 µm et de 0,001 à 0,064 à ±100 µm en ligne : avec 0,7 % de pixels d'encre, quelques traits suffisent à la déplacer.

## Métriques au pixel et à tolérance

Au-delà de 301 µm d'un bord d'étiquette, il reste 684 000 pixels sur la ROI 2 et 779 000 sur la ROI 5, **mais aucun pixel d'encre** : aucun trait ne fait plus de 602 µm de large. Les métriques au pixel (précision, rappel, Dice, Jaccard) sont donc indéfinies, comme le prévoit la règle. Les faux positifs loin de toute encre restent mesurables : Z_in au seuil de 0,5 en place 47 693 sur la ROI 2 et 17 052 sur la ROI 5, contre 0 pour Z_out.

| Top 5 % des scores, W2 | Précision à 301 µm | Rappel à 301 µm |
| --- | ---: | ---: |
| ROI 2, Z_in / Z_out | 0,03 / 0,40 | 0,14 / 0,96 |
| ROI 5, Z_in / Z_out | 0,21 / 0,28 | 0,31 / 1,00 |

Le niveau de hasard de ces métriques à tolérance n'est pas calculé. Elles ne servent qu'à comparer les deux ordres à part égale de pixels prédits.

## Contrôle a posteriori : l'intensité brute

Ce contrôle a été ajouté après les résultats et n'est pas dans le protocole ; il est seulement descriptif. [Script](validation/phase12_baseline.py) · [Valeurs](validation/phase12-baseline.json)

- Pris un par un, les plans de l'entrée W2 donnent une ROC-AUC de 0,36 à 0,58 sur la ROI 2 et de 0,39 à 0,64 sur la ROI 5. L'encre est un peu plus sombre au niveau de la surface : le minimum tombe aux plans 32 et 31 (couches 33,0 et 32,3 de Frag4). Ce creux à la surface publiée confirme que les étiquettes sont bien calées sur la grille de surface.
- Même avec le meilleur plan et le signe le plus favorable, choisis après coup, l'intensité seule (≈ 0,64) reste loin de Z_out (0,86 et 0,89). Le classement de Z_out ne se réduit donc pas à un seuil d'intensité. D'autres indices simples, comme la texture ou l'épaisseur, n'ont pas été testés.

## Limites

- Deux ROI d'environ 2,3 mm de côté et une seule fenêtre de profondeur. La ROI 5 contient environ 6 400 pixels d'encre.
- L'autocorrélation spatiale dépasse la taille des blocs (142 µm), donc les intervalles sont optimistes.
- La normalisation ÷ 255/÷ 200 et l'ordre attendu restent sans réponse ([villa#2627](https://github.com/ScrollPrize/villa/issues/2627)).
- Le pas latéral n'est pas isométrique (T2 de la feuille de route).
- L'ascendance des étiquettes et le pré-entraînement de A ne sont pas documentés : une fuite indirecte n'est pas exclue.

## Conséquences

1. La lecture de la phase 11 (« A ne répond que de l'air vers le papyrus ») était trompeuse : la réponse structurée de Z_in ne suit pas l'encre. La note communautaire le laissait ouvert (« says nothing about which order finds ink ») ; un complément est rédigé, non envoyé. [Complément](PHASE12_COMMUNITY_FOLLOWUP.md)
2. Une seule chaîne de A ne peut pas trancher sur l'ordre attendu. Pour la phase 13, il faudrait pré-enregistrer **H3 : ROC-AUC(Z_out) > 0,5 + demi-largeur** sur de nouvelles ROI de Frag4 non encore vues, puis sur Frag1 et Frag3, avec la même recette.
