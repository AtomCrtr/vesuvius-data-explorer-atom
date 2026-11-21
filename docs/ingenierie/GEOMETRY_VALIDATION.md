# Géométrie des pyramides et des surfaces

## Convention déterminée à partir des voxels publiés

Les voxels des niveaux successifs fournissent un repère indépendant
de T10, de napari et de NGFF. Deux régions par acquisition ont été
prélevées à L0 → L1, L1 → L2 et L2 → L3. Pour chacune, comparer la
boîte brute 16³ et la boîte publiée 8³ au même indice dyadique.
Chaque hypothèse choisit sur chaque axe la position paire, impaire
ou la moyenne. Le contrôle compare arrondi inférieur, au pair et
supérieur. Le masque conserve tous les voxels présents dans le niveau
fin ou grossier. [Script](../validation/phase4_geometry.py) · [Mesures Windows](../validation/phase4-geometry-windows.json)

| Acquisition | Boîtes | Voxels contrôlés | Hypothèse reproduisant exactement les niveaux |
| --- | ---: | ---: | --- |
| PHercParis4 `20260310170716`, copie v2 | 6 | 3 062 | Moyenne 2×2×2, arrondi au pair |
| PHercParis4 `20260310170716`, copie v3 shardée | 6 | 3 062 | Moyenne 2×2×2, arrondi au pair |
| PHercParis4 `20230205180739`, copie masquée HTTPS | 6 | 3 061 | Moyenne 2×2×2, arrondi au pair |
| PHerc0800 `20250521135224`, S3 | 6 | 3 072 | Moyenne 2×2×2, arrondi au pair |

Sur ces boîtes intérieures, un voxel d’indice `j` à L1
représente le bloc fin de centres `2j` et `2j+1` sur chaque axe.
Son centre est donc `2j+0,5` sur le repère L0. À L3, il est
`8j+3,5`. Dans un repère dont 0 désigne le **centre** du premier
voxel L0, la formule est `q = (p + 0,5) / 2^L − 0,5`. Dans un
repère dont 0 désigne le **coin** du premier voxel, la même
transformation divise la coordonnée par `2^L`.

L’échelle NGFF seule donne `p / 2^L` pour un indice de centre p.
Le terme de centre manquant vaut `(1 − 1/2^L)/2`, soit **0,4375
voxel de niveau** à L3. NGFF déclare les pas 1, 2, 4 et 8 dans les
assets contrôlés. Les métadonnées publiées de ces niveaux ont
une translation nulle. Les moyennes mesurées établissent la
position des supports d’intensité à l’intérieur du volume.
[Spécification NGFF 0.5](https://ngff.openmicroscopy.org/0.5/#coordinateTransformations-md)

## Provenance et correction

Le prototype T5.1, commit `5e49b0e`, a introduit la formule des
centres avec un facteur déduit du rapport des formes. T10, commit
`01d72da`, l’a réutilisée dans les profils par tuile et la projection
aplatie. Le rapport des formes assimile l’arrondi des dimensions à
un changement d’échelle. Par exemple, PHercParis4
`20260310170716` a 4 071 plans Z à L0 et 509 à L3, pour un pas
observé de 8 plutôt que 4 071/509.

Pour les sources et L0–L3 vérifiés, les profils, cartes et rendus
utilisent désormais le pas dyadique et le centre du support des
voxels. L’activation exige l’URI, les identifiants de niveau,
les formes et les échelles attendues, ainsi qu’une translation
nulle. Le parseur compose les transformations déclarées dans
l’ordre, du niveau vers le groupe, pour contrôler cette condition.
Les autres pyramides, niveaux supérieurs et transformations
inconnues gardent la convention historique, que la sortie
`carte.json` identifie avec le facteur et l’origine utilisés.

Cette correction concerne les trajectoires d’échantillonnage CT
des outils du projet. L’affichage multiscalaire interne de napari
reste piloté par napari. La pose d’une surface entre acquisitions,
les bords incomplets d’un niveau et les axes ou translations
d’autres jeux de données demandent leurs propres repères.

## Surfaces réelles et interpolation

Le TIFXYZ publie trois plans physiques X, Y et Z. Le lecteur les
empile en ZYX et conserve la correspondance entre la ligne V,
la colonne U et le point CT source L0. À L0, le contrôle de la
phase 3 contre les TIFF 16 bits a identifié le meilleur décalage
axial égal à zéro. La phase 4 reprend deux fenêtres de 3×3
sommets du segment `20231005123336`, déjà rattachées à leurs
acquisitions respectives par leurs meshes publiés. Chaque
référence 5×5 interpole indépendamment en U puis en V, applique
la formule du centre de boîte mesurée et interroge SciPy en
trilinéaire sur un bloc CT borné. L’écart maximal du rendu
`float32` par rapport à cette référence est inférieur à
0,000004 unité CT.

| Mesh cible à L3 | UV origine | Écart Z historique / vérifié | Écart maximal des intensités |
| --- | --- | ---: | ---: |
| PHercParis4 `20260310170716`, révision t2 | 294, 276 | 0,0942 voxel | 3,22 unités CT |
| PHercParis4 `20230205180739`, 7,91 µm | 267, 746 | 0,4486 voxel | 16,57 unités CT |

L’interpolation est continue sur ces points. Les indices de
lecture sont arrondis seulement pour déterminer la boîte, avec
un halo d’interpolation. La parité avec SciPy valide
l’échantillonnage de ces surfaces telles qu’elles sont publiées.
La position de la feuille, la face, et la vérité d’encre demandent
des références indépendantes. L’évaluation scientifique est
bloquée pour toute paire de cartes dont la révision, la face ou
le repère de rendu ne sont pas établis.
[Format TIFXYZ](https://github.com/ScrollPrize/open-data#tifxyz-mesh-tifxyz) · [Contrôle TIFF de la phase 3](ZARR_V3_UINT16_VALIDATION.md)

```powershell
$env:XDG_CACHE_HOME = Join-Path $PWD 'data/phase4-cache'
.venv/Scripts/python.exe docs/validation/phase4_geometry.py data/phase4-geometry data/phase4-geometry-windows.json
```

Le même protocole, avec `--v3` dans l’environnement Python 3.12
et le codec optionnel, vérifie directement la copie shardée et
sa projection TIFXYZ. [Trace v3](../validation/phase4-geometry-v3-windows.json)
