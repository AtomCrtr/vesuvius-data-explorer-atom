# T5 — Surfaces VC3D superposées au volume, avec leurs indicateurs

- **Origine :** [investigation I1](../investigations/I1-ecosysteme-donnees.md), recommandation 3, et
  mesures complémentaires sur le catalogue du 16 novembre 2026 (section « Faits » ci-dessous).
- **Statut :** validée par le PO le 17 novembre 2026 ; implémentée par l'orchestrateur.
- **Écarts constatés à l'implémentation** (détails dans la
  [validation](../validation/T5-surfaces.md)) : la trace sur la coupe est calculée par le plugin
  (`out_of_slice_display` ne fonctionne plus dans napari 0.10) ; `surface.normal_flips` compare les
  cellules voisines, car la mesure existante signalait la moitié de chaque segment réel ; seuils
  recalibrés (warn 0,5 %, fail 2 %).
- **Découpage :** **T5** = lecture, association au volume, superposition dans napari, indicateurs
  révisés. **T5.1** (plus tard) = indicateur quantitatif d'alignement surface–volume (profil
  d'intensité le long des normales), exploratoire.

## Objectif

Afficher sur un volume ouvert les segments VC3D publiés pour ce volume, pour **vérifier à l'œil leur
alignement** coupe par coupe, et calculer des indicateurs de qualité qui ne signalent plus à tort les
segments sains.

## Faits établis (catalogue et fichiers réels)

Mesures de l'orchestrateur, le 17 novembre 2026. Elles **corrigent I1** sur la compression.

1. **Quelle copie superposer.** Les artefacts `tifxyz-transformed` portent `parameters.target_volume` :
   leurs points sont dans le repère **voxels du niveau 0** de ce volume. Il y en a **1 642**, et
   **tous** visent un volume ouvrable du catalogue. Les `tifxyz` d'origine (199) peuvent être dans un
   repère sous-échantillonné (`original_volume_downscale` = 4 pour certains) : **hors périmètre**.
2. **Format.**
   - Dossier : `x.tif`, `y.tif`, `z.tif` (float32, 2D, même forme) et `meta.json` (`bbox`, `scale`,
     `format`, `type`, `uuid`), toujours présent dans l'échantillon examiné.
   - Points invalides : **(−1, −1, −1)**. Sur 8 segments, aucun point partiellement à −1 ni non fini.
     D'autres valeurs négatives existent : ce sont des points **hors du volume**, pas des invalides.
   - Compression : la **majorité est non compressée** (24 sur 25 copies transformées tirées au
     hasard ; 10 sur 15 copies d'origine). Le reste est en **LZW tuilé avec prédicteur flottant (3)**.
     `tifffile` exige `imagecodecs` pour le LZW ; Pillow le décode (vérifié en I1).
   - Grille : un point tous les 20 voxels (`scale` = 0,05 pour tous les segments).
3. **Taille de `x.tif` (1 642 copies transformées).** Médiane 0,8 Mio, p90 30 Mio, p99 329 Mio,
   maximum **443 Mio** (soit 1,3 Go pour les trois grilles). 98 copies dépassent 64 Mio. Les grandes
   sont **non compressées, en une seule bande contiguë** : la ligne `i` commence à
   `offset + i × largeur × 4`, donc une lecture décimée par lignes est possible avec des requêtes
   partielles.
4. **Points hors du volume.** Sur 6 segments, la part de points valides hors des bornes du volume vaut
   0 à 64 %, et correspond à **1 − `properties.volume_coverage[volume].overlap_ratio`** du catalogue
   (à 1 % près). Ce sont les scans haute résolution qui ne couvrent qu'une partie du rouleau : c'est
   normal, et le catalogue le documente.

## Périmètre

### 1. Lecture : `core/tifxyz.py`

- `load_tifxyz(source, *, max_bytes=64 * 2**20) -> TifxyzSurface`, pour un dossier local ou une URI
  `s3://` / `https://` (mêmes règles d'accès que `open_volume_store`, dont `ALLOWED_HTTPS_HOSTS`).
- `TifxyzSurface` : `points` en float64 de forme (lignes, colonnes, 3), ordre **(z, y, x)**, NaN pour
  les invalides ; `meta` (contenu de `meta.json`) ; `grid_shape` (forme complète du fichier) ;
  `stride` (décimation appliquée, 1 si aucune) ; `source` ; `bytes_read`.
- Conversion : les fichiers sont en [x, y, z] ; le cœur passe en (z, y, x), comme partout ailleurs.
  Invalide = les trois coordonnées à −1, ou une coordonnée non finie. Les autres négatifs restent des
  points valides.
- Décodage : `tifffile` d'abord ; si le fichier exige `imagecodecs` et qu'il est absent, **Pillow**.
  Pillow devient une dépendance du cœur (il est déjà installé avec napari). Sans aucun décodeur
  possible : erreur française.
- **Budget** : l'en-tête TIFF est lu en premier (requête partielle). Si les trois grilles tiennent
  dans `max_bytes` chacune, lecture complète. Sinon :
  - fichier non compressé en bandes : lecture **d'une ligne sur `stride`** par requêtes partielles,
    puis une colonne sur `stride` en mémoire, avec le plus petit `stride` qui respecte le budget ;
  - fichier compressé trop grand : refus en français, avec sa taille et le budget.
- `meta.json` absent ou illisible : avertissement, lecture des grilles quand même. Formes différentes
  entre x, y et z : erreur française.
- `load_surface_patch` (Streamlit, gelé) reste inchangé.

### 2. Catalogue : segments d'un volume

- `core/catalog.py` : `CatalogSegment(sample_id, segment_id, name, target_volume_id, uri,
  overlap_ratio, transform_revision, superseded)`, construit **uniquement** depuis les artefacts
  `tifxyz-transformed`, avec les mêmes règles d'accès que les volumes.
- `Catalog.segments_for(volume_id)`, trié par identifiant de segment.

### 3. Indicateurs

Fonction pure `tifxyz_metrics(surface, volume_shape=None)` dans le cœur :

- `valid_pct` : part de points valides. **Informatif** désormais : le contrôle `surface.valid` ne
  note plus (statut toujours `pass`, comme `volume.background`), car les bords irréguliers font baisser
  ce taux sur des segments sains (I1 : 81,9 %).
- `hole_pct` (nouveau contrôle **`surface.holes`**) : points invalides **non reliés au bord de la
  grille** (connexité 4), rapportés aux points valides plus ces trous. Seuils provisoires
  `warn` 1 %, `fail` 5 %, à recalibrer à la validation.
- `stretch` et `normal_flip_pct` : calcul existant (`surface_metrics`), sur la grille lue.
- `out_of_bounds_pct` (nouveau contrôle **`surface.bounds`**, si `volume_shape` est connu) : part de
  points valides hors du volume. Informatif ; si `overlap_ratio` est fourni, `warn` lorsque
  `|(100 − out_of_bounds_pct) − 100 × overlap_ratio|` dépasse 2 points (catalogue incohérent avec
  les données).
- Localisations : pour `surface.holes`, les 20 plus grands trous, avec leur boîte en (ligne, colonne)
  et leur centre en voxels (z, y, x) du volume, interpolé depuis les points valides voisins.
- `scipy.ndimage.label` est autorisé pour les composantes connexes : scipy devient une dépendance du
  cœur.
- Rapport : `schema_version` passe à **1.1** (nouveaux contrôles ; sens changé de `surface.valid`).
  Un seuil TOML `surface.valid` existant est accepté mais ignoré, avec un avertissement.

### 4. CLI

`vesuvius-qc surface <dossier ou URI>` utilise `load_tifxyz` et `tifxyz_metrics` ; option
`--max-bytes`. L'option `--window` est retirée de ce sous-commande (avertissement si fournie). Sans
volume associé, `surface.bounds` est `skipped`.

### 5. napari : widget « Vesuvius — Surfaces »

- S'applique au calque d'image sélectionné. Liste des segments du catalogue qui visent son volume
  (métadonnée `catalog.volume_id` posée en T4.2), avec leur couverture. Champ libre pour un dossier ou
  une URI de segment.
- **Superposer** (thread de travail, jamais le thread graphique) :
  - calque **Points** « Surface — `<segment>` », dans le **même repère** que l'image : coordonnées
    (z, y, x) en voxels du niveau 0 et **même `scale`** que le calque d'image ;
  - affichage hors coupe (`out_of_slice_display`) avec une taille égale au pas de la grille (20 voxels
    × `stride`), pour voir la **trace de la surface sur la coupe courante** ;
  - au plus 200 000 points affichés (décimation supplémentaire signalée) ;
  - points hors du volume masqués ;
  - second calque Points, en rouge, pour le centre des trous.
- Fiche affichée : taille de la grille, `stride`, octets lus, puis les indicateurs.
- **Aller à la surface** : coupe au centre de la boîte des points valides dans le volume, caméra
  centrée sur cette boîte.
- Erreurs : messages français ; pas de trace Python.

### Hors périmètre

T5.1 (alignement quantitatif) ; rendu des `layers-zarr` (volumes aplatis) ; maillages `obj` ; calque
Surface 3D ; `tifxyz` d'origine ; écriture ou correction de segments.

## Critères d'acceptation

1. **Tests sans réseau.**
   - Lecture : TIFF non compressé et LZW avec prédicteur 3 (décodé par Pillow quand `imagecodecs` est
     absent) ; ordre (z, y, x) ; −1 → NaN, autres négatifs conservés ; `meta.json` absent ; formes
     différentes.
   - Budget : lecture décimée par requêtes partielles (octets lus ≤ budget, contrôlé), refus d'un
     fichier compressé trop grand.
   - Indicateurs : bords irréguliers sans trou → `surface.holes` pass ; trou intérieur → warn ou
     fail, avec localisation ; `surface.bounds` cohérent ou incohérent avec `overlap_ratio` ;
     `surface.valid` toujours pass ; ancien seuil TOML ignoré avec avertissement ; schéma 1.1 validé.
   - Catalogue : seuls les `tifxyz-transformed` deviennent des segments, rattachés à leur volume.
2. **Tests napari** : superposition hors du thread graphique ; repère identique à l'image (scale
   0,5/1/2 de la pyramide de test) ; plafond de points ; points hors volume masqués ; navigation ;
   erreurs en français.
3. **Tests réseau** : le segment PHerc0800 `20251029010146` transformé vers `20250521135224`
   (non compressé, 49 × 49) et un segment de plus de 64 Mio lu en décimé dans le budget.
4. **Validation documentée** sur données réelles :
   - capture d'une superposition sur une coupe, avec licence des données ;
   - distribution de `hole_pct` sur au moins 20 segments, pour recalibrer les seuils ;
   - comparaison `surface.bounds` / `overlap_ratio` sur ces segments.
5. Suites `tests`, `napari` et `vcdelta3d` vertes ; Ruff propre ; README et feuille de route à jour.

## Points à valider par le PO

1. Superposer **uniquement les copies transformées** (`tifxyz-transformed`), qui sont dans le repère
   du volume affiché.
2. `surface.valid` devient informatif et `surface.holes` le remplace pour la notation.
3. Budget par défaut de **64 Mio par grille**, avec lecture décimée au-delà.
4. Pillow et scipy ajoutés aux dépendances du cœur.
5. Découpage T5 / T5.1.
