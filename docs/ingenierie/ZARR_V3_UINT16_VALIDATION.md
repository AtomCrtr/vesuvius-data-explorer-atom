# Validation scientifique de Zarr v3 et du CT uint16

19 novembre 2026. Essai Windows x64 avec Python 3.12.14, Zarr 3.4.2,
NumPy 2.5.5, `vc-delta3d` 0.3.2 et roue PyO3 Release GNU x64. Les
quotas du script bornent la lecture aux régions décrites ci-dessous.
Le JSON contient les chemins publics, les ETag des TIFF, les empreintes
des pixels et des grilles ainsi que les lectures Zarr par plage.
[Script](../validation/phase3_science.py) · [Mesures brutes](../validation/phase3-science-windows.json)

## CT uint16 d’origine, réencodé en pyramide shardée

Le CT provient des TIFF EduceLab de PHercParis4 `20230205180739`, à
7,91 µm. Les 32 coupes `08501.tif` à `08532.tif` sont lues par plages
HTTP vérifiées. Le script contrôle chaque en-tête, l’ordre des octets et
l’orientation TIFF, puis extrait les lignes et colonnes du même recadrage
ZYX. Les 73 728 voxels de la boîte `[8501, 4573, 3265] + [32, 48, 48]`
vont de 1 949 à 65 535. La pyramide locale NGFF 0.5 encode cette boîte
avec `vc-delta3d fast, quant=1`, puis encode au niveau 1 la même boîte
décimée avec un pas de 2 sur chaque axe. [TIFF EduceLab publiés](https://dl.ash2txt.org/full-scrolls/Scroll1/PHercParis4.volpkg/volumes/20230205180739/)

| Niveau | Forme ZYX | Blocs | Shards | Contrôles |
| --- | --- | --- | --- | --- |
| 0 | 32 × 48 × 48 | 8 × 16 × 16 | 16 × 32 × 32 | Voxels identiques, ROI coronale identique |
| 1 | 16 × 24 × 24 | 4 × 8 × 8 | 8 × 16 × 16 | Voxels identiques, ROI coronale identique |

Les tableaux Zarr gardent le type `uint16`, les dimensions et les
échelles 1 et 2. La ROI Dask traverse des frontières de blocs. À chaque
niveau, huit coordonnées fractionnaires autour d’une frontière
tridimensionnelle sont interpolées sur les voxels originaux par SciPy
(`order=1`, `mode=nearest`) et par les deux moteurs. Les trois sorties
concordent à `1e-8` unité CT en valeur absolue, avec `rtol=0`.

La copie Zarr masquée de la même acquisition sert de contrôle
d’orientation et d’origine. La meilleure corrélation entre
intensités sur les voxels non masqués est de 0,999981, sans décalage
axial, parmi les 257 décalages de −128 à +128 coupes. Le contrôle
compare aussi les inversions et la permutation Y/X. Ce résultat
valide le repère du recadrage à L0.

La cellule UV `[267, 746]` du segment `20231005123336` recalé sur cette
acquisition est translatée de l’origine de la boîte, en ZYX. La projection
échantillonne la cellule aux décalages normaux de −1, 0 et +1 voxel
source. Les rendus Python et Rust coïncident bit pour bit aux deux
niveaux. Ils contiennent respectivement 441 et 121 pixels `float32`.
Le témoin utilise un CT réel avec une pyramide construite pour
l’expérience. [Formats et attribution](https://scrollprize.org/data)

## Zarr v3 shardé publié

PHercParis4 `20260310170716`, 45,532 µm, `uint8`, huit niveaux,
`vc-delta3d fast, quant=1`. À L0 et L1 les blocs sont 64³ et les
shards 1 024³. À L3 les blocs sont 64³ et les shards 256³. Les
lectures de 8³ voxels croisent les frontières de blocs sur trois axes.
La boîte L0, centrée sur la frontière `[3072, 1024, 1024]`, traverse
également huit shards. Les lectures Zarr directes et Dask concordent
exactement avec les valeurs des régions correspondantes de la copie
v2 publiée, type et formes compris.
[Catalogue et attribution](https://github.com/ScrollPrize/open-data#support-and-citation)

| Niveau | Forme ZYX | Frontière de la ROI | Plage CT | Rendu Python / Rust |
| --- | --- | --- | --- | --- |
| 0 | 4071 × 2264 × 2264 | 3072, 1024, 1024 | 0–168 | 7 × 7, écart 0 |
| 1 | 2036 × 1132 × 1132 | 1536, 512, 512 | 0–172 | 5 × 5, écart 0 |
| 3 | 509 × 283 × 283 | 384, 128, 128 | 7–136 | 3 × 3, écart 0 |

La grille publique de cette acquisition est le TIFXYZ
`20231005123336-on-20260310170716-45.532um-t2.tifxyz`. La fenêtre 3 × 3
démarre à UV `[294, 276]`. Le test reprend ses coordonnées ZYX et son
pas, calcule des normales finies et compare le rendu aux mêmes décalages
normaux que pour le CT 16 bits. Le seuil d’acceptation des comparaisons
`float32` est de 0,004 unité CT, soit environ un ULP près du maximum
`uint16`. Les cinq rendus ont le même masque de valeurs manquantes et
les mêmes empreintes Python/Rust. Le script échoue si la roue Rust
est indisponible.

## Coordonnées entre résolutions

La projection historique utilise `(p + 0.5) / facteur_forme - 0.5`, avec
un facteur déduit des dimensions. Sur ce recadrage, l’application de la
seule échelle NGFF publiée donne `p / facteur_NGFF`. L’écart maximum
entre les deux expressions atteint 0,25 voxel de niveau à L1 et 0,4375
à L3. Il combine la convention de centre des voxels et, sur Z, l’arrondi
des formes. La parité des moteurs valide leur calcul sur les mêmes
coordonnées. La convention de rééchantillonnage du producteur et
l’exactitude du recalage sur la feuille demandent des repères
indépendants avant une modification du parcours de mesure T10.
[Format NGFF 0.5](https://ngff.openmicroscopy.org/0.5/)

Le test combine un Zarr v3 shardé publié en 8 bits et du CT originel 16
bits réencodé à l’identique dans un Zarr local. La généralisation à
d’autres pipelines de reconstruction, aux quantifications avec pertes
et à un Zarr distant natif `uint16` reste à mesurer.

## Reproduction

Utiliser Python 3.12 avec les extras `[vcdelta3d,dev]`, `psutil` pour
les scripts de validation et la roue Rust du même interpréteur.

```powershell
python rust/build_release.py
python -m pip install (Get-ChildItem rust/target/wheels -Filter '*cp312*.whl' | Select-Object -First 1 -ExpandProperty FullName)
python docs/validation/phase3_science.py data/phase3-science data/phase3-science-windows.json
```
