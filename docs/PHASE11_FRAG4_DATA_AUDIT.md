# Phase 11 · Inventaire des données Frag4 / PHercParis1Fr39

Le paquet public `Frag4/PHercParis1Fr39.volpkg` contient tout ce qu'il faut pour relier le CT natif à la surface aplatie et à l'IR aligné. Seuls les index, les petits fichiers texte et 21 Mio d'images 2D ont été téléchargés, plus la couche centrale du volume de surface (113 Mio) et des lectures par plages HTTP. Aucun volume complet n'a été rapatrié. [Inventaire brut et empreintes](validation/phase11-frag4-inventory.json) · [Script](validation/phase11_inventory.py)

## Contenu vérifié le 20 novembre 2026

| Élément | Constat | Conséquence |
| --- | --- | --- |
| `volumes/20230215185642` | CT 54 keV, 9 231 TIFF uint16 de 5 808 × 1 968, 3,24 µm, 196,5 Gio. `meta.json` : « cropped 5808x1968x9231+996+4584+500 ». | Le volume publié est un recadrage d'une reconstruction plus grande. La PPM du maillage s'exprime **dans ce repère recadré**, sans décalage (contrôle B1). |
| `volumes/20230222173037` | CT 88 keV, 9 209 × 1 969 × 5 957, 201,5 Gio, recadrage différent (+901+4528+511). | Non utilisé. Toute comparaison 54/88 keV exige un recalage propre. |
| `volumes_zarr/54keV_3.24um_.zarr` | OME-Zarr 0.4, Zarr v2, zstd niveau 3, blocs 128³, 6 niveaux, ZYX [9231, 1968, 5808] au niveau 0. Échelles 1…32 **sans unité** ni translation. | Même grille que les TIFF. Le pas de 3,24 µm n'existe que dans `meta.json` du volpkg. L'application ouvre ce Zarr depuis la phase 11 (hôte `dl.ash2txt.org` autorisé). |
| `volumes_standardized/` | Mêmes formes et mêmes codecs que `volumes_zarr/`. | Différence de contenu non vérifiée. |
| `working/54keV_exposed_surface/…_surface_volume/` | 65 couches `00–64` uint16, 6 064 × 9 791, TIFF non compressés en une seule bande, 7,19 Gio. `invert_normals: false`. | Lecture d'un recadrage par plages HTTP sans télécharger la couche. |
| `extras/PHercParis1Fr39_54keV.ppm` | Carte par pixel 6 064 × 9 791, 6 doubles (x, y, z, nx, ny, nz), 2,7 Gio. | **Lien UV → CT natif.** Validé en B1. |
| `extras/…_surface_volume.ppm` | Même en-tête, mais **application identité** : x = colonne, y = ligne, z = 32, normale (0, 0, 1). | Piège : elle relie le volume de surface à lui-même, pas au CT. Ne pas l'utiliser pour une chaîne CT. [Preuve](validation/phase11-geometry-identity-ppm.json) |
| `extras/` | OBJ, cinq PLY d'étapes de maillage, PSD d'alignement (207 Mio), IR aligné 6 064 × 9 791, faux RVB, carte des cellules, carte UV. | Le PSD documente l'alignement manuel ; ses calques n'ont pas été extraits. |
| `reference/` | IR brut 1 000 nm, 2 056 × 3 072 uint8, 72 dpi factice ; deux photos 4 000 × 6 000. | Aucune calibration physique. L'IR brut est tourné de 180° par rapport à l'IR aligné, sans miroir. Le fragment y couvre environ 1 620 lignes pour 9 791 sur la grille CT : **≈ 20 µm par pixel IR natif**, soit un suréchantillonnage d'environ 6 sur la grille de 3,24 µm. |
| `paths/`, `renders/`, `transforms/` | Seulement `.vckeep`. | Aucune transformation enregistrée hors du PSD. |
| Masque, étiquettes | `…_mask.png` 6 064 × 9 791 ; `…_inklabels.png` **non téléchargé**. | Les étiquettes restent fermées tant que l'étape E est bloquée. |
| `s3://vesuvius-challenge-open-data/PHercParis1Fr39/` | Une seule photo. | Le Data Browser annonce CT et surfaces sur S3 ; en pratique, ils ne sont que sur `dl.ash2txt.org`. |

## Licence et redistribution

Les fragments 1 à 6 appartiennent à l'**EduceLab-Scrolls Dataset**. Les conditions du serveur interdisent de redistribuer les données sans accord écrit, et de rendre publiques hors du Discord officiel les transcriptions, interprétations ou images d'étiquettes d'encre. Toute publication doit citer Parsons et al. 2023 (arXiv:2304.02084) et nommer « EduceLab-Scrolls » dans le résumé. [Conditions, SHA-256 `9dc08a92…`](https://dl.ash2txt.org/LICENSE.txt)

En conséquence, le dépôt ne contient **aucune image ni aucun extrait Frag4** : seulement scripts, URL, empreintes, coordonnées et statistiques. Les extraits restent sous `data/phase11/`, ignoré par Git. Aucun texte du fragment n'est transcrit dans cette documentation.

## Fichiers téléchargés

| Fichier local | Source | Octets | SHA-256 |
| --- | --- | ---: | --- |
| `raw/sv_32.tif` | couche 32 du volume de surface | 118 745 433 | `b0d219dc9cf9bac0576cc0cfde6f9ee1a94d73ae8214770e5f4aa48b0359be97` |
| `raw/ir_aligned.png` | `extras/PHercParis1Fr39_54keV_ir.png` | 12 035 921 | `817670615d5dabba500ac874b865e787882d7f15c86c99eec383a4b10b0d36e2` |
| `raw/mask.png` | `PHercParis1Fr39_54keV_mask.png` | 54 426 | `5d437887925ecd6a0f5b943c5b318a6a15c85e9fc97c95d442ada2255b4f51c7` |
| `raw/ir_raw_1000nm.tif` | `reference/PHerc Paris 1 Cornici 2-FRR 39-01392-1000nmS40-FStop 8-Lens=.tif` | 6 326 014 | `181a1343a86990410825e2fae26eb2d8bd7fe3a8e1ebb8a109448b797c7735ae` |
| `raw/photo_ImgA.jpg`, `raw/photo_ImgB.jpg` | `reference/` | 1 922 477 · 1 588 949 | `cccd0833…` · `a2ce1e71…` |

Les patchs PPM, les couches 0–64 des patchs et les recadrages des ROI ont été lus par plages HTTP ; leurs coordonnées sont dans les JSON de résultats.
