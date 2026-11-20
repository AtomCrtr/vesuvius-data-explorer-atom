# Phase 11 · Décisions appliquées : tolérance, fenêtre, envoi

Trois décisions prises le 21 novembre 2026 à la demande du responsable du projet. Les étiquettes d'encre de Frag4 restent fermées ; le protocole d'évaluation est gelé dans [phase12-protocol.json](validation/phase12-protocol.json) avant leur ouverture.

## 1 · Tolérance de recalage

Le critère « RMS < 2 px CT » est remplacé, pour les références optiques plus grossières que le CT, par une **tolérance spatiale** : `max(|biais| + 3σ robuste, 2 px de la grille la plus grossière)`, avec σ = 1,4826 × MAD de résidus indépendants. Les métriques au pixel ne sont valides que si `|biais| + 3σ ≤ 2 px CT`. Fonction `core.optical_registration.registration_tolerance`, testée.

Sur Frag4, résidus des fissures (`phase11-cracks.json`), pixel IR natif 19,6 µm :

| Résidus | n | Biais | σ robuste | Tolérance |
| --- | ---: | ---: | ---: | ---: |
| Fissure supérieure | 64 | 13 µm | 67 µm | 215 µm |
| **Deux fissures (retenu, plus conservateur)** | 77 | 13 µm | 96 µm | **301 µm** |

Les pixels à moins de 301 µm (≈ 93 px CT) d'un bord d'étiquette seront exclus des métriques au pixel. Métriques au pixel non valides sur Frag4.

## 2 · Fenêtre d'intensité

Calculée sur le CT seul, 8 patchs de 128 × 128 px centrés sur les patchs géométriques gelés. [Script](validation/phase11_window.py) · [Valeurs](validation/phase11-window.json)

- **W1, air → 0** (gelée la première) : air 24 918, haut 60 024 (P99,9 du papyrus). Elle écrête à 0 **33 %** des voxels de papyrus, plus sombres que l'air dans ce volume DLS ; moyenne du papyrus 0,17 contre 0,38 dans la recette. Écartée.
- **W2, ajustement des moments** (principale, décidée après avoir vu les statistiques de W1, jamais d'étiquette ni de score) : moyenne 26 402 et écart-type 7 416 des couches 11–53 ramenés à 0,379 et 0,148, ceux de la tuile PHerc0500P2 vérifiée. Saturation 0,08 %, zéros 0,39 %.

Contrôle sans étiquettes : l'expérience Z relancée avec W2 donne le même schéma qu'avec `>> 8`. [Résultats](validation/phase11-z-frag4-w2.json)

| | ROI 2 | ROI 5 |
| --- | ---: | ---: |
| Spearman Z_out–Z_in | 0,027 | −0,006 |
| Écart absolu moyen [IC 95 %] | 0,071 [0,054 ; 0,086] | 0,043 [0,035 ; 0,055] |
| Top 1 % communs | 0 | 0 |
| Part > 0,5, Z_out / Z_in | 0 % / 6,0 % | 0 % / 2,3 % |

L'asymétrie (réponse seulement de l'air vers le papyrus) ne s'explique donc pas par le niveau de l'air.

## 3 · Envoi aux mainteneurs

La [note corrigée](PHASE11_COMMUNITY_NOTE.md) et ses trois questions (données exactes d'entraînement de A, normalisation ÷ 255/÷ 200, ordre attendu pour une surface exposée) sont envoyées sous forme d'issue publique sur `ScrollPrize/villa`, le dépôt où les mainteneurs ont répondu aux issues #1377 et #1765. Elle ne contient ni image, ni extrait, ni transcription Frag4, conformément à la licence EduceLab. Le lien de l'issue est consigné dans le bilan de phase 11.
