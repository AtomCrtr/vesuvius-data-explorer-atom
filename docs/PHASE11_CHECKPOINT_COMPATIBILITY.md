# Phase 11 · Compatibilité du checkpoint A avec Frag4

**Le checkpoint A s'exécute sur Frag4 après rééchantillonnage, mais son entrée n'est pas dans le domaine de la recette : air non nul, intensité moyenne +37 %, résolution native 1,46 fois plus grossière et aplatissement non isométrique.** Une sortie de A sur Frag4 est donc une mesure hors distribution. Elle ne peut pas servir de test de généralisation tant que ces écarts ne sont pas corrigés ou bornés.

## Comparaison point par point

| Paramètre | Recette A (sources) | Frag4 | Traitement en phase 11 | Statut |
| --- | --- | --- | --- | --- |
| Poids | `r152_3ddec_v2_l5_epoch13.ckpt`, SHA-256 `36dd0de8…`, ResNet-152 3D + décodeur 3D, `BatchNorm3d(1)` en entrée | — | Vérifié avant chargement, `weights_only=True` | Conforme |
| Résolution | ≈ 2,2–2,4 µm (segments 2 µm de PHerc0139, 0500P2, 0009B, 0814, 0841…) | 3,24 µm nominal, 3,05–4,09 µm réel selon la zone | Rééchantillonné à 2,215 µm, trilinéaire | **Écart** : l'information native est plus grossière ; le pas réel varie de ±25 % |
| Plans | 62, centrés sur la surface (fenêtre 23–85 d'un volume de 109 couches, Villa #1766) | 65 couches, surface en 32 | 62 plans à (k − 58,5) × 2,215 µm autour de 32, soit les couches 11,1 à 52,9 | Conforme en profondeur physique (±67,5 µm) |
| Ordre Z | Selon le segment : `reverse_layers` est fixé au cas par cas dans le script d'entraînement (vrai pour `500p2a`, faux par défaut et pour la branche `frag4`) | n sort du papyrus | Deux conditions nommées par direction physique, `Z_out` et `Z_in` | Indéterminé a priori ; mesuré en [Z](PHASE11_Z_GENERALIZATION.md) |
| Type et intensité | uint16 → uint8 par `>> 8` (`_from_uint16_to_uint8`), écrêtage 200 | uint16 DLS 54 keV, air ≈ 24 500 | `>> 8` puis écrêtage 200 | **Écart** : l'air vaut ≈ 0,48 après normalisation (≈ 0 sur PHerc0500P2) ; moyenne 0,52 contre 0,38 |
| Normalisation | Inférence : ÷ 200 (`max_clip_value = 200`). Entraînement : `A.Normalize(mean=0, std=1)` avec le diviseur par défaut d'Albumentations, 255 | — | ÷ 200, la règle d'inférence reproduite à un niveau près en phase 7 | **Question ouverte** sur la cohérence entraînement/production (voir ci-dessous) |
| Tuiles | 256 × 256, pas 128 (production), fusion Hann | — | Identique, FP32 déterministe | Conforme |
| Masque | Support non nul de la pile | Masque publié, sans zéro dans la pile | Masque publié érodé de 16 px, poids de fusion ≥ 25 % du maximum | Conforme |
| Domaine | Rouleaux et fragments scannés à l'ESRF/DLS 2023–2026, rendus 8 bits | Fragment 2023, DLS 54 keV, surface exposée | — | Décalage de domaine non quantifié au-delà des statistiques d'intensité |

Les statistiques d'intensité comparent les deux ROI Frag4 préparées à la tuile PHerc0500P2 vérifiée en phase 6, après la même règle : moyenne 0,520 et 0,521 contre 0,379 ; écart-type 0,139 contre 0,148 ; voxels saturés 0,23 % contre 0,01 %.

## Normalisation : entraînement ÷ 255, production ÷ 200 ?

Le script d'entraînement public dont les identifiants correspondent à A applique `A.Normalize(mean=[0]*62, std=[1]*62)`, dont le `max_pixel_value` par défaut est 255. Le code d'inférence épinglé divise par 200. Si les deux ont réellement servi, la production fournit au modèle des entrées 1,275 fois plus fortes qu'à l'entraînement, et la `BatchNorm3d` d'entrée, figée en évaluation, ne l'absorbe pas.

Les statistiques courantes du checkpoint (`running_mean` 0,279, `running_var` 0,061) ne tranchent pas sur une seule tuile : la moyenne est plus proche de ÷ 255 (0,297) que de ÷ 200 (0,379), mais la variance s'explique mieux par ÷ 200 avec des zéros de remplissage. C'est une question à poser aux mainteneurs, pas un défaut démontré. Elle n'affecte pas la reproduction des cartes publiées, qui utilisent la même règle ÷ 200.

## Ce qui rendrait l'entrée compatible

1. Une fenêtre d'intensité qui ramène l'air à 0 et le papyrus dans la plage des volumes d'entraînement, **fixée sur le CT seul** (par exemple niveau de l'air et percentile du papyrus mesurés hors des zones étiquetées), avant toute ouverture des étiquettes.
2. Un rééchantillonnage qui suit le pas réel de la PPM plutôt que le pas nominal, ou au minimum une carte du facteur d'échelle local pour stratifier les résultats.
3. La réponse des mainteneurs sur ÷ 255 / ÷ 200 et sur l'ordre Z attendu pour une surface exposée.

L'application réussie d'un checkpoint n'établit pas sa généralisation : ici, même l'application est hors recette sur deux paramètres.
