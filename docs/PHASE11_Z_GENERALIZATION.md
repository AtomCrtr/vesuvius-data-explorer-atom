# Phase 11 · Sensibilité à l'ordre Z sur Frag4

**L'effet observé sur PHerc0500P2 se retrouve sur Frag4 : inverser l'ordre des 62 plans décorrèle les scores de A et rend leurs top 1 % disjoints. Il s'y ajoute une asymétrie franche : A ne produit de réponse structurée que si les plans vont de l'air vers l'intérieur du papyrus.** Il s'agit d'une mesure de sensibilité sans étiquettes, sur une entrée hors recette ; elle ne dit pas laquelle des deux sorties détecte l'encre.

## Protocole

- Deux ROI de 1 024 × 1 024 pixels à 2,215 µm (≈ 2,27 mm de côté), centrées sur les patchs 2 et 5 de la liste géométrique gelée du contrôle B1, entièrement dans le masque. Choix aveugle aux scores et aux étiquettes.
- Entrée construite selon la [fiche de compatibilité](PHASE11_CHECKPOINT_COMPATIBILITY.md) ; `Z_out` = plans croissants vers l'air, `Z_in` = l'inverse. Même tableau, mêmes poids, mêmes tuiles 256/128, même fusion Hann ; seule change l'orientation de l'axe de profondeur.
- CUDA FP32 déterministe, RTX 4080 Laptop, torch 2.8.0+cu126, 49 tuiles par carte. La tuile centrale relancée dans le même processus reproduit les scores au bit près dans les quatre cartes.
- Support : masque érodé de 16 px et poids de fusion ≥ 25 % du maximum, 876 272 pixels par ROI.

[Script](validation/phase11_z_frag4.py) · [Résultats](validation/phase11-z-frag4.json)

## Résultats

| | ROI 2 | ROI 5 |
| --- | ---: | ---: |
| Pearson / Spearman Z_out–Z_in | 0,024 / 0,029 | 0,073 / −0,080 |
| Écart absolu moyen [IC 95 %, blocs 64²] | 0,086 [0,066 ; 0,105] | 0,047 [0,037 ; 0,059] |
| Top 1 % communs | 0 / 8 763 | 0 / 8 763 |
| Top 5 % : Jaccard | 0,000 | 0,106 |
| Top 10 % : Jaccard | 0,029 | 0,103 |
| Score moyen Z_out / Z_in | 0,127 / 0,212 | 0,124 / 0,171 |
| P99 Z_out / Z_in | 0,170 / 0,841 | 0,142 / 0,711 |
| Part > 0,5, Z_out / Z_in | 0 % / 8,3 % | 0 % / 2,6 % |

## Lecture

- **Généralisation qualitative de l'effet.** Comme sur PHerc0500P2 (Spearman 0,021, top 1 % disjoints sur 790 200 pixels), le classement des pixels ne survit pas à l'inversion.
- **Amplitude plus faible, pour une raison identifiable.** L'écart moyen (0,05–0,09) est inférieur aux 0,247 de la phase 8 parce qu'en `Z_out` la sortie de A est presque constante (≈ 0,12, aucun pixel au-dessus de 0,5). L'écart mesure surtout la structure produite en `Z_in`.
- **Sens physique.** `Z_in` place l'air dans les premiers plans et s'enfonce dans le papyrus ; c'est l'ordre dans lequel A « répond ». La branche `frag4` du script Villa (`reverse_layers=False`, couches croissantes) correspond à `Z_out`, ce qui suggère qu'un `xyz_scale` ou un autre prétraitement intervenait aussi, ou que cette branche visait un autre modèle. On ne peut pas en déduire l'ordre « correct » sans étiquettes.
- **Limites.** Deux ROI d'un seul fragment ; entrée hors recette (air non nul, pas nominal) ; blocs de 64² autocorrélés au-delà de 64 px, donc intervalles optimistes. La face écrite de Frag4 est connue (surface exposée), ce qui fera de Frag4 un bon test de l'ordre une fois l'évaluation débloquée.

Aucune image de score n'est versée au dépôt : les cartes restent sous `data/phase11/` (`z-frag4-scores.npz`, SHA-256 dans le JSON), conformément à la licence EduceLab.
