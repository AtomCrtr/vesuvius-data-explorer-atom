# Audit de la profilométrie PHerc0500P2

Le fichier numérique de ν2 confirme un pas **dans l’export** de 0,68793625 µm par pixel sur les deux axes. La publication indique 0,34 µm. Une calibration instrumentale ou une mesure indépendante reste nécessaire pour fixer l’échelle physique du champ. [Article, Scientific Reports 16, 27835](https://doi.org/10.1038/s41598-026-58467-1) · [Fiche du jeu et avis du 3 septembre 2026](https://huggingface.co/datasets/scrollprize/profilometer)

## Version, acquisitions et choix du pilote

Jeu 1.0.0, révision `a806bead2f3b9100c20e19de37814fb285cfeefd`, licence CC BY-NC 4.0. L’article publié en ligne le 18 juin 2026 identifie PHerc. 500P2 comme une pièce détachée du cassetto 28. Il décrit le mode confocal d’un Sensofar S lynx 2, une sensibilité verticale annoncée de 8 nm et une acquisition en champ clair associée à chaque relief. Les quatre champs portent la date du 23 septembre 2025. La sensibilité verticale annoncée décrit un paramètre instrumental et ne fournit pas l’incertitude d’un recalage. [Manifeste épinglé](https://huggingface.co/datasets/scrollprize/profilometer/blob/a806bead2f3b9100c20e19de37814fb285cfeefd/manifest.csv) · [Article](https://doi.org/10.1038/s41598-026-58467-1) · [Notice Crossref](https://api.crossref.org/works/10.1038/s41598-026-58467-1)

| Fichier d’origine | Identifiant publié | Dimensions X × Y | Étendue X × Y du manifeste | Localisation CT |
| --- | --- | ---: | --- | --- |
| η | `500P2_230925_H` | 5 369 × 3 617 | 3,693 × 2,488 mm | Inconnue |
| ιτ | `500P2_230925_IT` | 7 105 × 5 352 | 4,887 × 3,681 mm | Inconnue |
| ν | `500P2_230925_N` | 5 365 × 3 622 | 3,690 × 2,491 mm | Inconnue |
| ν2 | `500P2_230925_N2` | 4 499 × 3 628 | 3,094 × 2,495 mm | Recherche pilote |

Les quatre cas ont la même provenance de fragment, les mêmes types de données et aucun repère CT explicite dans les manifestes. ν2 a la plus petite emprise publiée et la plus légère des quatre livraisons complètes. Ce choix limite le transfert et rend le test de recouvrement moins restrictif. Les trois autres cas restent au stade documentaire. Les six métadonnées demandées, dont la fiche du jeu, occupent environ 23 ko. Pour ν2, les quatre fichiers d’origine totalisent 239 690 000 octets, soit environ 240 Mo. Taille et SHA-256 correspondent aux quatre pointeurs LFS. [Rapport et empreintes](../../validation/phase9-optical.json)

## Contrôle sur les fichiers originaux

- Les axes X et Y lus dans `ν2.txt` donnent respectivement **0,6879362463** et **0,6879362469 µm/pixel** par régression sur l’indice du centre de pixel. L’écart maximal à cette grille est inférieur à 0,00018 µm. Les étendues centre à centre sont **3 094,3372 × 2 495,1448 µm**. Avec 0,34 µm, elles seraient 1 529,32 × 1 233,18 µm. L’écart de position en fin de champ atteint donc environ 1,565 mm en X et 1,262 mm en Y. Une différence de pas de cette taille ne peut pas être absorbée dans le budget d’erreur d’un recalage fin. [Mesures](../../validation/phase9-optical.json)
- Relief brut, TIFF de hauteur, photographie et annotation ont la même grille de 3 628 × 4 499. Le relief brut comporte **97,47 %** de valeurs finies. Une régression affine niveau TIFF contre hauteur brute donne un RMS équivalent de **0,0042 µm** aux mêmes indices sur le sous-échantillon. Un décalage d’un pixel donne **15,7 à 16,2 µm**. Cela confirme l’indexation commune du relief brut et du TIFF normalisé, qui ne conserve pas directement les unités Z. [Mesures](../../validation/phase9-optical.json)
- Le TIFF de photographie signé par LFS déclare `IEEEFP` avec trois canaux de 8 bits, une combinaison que tifffile et Pillow ne décodent pas normalement. Le script vérifie les tailles, l’ordre et la contiguïté des bandes RGB non comprimées puis lit les octets uint8. Le fichier source reste intact. La photographie et le relief montrent des structures compatibles dans leur repère commun publié. La corrélation des amplitudes de gradient est faible et négative autour de zéro (−0,081 sans décalage et −0,094 à −0,088 pour les offsets de contrôle à quatre pixels). Elle ne fournit pas une mesure indépendante de l’erreur brightfield–relief. La résolution d’impression inscrite dans le PNG est sans valeur métrologique ici. [Code et résidus](../../validation/phase9_optical.py)

Le fichier numérique confirme la convention de la version publiée. Pour décider de l’échelle physique, il manque la calibration de l’objectif et de la platine, une image de mire avec la chaîne d’export, ou deux repères observables à une distance indépendante connue. Les aperçus de napari et des figures utilisent un pixel sur quatre, avec le pas d’aperçu indiqué. Ils servent à l’inspection, tandis que l’évaluation utiliserait les données natives.
