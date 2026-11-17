# I1 — Investigation : formats réels, catalogue officiel, surfaces VC3D

- **Date :** 17 novembre 2026
- **Demandée par :** Product Owner, avant de spécifier T5 et T6
- **Menée par :** Orchestrateur
- **Questions :** (1) notre outil lit-il tous les volumes publiés ? (2) existe-t-il un catalogue
  officiel exploitable ? (3) les vraies surfaces VC3D sont-elles lisibles et alignées sur un volume ?

## Résumé

| Question | Réponse |
|---|---|
| Volumes du bucket ouvert | **66 / 66 lisibles**, sans avertissement |
| Volumes publiés ailleurs (HTTPS) | **8, dont Scroll 1** : lisibles techniquement, mais **refusés par notre outil** |
| Copies au codec `vc-delta3d` | **8** (toutes PHercParis4, en double d'une version standard) : **illisibles** sans paquet supplémentaire |
| Catalogue officiel | **Oui** : `metadata.json` (« Vesuvius Atlas »), avec schéma JSON |
| Surfaces VC3D (TIFXYZ) | **Refusées par notre lecteur** (TIFF compressés LZW) ; lisibles avec Pillow |

## 1. Le catalogue officiel « Vesuvius Atlas »

`s3://vesuvius-challenge-open-data/metadata.json` (37 Mo une fois décompressé, servi compressé en
gzip) et son schéma `metadata.schema.json` décrivent tout le bucket :

- **45 échantillons**, **74 volumes**, **324 segments** ;
- pour chaque volume : taille de voxel (`pixel_size_um`), énergie, distance détecteur, forme, type
  de données, transformations vers les autres volumes du même échantillon ;
- pour chaque artefact : son type, son chemin et sa **racine d'accès** (`access_roots`) ;
- des artefacts dérivés : prédictions de surface (44), grilles de normales (41), données lasagna (32),
  détection d'encre, etc. ;
- conventions documentées : points en **[x, y, z]** en voxels du niveau 0, tableaux en **[z, y, x]**,
  niveau N d'une pyramide = sous-échantillonnage 2^N.

**Conséquence :** un sélecteur de volume dans napari peut s'appuyer sur ce fichier, au lieu de
demander à l'utilisateur de copier une URI. Il donne aussi la **taille physique du voxel**, absente
des métadonnées OME (toutes les échelles OME du niveau 0 valent 1).

Bibliothèque Python officielle `vesuvius` (dans `ScrollPrize/villa`, version 0.2.4 sur PyPI) : **non
évaluée en exécution**. Le catalogue `metadata.json` suffit pour nos besoins de catalogue.

## 2. Recensement des volumes

Script : [`I1_census.py`](I1_census.py) ; résultats détaillés : [`I1-volumes-census.json`](I1-volumes-census.json).
Chaque volume `ome-zarr` du catalogue a été ouvert avec notre cœur (`open_volume_store`,
`list_levels`), et une ROI de 64 × 64 a été lue au niveau le plus grossier sur un volume sur quatre.

**Bucket ouvert `s3://vesuvius-challenge-open-data` : 66 volumes, tous lisibles.**

- tous en **Zarr v2**, **OME-NGFF 0.4**, **6 niveaux**, `uint8`, chunks **128³** ;
- 65 **sans compression**, 1 en blosc/zstd ;
- ouverture médiane 1,0 s (maximum 2,3 s) ; 18 ROI lues sur 18, en 0,7 s au plus ;
- aucun avertissement ; échelles issues des métadonnées pour tous.

Chunks non compressés de 128³ octets = **2 Mio par chunk**, quelle que soit la taille de la ROI. C'est
une cause directe de la lenteur de navigation sur S3 (T6).

**HTTPS `https://data.aws.ash2txt.org` : 8 volumes, refusés par notre outil.** Ce sont des volumes
plus anciens de PHerc0332, PHerc1667 et PHercParis4, dont `20230205180739` (**Scroll 1**). Ils sont
publics (réponse HTTP 200, Zarr v2 non compressé). Un essai direct avec un store fsspec HTTP a
listé les 6 niveaux en 2,6 s et lu une ROI en 0,8 s : seul notre refus volontaire du HTTPS bloque.

**Codec `vc-delta3d` : 8 copies, illisibles en l'état.** Format Zarr v3 shardé (shards 1024³, chunks
64³) avec le codec `vc-delta3d`, métadonnées OME-NGFF 0.5. Toutes concernent PHercParis4 et chacune
existe aussi en version standard. Erreur obtenue : `UnknownCodecError: … 'vc-delta3d' is not
available`. Le paquet `vc-delta3d[zarr]` (PyPI, licence MIT, roues précompilées) déclare enregistrer
ce codec auprès de zarr-python automatiquement. **Non vérifié** : l'installation de ce paquet natif a
été refusée par le contrôle des permissions de l'environnement de travail.

## 3. Surfaces VC3D (TIFXYZ)

1 706 segments TIFXYZ sont associés à un volume lisible (186 dans leur volume d'origine, 1 520
transformés vers un autre volume). Étude du plus petit : PHerc0800, segment `20251029010146`, sur le
volume `20250521135224` (8,64 µm).

- Dossier : `x.tif`, `y.tif`, `z.tif` (environ 18 Ko chacun) et `meta.json` (aire, bbox, `scale`,
  source `vc_grow_seg_from_seed`).
- TIFF **float32, compression LZW, tuilés** : `load_surface_patch` les **refuse** (il n'accepte que
  des TIFF projetables en mémoire), et `tifffile` exige le paquet `imagecodecs` pour le LZW.
  **Pillow**, déjà installé avec napari, les décode.
- Grille de **42 × 42** points pour `scale = 0,05` : un point tous les **20 voxels**.
  `surface_metrics` le confirme : pas médian 19,99, p95 20,56.
- Points invalides codés **−1** (et non NaN) : 81,9 % de points valides. Ce sont les bords
  irréguliers du segment, pas des trous ; pourtant notre seuil `surface.valid` (alerte sous 95 %)
  signalerait ce segment sain.
- Coordonnées en [x, y, z] voxels du niveau 0 : x 3 085–3 718, y 5 891–6 623, z 11 598–12 517, dans
  la forme du volume (24 298, 9 867, 9 867) en (z, y, x).
- Contrôle d'alignement au niveau 2 : valeur moyenne **sur la surface 103,0** contre **99,3** pour des
  points aléatoires de la même boîte. L'écart est faible et **ne prouve pas l'alignement** ; une
  vérification visuelle (superposition dans napari) reste nécessaire, c'est l'objet de T5.

## Recommandations

1. **T4.1 — Accès aux données (petite tâche, prioritaire).**
   - Accepter les URL HTTPS de `data.aws.ash2txt.org` (Scroll 1 et 7 autres volumes).
   - Extra optionnel `[vcdelta3d]` = `vc-delta3d[zarr]`, après vérification du paquet par le PO.
   - Message d'erreur explicite en français pour un codec inconnu, avec la commande d'installation.
2. **T4.2 — Sélecteur de volume par catalogue.** Dans le widget d'ouverture : choix
   échantillon → volume à partir de `metadata.json`, avec affichage de la taille de voxel en µm.
3. **T5 — Surfaces VC3D, à re-spécifier avec ces constats :** lecture LZW (Pillow ou `imagecodecs`),
   `meta.json`, points invalides à −1, ordre [x, y, z], association segment → volume par le
   catalogue, superposition sur le volume dans napari. Revoir `surface.valid` : distinguer les
   **bords** du segment des **trous** intérieurs.
4. **T6 — Performance, périmètre réduit.** Les chunks non compressés de 2 Mio sont imposés par la
   source. Pistes réalistes : cache fsspec local, préchargement du niveau grossier, contraste estimé
   hors fond. Ne pas chercher à égaler `vesuvius-gui`, qui utilise ses propres tuiles optimisées.

## Reproduire

```bash
# Catalogue (gzip) : décompresser avant lecture.
python - <<'PY'
import gzip, s3fs
fs = s3fs.S3FileSystem(anon=True)
raw = fs.cat("vesuvius-challenge-open-data/metadata.json")
open("metadata.json", "wb").write(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw)
PY
```

Le script `I1_census.py` prend une liste JSON de volumes `(échantillon, id, format, taille de voxel,
chemin, racines d'accès)` extraite de ce catalogue (artefacts de type `ome-zarr`).
