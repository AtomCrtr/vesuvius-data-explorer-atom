# Fiche de relecture CT · PHerc0500P2 · R02 et R04

Cette fiche accompagne les cubes CT du segment `20250919184428-0500P2-wrap01_0919` et deux extraits natifs L0 de l’acquisition `20250526151718`. Commencer par lire les images et remplir la grille, puis examiner les hypothèses structurales. Consigner les observations du lecteur dans une copie de cette fiche.

## Images et repères

| Région | Bornes V,U du rendu, fin exclue | Structure à suivre |
| --- | --- | --- |
| R02 | V[644,772) U[636,764) | Bande inclinée visible à Z59 et faisceaux plus transversaux en profondeur. |
| R04 | V[644,772) U[764,892) | Contours courbes autour de zones sombres et point clair à Z59, puis bordure surtout en haut à gauche. |

- `ct-ZVU.tif` conserve les 62 coupes du rendu `[28,90)` de phase 9. L’index local 0 désigne la coupe 28. `ct-59.tif` est le plan de départ et `valid-mask.tif` décrit le support. Les coordonnées globales, l’identifiant du volume, le pas 2,215 µm et les empreintes sont dans `ct-provenance.json`.
- `CT-brut-L0-ZYX.tif` fournit pour chaque région un cube natif de 80³ voxels. Le cube est centré près du nœud TIFXYZ valide le plus proche du centre UV, avec des bornes entières Z,Y,X et le centre non arrondi consignés dans `CT-brut-provenance.json`. Le cube contrôle une partie centrale de la fenêtre. Les axes Z,Y,X du tomographe et la profondeur du rendu sont deux repères.

## Questions de lecture

1. **R02**. Repérer l’entrée, la bifurcation ou l’interruption des bandes claires sur les coupes adjacentes. Tester si la structure se poursuit dans une même lamelle, intersecte une autre couche ou correspond à plusieurs faisceaux. Chercher le même type de continuité dans les trois plans natifs.
2. **R04**. Délimiter les contours sombres et lumineux sur les coupes successives. Tester si une bordure suit un vide, une fissure, un pli ou une frontière de couche. Noter si le point clair est isolé ou se prolonge.
3. **Géométrie**. Relever les coupures de contour, changements brusques au voisinage d’un bord, empreintes de grille et zones où la trajectoire du rendu traverse plusieurs feuillets. Distinguer ce qui est visible dans le CT natif de ce qui apparaît à l’échantillonnage du rendu. Signaler les structures qui sortent du cube L0.

| ID | Repère, coordonnées et coupes | Observation directe | Hypothèse structurale | Autre explication ou incertitude | Pièce de validation nécessaire |
| --- | --- | --- | --- | --- | --- |
| R02 | | | | | |
| R04 | | | | | |

La face anatomique locale et la correspondance avec une photographie optique restent indéterminées. L’examen initial porte sur la matière et la géométrie. Conserver ce relevé séparément de toute relecture des scores. Les images sont issues de Vesuvius Challenge Open Data. [Attribution et conditions](https://github.com/ScrollPrize/open-data#support-and-citation)
