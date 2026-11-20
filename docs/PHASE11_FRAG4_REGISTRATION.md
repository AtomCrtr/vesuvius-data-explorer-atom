# Phase 11 · Contrôle géométrique aveugle de Frag4

**La chaîne CT natif → maillage → volume de surface est validée sous le quart de voxel. Le lien volume de surface → IR aligné ne l'est pas : son erreur, d'environ 50 µm en médiane le long d'une fissure, dépasse d'un ordre de grandeur le seuil pré-déclaré.** Les étiquettes d'encre et toute prédiction sont restées fermées pendant ces mesures ; elles n'ont jamais été téléchargées.

## Chaîne et conventions établies

| Lien | Convention vérifiée | Preuve |
| --- | --- | --- |
| Repère CT | Indices de voxel ZYX du volume **recadré** publié (Zarr ou TIFF), centre de voxel = indice entier, pas de décalage ±0,5. | B1, 0/72 comparaisons hors volume, optimum de décalage en (0, 0, 0) au pas de 0,25 voxel. |
| UV → CT | `extras/PHercParis1Fr39_54keV.ppm` : x, y, z, nx, ny, nz en voxels, ordre XYZ, pixels nuls = invalides. | B1. L'autre PPM du dossier est une identité (voir l'inventaire). |
| Couche k | `p + (k − 32) · n`, normale PPM telle quelle (`invert_normals: false`), interpolation trilinéaire. | B1 : MAE 230 / 65 535 contre 929 en plus proche voisin et > 1 280 avec un décalage de centre. |
| Sens de la normale | **n sort du papyrus** : au-delà de la couche ~38, intensité constante ≈ 24 500 (air) ; en dessous de 32, texture du papyrus. | Profils de profondeur des 8 patchs. |
| Pas latéral | Non isométrique : 0,94 à 1,26 voxel par pixel UV selon la zone et l'axe (3,05 à 4,09 µm). | Pas médians des 8 patchs. Toute conversion en µm à 3,24 µm/px est nominale, à ±25 % près localement. |
| IR aligné | Même grille 6 064 × 9 791 que le volume de surface, IR natif ≈ 20 µm/px suréchantillonné ≈ 6 fois, tourné de 180° depuis le cliché brut, sans miroir. | Inventaire, inspection des formes. |

Rappel : `core.alignment.grid_normals` donne la normale opposée à la convention XYZ de VC3D (produit vectoriel sur des composantes ZYX). Ce n'est pas un défaut de calcul, mais la docstring et un test le documentent désormais. [Revue](CLAUDE_FULL_REVIEW.md#p1)

## B1 · CT natif → maillage → couches publiées

Huit patchs de 32 × 32 pixels, choisis par une règle gelée sur le seul masque (érosion de 160 px, fractions fixes de la boîte englobante). Pour chacun, la PPM est lue par plages HTTP, le CT natif est échantillonné aux 9 couches 0, 8, …, 64 et comparé aux couches publiées. [Script](validation/phase11_geometry.py) · [Résultats](validation/phase11-geometry-ppm.json)

- Pearson par couche de **0,983 à 0,999** sur les 72 comparaisons, MAE moyenne 230 niveaux sur 65 535, soit moins d'un niveau en 8 bits.
- Balayage 3D de décalages de −1 à +1 voxel au pas de 0,25 : optimum exactement en (0, 0, 0) pour les couches 0, 32 et 64. L'erreur résiduelle de la chaîne est **inférieure à 0,25 voxel (0,8 µm)**.
- Couverture : 8 patchs de 1 024 pixels, répartis sur 4 rangées et 2 colonnes du fragment. Les bords et les zones de forte courbure ne sont pas testés.

## B2 · Volume de surface → IR aligné, mesures globales

[Script](validation/phase11_ir_registration.py) · [Résultats](validation/phase11-ir-registration.json)

Le contour du maillage CT (issu de la segmentation CT, donc indépendant de l'IR et de l'encre) est comparé au contour du fragment détecté sur l'IR, à l'échelle ¼ (12,96 µm/px nominal).

| Mesure | Valeur (px ¼) | Valeur nominale |
| --- | ---: | ---: |
| IoU des supports | 0,956 | |
| Distance symétrique médiane / RMS / P90 | 15,1 / 17,4 / 26,2 | 196 / 226 / 339 µm |
| Bord CT à l'extérieur du bord IR, médiane signée | +12,7 | 165 µm |
| Meilleur RMS après érosion uniforme du support CT (8 px) | 15,4 | 199 µm |

Le maillage déborde donc le papyrus vu en IR d'un liseré d'environ 165 µm, et un résidu local d'environ 200 µm RMS subsiste. Les définitions de bord diffèrent entre modalités (bord effiloché, seuil IR, liseré du maillage) : cette mesure est une **borne supérieure grossière**, pas une estimation fine.

La corrélation de phase des gradients par blocs, prévue pour mesurer un champ de déplacement local, **a échoué** : 0 bloc accepté sur 489 (NCC médiane 0,01, P99 0,14 pour un seuil de 0,20). L'IR ne partage avec le CT ni la texture des fibres ni d'autre structure fine que les fissures et le contour. Aucun ajustement rigide ou affine n'a donc pu être évalué sur des blocs réservés.

## B3 · Fissures partagées, mesure perpendiculaire

Les deux fissures horizontales sont visibles dans les deux modalités et indépendantes de l'encre. Fenêtres fixées sur leur géométrie visible avant la mesure ; par bande de 8 colonnes, centre de l'interstice CT (minimum de texture) et trait sombre fin de l'IR (filtre de crête). [Script](validation/phase11_cracks.py) · [Résultats](validation/phase11-cracks.json)

| Fissure | Bandes retenues | Biais médian | σ robuste (1,4826 × MAD) | \|dy\| médian [IC bootstrap] |
| --- | ---: | ---: | ---: | ---: |
| Supérieure | 64 / 146 | +1 px ¼ (13 µm) | 5,2 px ¼ (67 µm) | 4 px ¼ = **52 µm** [32 ; 65] |
| Inférieure | 13 / 25 | −1 px ¼ | 37 px ¼ | non concluant |

RMS et P90 (316 µm et 654 µm sur la fissure supérieure) sont dominés par des décrochages des traceurs (interstice CT parallèle à gauche, traits d'encre côté IR) et ne mesurent pas le recalage. L'intervalle bootstrap est optimiste, les bandes voisines étant corrélées. Seule la composante perpendiculaire aux fissures est observée ; la composante parallèle n'est bornée que par le contour.

## Déviations de protocole, déclarées

1. **B2, passage 1** (pleine résolution, blocs 256 px, support CT par seuil d'intensité) : 0/585 blocs, IoU 0,003, le seuil isolait les fibres. **Passage 2** (échelle ¼, support CT par écart-type local) : IoU 0,12, la texture remplit tout le maillage. **Passage 3** (support CT = maillage) : résultats ci-dessus. Le critère d'acceptation des blocs n'a jamais changé.
2. **B3, passage 1** : critères d'amplitude en plus de la continuité ; 23 bandes, dont des bandes hors fissure visibles sur les superpositions. **Passage 2** : continuité seule (médiane glissante sur 9 bandes). Le passage 1 est conservé localement (`data/phase11/phase11-cracks-run1.json`).

Ces changements visaient la fiabilité des détecteurs ; aucun n'a utilisé d'étiquette ni de prédiction. Ils ont été décidés après avoir vu des résultats intermédiaires, ce qui limite la valeur confirmatoire des chiffres B2/B3.

## Verdict du critère pré-déclaré

Le protocole des phases 9–10 exige RMS et P90 réservés inférieurs à `min(2 px CT, largeur d'intérêt / 4)` = min(6,5 µm, 25 µm) = **6,5 µm**, avec une couverture d'au moins 25 %. Le résidu médian seul (52 µm) dépasse ce seuil d'un facteur 8 ; la couverture validée se limite à une fissure. **Échec.**

Ce seuil est d'ailleurs inatteignable avec cette référence optique : un pixel IR natif mesure environ 20 µm. Le plancher réaliste est d'un ou deux pixels IR (20–40 µm). Toute évaluation d'encre sur Frag4 devra fixer à l'avance une tolérance spatiale compatible, par exemple une zone d'incertitude de 3σ ≈ 200 µm autour des bords des étiquettes. C'est une décision à prendre avant d'ouvrir les étiquettes. [Évaluation](PHASE11_INK_EVALUATION.md)
