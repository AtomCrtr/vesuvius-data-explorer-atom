# Référence technique

Détail du comportement de chaque fonction de Vesuvius Data Explorer. Pour démarrer, lire plutôt le
[README](../README.md) puis le [guide d'utilisation](guide.md).

## Explorer avec napari

```bash
napari -w vesuvius-data-explorer
```

Dans le widget **Vesuvius — Ouvrir un volume**, deux façons de désigner un volume :

- **Catalogue officiel** : cliquer sur **Charger le catalogue officiel**, choisir l'échantillon puis
  le volume ; la fiche affiche la taille de voxel, la forme, le dtype et la licence, et le chemin est
  rempli ;
- **à la main** : saisir le chemin d'un dossier local `/chemin/volume.zarr`, une URI S3 publique ou
  une URL HTTPS officielle.

Puis cliquer sur **Ouvrir**. Un dossier `.zarr` local
peut aussi être glissé dans napari ; ce lecteur npe2 est synchrone, donc les métadonnées et la petite
coupe de contraste peuvent retarder un glisser-déposer : préférer le widget, qui travaille en
arrière-plan. Les URI S3 et HTTPS passent uniquement par le widget.

Exemple réel vérifié dans le [bucket public officiel](https://github.com/ScrollPrize/open-data), pour
PHerc0332 (l'accès et les noms peuvent évoluer) :

```text
s3://vesuvius-challenge-open-data/PHerc0332/volumes/20251211183505-2.399um-0.2m-78keV-masked.zarr
```

**HTTPS.** Huit volumes du catalogue officiel, dont **Scroll 1**, sont publiés hors du bucket S3, sur
`https://data.aws.ash2txt.org`. Ce domaine est le seul accepté en HTTPS (liste
`ALLOWED_HTTPS_HOSTS` de `core/volume.py`) ; les autres URL et le HTTP non chiffré sont refusés.
Exemple vérifié :

```text
https://data.aws.ash2txt.org/samples/PHercParis4/volumes/20230205180739-7.910um-54keV-masked.zarr
```

L'ouverture des métadonnées et l'estimation du contraste s'exécutent dans un thread de travail ; le
bouton reste désactivé pendant cette étape. Le tableau affiche, pour chaque niveau : forme, dtype,
chunks, échelle et taille estimée avant compression. Le calque créé conserve les tableaux **Zarr**
multi-échelles, l'échelle du niveau le plus fin en **(z, y, x)**, l'URI source et ce résumé. Le
contraste initial est explicite : percentiles 1 et 99 d'une seule coupe centrale du niveau le plus
grossier, bornée à 512 × 512 (valeurs non finies ignorées ; bornes du dtype pour une coupe vide ou
constante). Sur un volume masqué, le **fond à 0 est exclu** de ce calcul quand il occupe au moins
5 % de la coupe (et qu'il reste au moins 1 % de matière) : le fond reste noir et le papyrus garde son
contraste. Il reste ajustable dans napari.

**Vitesse et cache local.** Les volumes distants sont lus directement avec Zarr, 64 chunks à la
fois (variable `VESUVIUS_ZARR_CONCURRENCY` ; réglage global au processus), et chaque chunk lu est
gardé sur le disque dans `~/.cache/vesuvius-data-explorer/chunks/` (ou `$XDG_CACHE_HOME`), un
dossier par volume. Une coupe lit des chunks de 128 coupes d'épaisseur : la coupe suivante, un QC
ou une mesure d'alignement relancés viennent du disque. Limite de **10 Gio** pour l'ensemble
(`VESUVIUS_CACHE_MAX_GB`, vérifiée à l'ouverture et en cours de session ; les fichiers les moins
récemment utilisés partent d'abord), expiration
après **30 jours**, bouton **Vider le cache local** dans le widget, désactivation par
`VESUVIUS_CACHE=0`. Les volumes locaux ne sont jamais copiés. Mesures sur PHerc0800 : coupe
suivante de 0,77 s à 0,20 s, mesure d'alignement de 21 s à 4,5 s, puis 0,7 s en cache
([validation T6](validation/T6-performance.md)).

**Catalogue.** Le fichier officiel `s3://vesuvius-challenge-open-data/metadata.json` (environ 9 Mo)
est téléchargé en arrière-plan puis gardé 24 h dans `~/.cache/vesuvius-data-explorer/` (ou
`$XDG_CACHE_HOME`) ; **Actualiser le catalogue** le télécharge à nouveau. Sans réseau, une copie
plus ancienne est utilisée et signalée. Seules les copies accessibles publiquement sont proposées
(S3, ou HTTPS sur `data.aws.ash2txt.org`) ; les copies `vc-delta3d` sont marquées comme telles.
Pour un volume du catalogue, le calque reçoit `pixel_size_um` et la fiche `catalog` dans ses
métadonnées, et le widget **avertit si la forme réelle du niveau 0 diffère de celle du catalogue**
(c'est le cas de Scroll 1, dont la fiche annonce la forme d'avant recadrage, voir la
[validation T4.2](validation/T4.2-catalogue.md)). Le schéma du catalogue précise que les
métadonnées Zarr font foi. Les
coordonnées de napari restent en **voxels du niveau 0**, convention du catalogue et des surfaces
VC3D.

**Chargement asynchrone.** Sans la préférence napari **Render Layers Asynchronously**
(`experimental.async_`), les lectures de la vue (y compris S3) s'exécutent sur le thread graphique et
bloquent l'interface. Cette préférence est globale et enregistrée par napari pour les sessions
suivantes : le plugin **ne la modifie jamais de lui-même**. Si elle est désactivée, le widget ne lit
rien et propose le bouton **Activer le chargement asynchrone (préférence napari)** ; elle se règle
aussi dans les Préférences de napari. Le glisser-déposer respecte la préférence existante.

**Limites connues.** Les chunks téléchargés peuvent dépasser la fenêtre demandée ; le premier rendu
et la navigation déclenchent des lectures supplémentaires selon la vue et le réseau (de quelques
secondes à environ une minute pour la première image sur S3, selon la connexion). En 3D, napari
affiche le niveau le plus grossier. Le cache s'appuie sur `CacheStore`, une API expérimentale de
Zarr : si elle manque, le plugin lit sans cache et l'indique. Qt et un environnement graphique local
sont nécessaires.

## Contrôle qualité dans napari

Le widget **Vesuvius — Contrôle qualité** (menu Plugins) travaille sur un volume ouvert par
**Vesuvius — Ouvrir un volume** :

- **Lancer le QC** : mêmes contrôles que `vesuvius-qc` (niveau, nombre de ROI, graine, budget de
  voxels, fichier de seuils TOML optionnel), exécutés hors du thread de l'interface ;
- **Charger un rapport JSON** produit par `vesuvius-qc volume` : validé par le schéma ; si son URI
  diffère du volume affiché, un avertissement apparaît. Les segments se superposent avec le widget
  **Vesuvius — Surfaces** (ci-dessous) ;
- les résultats s'affichent dans un tableau (échecs en premier) et les anomalies localisées dans un
  calque **QC — anomalies** : un rectangle par ROI fautive (rouge : `fail`, orange : `warn`), visible
  sur sa coupe. Relancer remplace ce calque ;
- sélectionner un contrôle puis une localisation amène la vue sur la coupe et centre le rectangle ;
- **Mesurer la vue** lit la région affichée, au niveau le plus fin qui tient dans 512 × 512, et
  donne le pourcentage de valeurs finies, p1, p99, l'écart-type et le pourcentage de fond (2D
  uniquement).

Les localisations sont converties du niveau `k` vers les coordonnées monde par le rapport des formes
(`qc/locate.py`, sans dépendance graphique), avec ou sans métadonnées d'échelle, comme napari le fait
pour ses niveaux. Au niveau le plus grossier, une ROI couvre une grande partie de la coupe : choisir
un niveau plus fin pour localiser précisément.
Validation sur PHerc0332 : [docs/validation/T4-donnees-reelles.md](validation/T4-donnees-reelles.md).

## Surfaces VC3D dans napari

Le widget **Vesuvius — Surfaces** travaille sur un volume ouvert par **Vesuvius — Ouvrir un volume** :

- **Lister les segments du catalogue** (volume choisi dans le catalogue officiel) : segments publiés
  **dans le repère de ce volume** (copies `tifxyz-transformed`), avec leur couverture. Les copies
  remplacées, issues d'un recalage plus ancien, sont masquées. Un dossier local ou une URI de segment
  peut aussi être saisi ;
- **Superposer** lit le segment hors du thread de l'interface, dans un budget par grille (64 Mio par
  défaut ; au-delà, lecture d'une ligne et d'une colonne sur N, par requêtes partielles, pour les
  fichiers non compressés) ;
- le calque **Surface — …** montre la **trace du segment sur la coupe affichée** : les points à moins
  d'un demi-pas de grille de la coupe, recalculés à chaque changement de coupe (tous les points en
  vue 3D). Points hors du volume masqués, 200 000 points au plus. Le calque **Trous — …** marque en
  rouge le centre des trous intérieurs ;
- **Aller à la surface** amène la vue sur la coupe centrale du segment et le cadre ;
- la fiche donne la taille de la grille, les octets lus et les indicateurs (`vesuvius-qc surface`) ;
- **Mesurer l'alignement** (T5.1) lit l'intensité du volume le long des normales du segment, sur
  36 patchs de 6 × 6 points (réglable), de −200 à +200 µm (±24 voxels si la taille de voxel est
  inconnue), au niveau dont le voxel mesure au plus 10 µm. Le graphique montre le profil moyen ; le
  pic de brillance le plus proche de 0 est la feuille suivie. Les patchs mesurés apparaissent en
  jaune. Sur deux échantillons indépendants de 21 segments réels, la mesure retrouve 86 % puis 83 %
  des décalages imposés de ±25 µm ([validation](validation/T5.1-alignement.md)).
  **Alerte** (T5.3) si la surface est à plus de **30 µm** de sa feuille **et** que la mesure est
  fiable (proéminence ≥ 1,0, taille de voxel connue) ; sinon le résultat est affiché sans note
  (environ deux segments sur trois). Un profil plat ou un maximum au bord de la fenêtre donne
  « alignement indéterminé » ; un saut d'une feuille entière n'est jamais détectable. Compter
  quelques secondes depuis S3, moins d'une seconde en cache.

Points et image partagent le même repère : voxels **(z, y, x)** du niveau 0 et même échelle de
calque. Validation sur PHerc0800 et 30 segments réels :
[docs/validation/T5-surfaces.md](validation/T5-surfaces.md).

## Contrôle qualité en ligne de commande

Le cœur, le moteur QC et la CLI fonctionnent sans extra graphique :

```bash
vesuvius-qc volume /chemin/volume.zarr --samples 16 --seed 0 -o rapport.json --html rapport.html
vesuvius-qc volume s3://bucket/volume.zarr --level 3 --max-voxels 65536
vesuvius-qc surface s3://vesuvius-challenge-open-data/…/segment.tifxyz --max-bytes 67108864 -o surface.json
vesuvius-qc surface s3://…/segment.tifxyz --volume s3://…/volume.zarr --pixel-size-um 8.64
```

Le chemin S3 ci-dessus est un **gabarit**, pas une source de données : utiliser une URI complète et
vérifiée. Chemins locaux, S3 anonyme et HTTPS officiel (`data.aws.ash2txt.org`) sont pris en
charge ; les autres URL sont refusées. Le niveau par
défaut est le plus grossier. Les échantillons sont des fenêtres carrées de coupe `z`, de côté
`min(256, y, x)`, tirées avec `numpy.random.default_rng(seed)` ; axes et localisations sont en
`(z, y, x)`. Le rapport contient les seuils effectifs et toutes les fenêtres signalées. Les anomalies
de métadonnées concernent un niveau entier et pointent sa première fenêtre. Les localisations de
surface désignent une fenêtre de grille `(ligne, colonne)` du fichier complet ; celles des trous
portent aussi leur centre `center` en voxels `(z, y, x)` du volume visé.

**Codes de sortie** : **0** si aucun `fail` ni `error` (avertissements autorisés), **1** si un contrôle
échoue ou lève une exception, **2** si l'entrée ou les arguments sont invalides. Sans `-o`, seul le
JSON est écrit sur la sortie standard ; les messages de budget vont sur la sortie d'erreur. Une
exception dans un contrôle est isolée : les autres contrôles continuent.

**Budget de lecture.** `--max-voxels` impose un plafond strict de **voxels effectivement matérialisés
dans les ROI** (16 777 216 par défaut). Le moteur réduit le nombre de fenêtres sans changer leur
taille ; si aucune ne tient, les contrôles d'échantillons sont `skipped` et les métadonnées restent
évaluées. Une surface a son propre budget, `--max-bytes`, en octets lus **par grille** (64 Mio par
défaut) : au-delà, un fichier non compressé est lu une ligne et une colonne sur N (le plus petit N
qui tient), un fichier compressé est refusé. `voxels_read` compte alors les coordonnées lues
(`3 × lignes × colonnes`). Les options `--window` et `--max-voxels` d'avant T5 sont ignorées pour
une surface, avec un avertissement.

Ce plafond ne borne **pas les octets téléchargés ou décodés** : Zarr lit des chunks, voire des shards,
bien plus grands que la ROI. `budget.chunks_touched` compte les clés de chunks uniques réellement
demandées au store Zarr (lectures synchrones, asynchrones et par plages) ; ce n'est ni un nombre de
requêtes HTTP, ni un volume transféré. Pour un tableau shardé, ce champ vaut `null` et
`store_objects_touched` compte les shards demandés. Les contrôles de métadonnées ne lisent aucun
chunk.

**Volumes masqués.** Les volumes `*-masked.zarr` mettent à une valeur unique (0) tout ce qui est hors
du rouleau. Ces voxels de **fond** sont exclus de `volume.saturation`, `volume.empty` et
`volume.low_contrast` : sinon le fond serait compté comme saturé (0 est le minimum d'un dtype non
signé). Une ROI entièrement dans le fond est ignorée et signalée dans le message ; si toutes le sont,
ces contrôles sont `skipped`. Le contrôle informatif `volume.background` (toujours `pass`) donne la
part de fond échantillonnée. Sur PHerc0332, l'ancienne « saturation » de 17,59 % était exactement
la part de fond ([détails](validation/T3-donnees-reelles.md)).

`volume.levels.scale_consistency` est `skipped` quand les échelles sont le repli unitaire faute de
métadonnées OME exploitables.

**Seuils.** Ils sont **provisoires**, à réviser sur davantage de volumes réels, et centralisés dans
`qc/thresholds.py`. Un fichier TOML peut en surcharger une partie :

```toml
["volume.saturation"]
warn = 1.0
fail = 5.0

["volume.background"]
value = 0      # valeur du fond (toute valeur finie)
enabled = 1    # 0 pour désactiver l'exclusion du fond

["surface.holes"]
warn = 1.0
fail = 5.0
```

```bash
vesuvius-qc volume /chemin/volume.zarr --config seuils.toml -o rapport.json
```

Les noms inconnus, valeurs non finies, booléens, pourcentages hors bornes et seuils inversés sont
refusés. Les comparaisons `warn`/`fail` sont strictes. Saturation et faible contraste sont `skipped`
pour les dtypes flottants, qui n'ont pas de plage d'intensité définie. Les mesures non définies
(par exemple les normales d'une grille entièrement manquante) valent `null` avec le statut
`skipped`, jamais NaN ou Infinity dans le JSON.

**Format.** Il est décrit par [`report.schema.json`](../src/vesuvius_data_explorer/qc/report.schema.json).
Chaque rapport est validé à sa création par un validateur structurel (bibliothèque standard) du
sous-ensemble du schéma utilisé, puis sérialisé avec `allow_nan=False` ; les tests utilisent aussi
`jsonschema` comme validateur indépendant. Le HTML est autonome et échappe URI, messages et
localisations. Les [exemples synthétiques](examples/README.md) sont reproductibles.

## Contrôle qualité en lot

`vesuvius-qc lot <identifiant du volume> -o <dossier>` applique `vesuvius-qc surface` (avec le volume,
donc bornes et alignement compris) à tous les segments actuels que le catalogue publie pour ce
volume. Le volume est ouvert une fois et partagé ; `--workers` segments sont traités en parallèle
(4 par défaut). Une erreur sur un segment est notée dans sa ligne sans arrêter le lot. Sorties :
`synthese.json`, `synthese.csv`, `synthese.html` et `rapports/<segment>.json`. Options :
`--max-segments`, `--sans-alignement`, `--max-bytes`, `--config`, `--catalogue` (fichier
`metadata.json` local). Code de sortie 1 si un segment est en `fail` ou `error`. API Python :
`vesuvius_data_explorer.qc.batch.run_batch`, `to_csv`, `to_html`
([validation T7](validation/T7-qc-en-lot.md)).

## Carte d'alignement (T10)

`vesuvius-qc carte SEGMENT -o DOSSIER [--volume URI] [--pixel-size-um µm] [--catalogue [FICHIER]]
[--recaler] [--cible µm] [--deplacement-max µm] [--derive-max µm] [--tuile N] [--max-bytes N]
[--sans-rendu]`.

- **Mesure** (`core/alignment_map.py`). Grille découpée en tuiles de `--tuile` × `--tuile` points
  (8 par défaut) ; une tuile est mesurée si elle a au moins 16 points valides dans le volume. Profil
  moyen le long des normales, comme T5.1 (portée ±200 µm, niveau le plus grossier dont le voxel
  est ≤ 10 µm). **Pic** : maximum local le plus proche de 0, plus clair que la médiane du profil,
  raffiné par une parabole. **Fiabilité** : hauteur du pic divisée par l'erreur type du profil
  moyen à cet endroit ; **fiable** si ≥ 3 (provisoire). **Incertitude** : écart type de la position
  du pic propagé par la méthode delta, borné à 3 pas.
- **Référence** : moyenne circulaire (ou médiane) des décalages, pondérée par la fiabilité ; la
  **dérive** est le décalage moins la référence.
- **Espacement des feuilles** : premier maximum de l'autocorrélation moyenne des profils, s'il
  dépasse 0,2 fois la valeur centrale. Sinon, pas d'analyse de phase (cas de toutes les données
  réelles essayées). Avec un espacement : dérive repliée, déroulement guidé par la fiabilité, indice
  de feuille relatif, résidus sur les boucles 2 × 2 et bords de repliement.
- **Zones** (`zones.json`) : `saut_de_feuille` (gravité 3), `derive` (fiable et au-delà de
  `--derive-max`, gravité 2), `sans_feuille` (mesurée mais pas fiable, gravité 1) ; composantes
  4-connexes, triées par gravité puis taille. Lignes et colonnes dans la grille des fichiers
  tifxyz ; centre en voxels du niveau 0 (z, y, x).
- **Recalage** (`--recaler`). Tuiles libres : fiables, hors sauts de feuille, dérive ≤
  `--deplacement-max`. Moindres carrés `(W + λL) u = W t` sur ces seules tuiles (`W` : inverse de
  la variance, `L` : laplacien entre tuiles libres voisines, λ = 0,5) ; les autres tuiles restent à
  0. Interpolation bilinéaire normalisée vers chaque point, déplacement le long de la normale.
  Chaque point d'une tuile exclue garde sa position et chaque point d'une tuile recalée reçoit
  tout son déplacement : le maillage forme une marche à la frontière, au plus égale au plafond.
  Écrit `recale/` (`x/y/z.tif` float32, −1 hors surface, `meta.json` avec la provenance) ; refuse
  d'écrire sur un segment existant et de recaler une grille décimée.
- **Lecture** : seuls les blocs Zarr traversés sont lus, chacun décompressé une fois par carte
  (cache en mémoire de 1 Gio), tuiles en parallèle (8 tâches).
- **Rendu aplati** (`core/flatten.py`) : grille interpolée à environ un pixel par voxel du niveau
  lu, sur au plus 1 024 pixels de côté, centrée sur la tuile la plus fiable.

## Utiliser le cœur en Python

```python
import json
import os

from vesuvius_data_explorer.core.volume import open_multiscale, read_slice, volume_summary

# Chemin Zarr local ou URI S3 publique exacte issue du catalogue officiel.
arrays, levels = open_multiscale(os.environ["VESUVIUS_TEST_ZARR"])
print(json.dumps(volume_summary(levels), indent=2))
roi = read_slice(arrays[-1], axis="z", index=0, start_a=0, start_b=0, width=64)
```

`open_levels(uri)` renvoie les tableaux **Zarr** des niveaux, lus en parallèle et, pour un volume
distant, à travers le cache local : c'est la voie rapide, utilisée par napari et la mesure
d'alignement. `open_multiscale` renvoie des tableaux Dask et des enregistrements `Level` immuables, du niveau le
plus fin au plus grossier. Ouvrir, lister les niveaux et résumer ne lisent que les métadonnées, aucun
chunk de voxels. `read_slice` ne calcule que la fenêtre 2D demandée, au plus 512 × 512. Appeler
`.compute()` sur un niveau entier le charge entièrement : découper d'abord.

Formes, chunks et échelles sont en **(z, y, x)**. Les métadonnées **OME-NGFF 0.4** (`multiscales` à
la racine) et **0.5** (`ome.multiscales`) sont prises en charge ; l'espace `ome` est prioritaire, et
s'il est invalide, un avertissement est émis avec repli sur les tableaux du groupe. `scale` combine
les `coordinateTransformations` de chaque niveau et de la pyramide ; ses unités sont celles de la
source. Un ordre d'axes explicitement différent est refusé ; sans axes déclarés, l'ordre ZYX est
supposé. Sans métadonnées multi-échelles, les tableaux du groupe (y compris `0`, `1`, `2`) sont
utilisés avec l'échelle `(1, 1, 1)` et un avertissement : ces échelles ne sont pas des mesures
physiques (`Level.scale_from_metadata` vaut alors `False`). Seule la première pyramide est utilisée.

`volume_summary` renvoie `level_count` et une liste `levels` (`key`, `shape`, `dtype`, `chunks`,
`scale`, `estimated_bytes` = nombre de voxels × taille de l'élément, avant compression). Les anciens
imports `vesuvius_data_explorer.volume`, `.surface` et `.demo` restent disponibles mais sont
dépréciés : importer depuis `.core`.

## Grilles de surface TIFXYZ

Un segment VC3D est un dossier de trois grilles de coordonnées et d'un fichier de métadonnées :

```
segment.tifxyz/
  x.tif  y.tif  z.tif   # float32, coordonnées [x, y, z] en voxels du niveau 0 du volume visé
  meta.json             # bbox, scale (0,05 : un point tous les 20 voxels), format, uuid
```

`core.tifxyz.load_tifxyz` les lit (dossier local, S3 anonyme, HTTPS officiel) et renvoie les points
en **(z, y, x)**, avec NaN pour les points invalides **(−1, −1, −1)** ; les autres valeurs négatives
sont des points valides hors du volume. La plupart des fichiers publiés ne sont pas compressés ; les
autres (LZW avec prédicteur flottant) sont décodés par Pillow quand `imagecodecs` est absent. Des
grilles locales `x.npy`, `y.npy`, `z.npy` sont aussi acceptées.

Indicateurs (`core.tifxyz.tifxyz_metrics`, contrôles `surface.*`) :

| Contrôle | Mesure | Notation |
|---|---|---|
| `surface.valid` | points valides | **informatif** : les bords irréguliers d'un segment sain le font baisser |
| `surface.holes` | points manquants **non reliés au bord** de la grille | warn > 1 %, fail > 5 % |
| `surface.bounds` | points valides hors du volume | informatif ; warn si l'écart avec la couverture du catalogue dépasse 2 points |
| `surface.stretch` | pas p95 / pas médian | warn > 2, fail > 4 |
| `surface.normal_flips` | cellules **voisines** aux normales opposées (replis) | warn > 0,5 %, fail > 2 % |
| `surface.alignment` | décalage de la feuille la plus proche le long des normales (`--volume`) | warn > 30 µm, **seulement si la mesure est fiable** (proéminence ≥ 1,0) et la taille de voxel connue ; sinon non noté |

Les replis sont détectés **localement** : une feuille enroulée a des normales dans toutes les
directions, ce qui faisait signaler environ la moitié de chaque segment réel par l'ancienne
comparaison à une normale moyenne. Cela reste une heuristique, pas une preuve de topologie. Les
seuils sont provisoires, calibrés sur 30 segments réels.

## Trouver un volume réel

1. Dans napari, utiliser le **sélecteur de catalogue** du widget d'ouverture ; sinon, consulter le
   [navigateur de données officiel](https://scrollprize.org/data_browser) ou la
   [documentation du bucket S3](https://github.com/ScrollPrize/open-data).
2. Choisir un **échantillon réel** et copier le chemin S3 complet d'un volume `.zarr` existant : le
   projet ne code volontairement **aucune** URL d'échantillon supposée.
3. Commencer par le niveau le plus **grossier**, puis affiner.

Le catalogue officiel `s3://vesuvius-challenge-open-data/metadata.json` recense échantillons,
volumes et segments. En Python :

```python
from vesuvius_data_explorer.core.catalog import load_catalog

catalog = load_catalog()  # cache local de 24 h
for volume in catalog.volumes_of("PHerc0332"):
    print(volume.label, volume.uri)
```

Voir l'[investigation I1](investigations/I1-ecosysteme-donnees.md)
pour son contenu et l'état de lecture des 74 volumes publiés.

L'accès S3 public est anonyme (`anon=True`). Une petite ROI peut nécessiter le téléchargement de
chunks compressés entiers. Aucun volume complet n'est téléchargé.

## Tests

```bash
python -m pip install -e '.[dev]'
pytest -q
ruff check .
```

La suite par défaut utilise des données synthétiques et des stores Zarr locaux temporaires, sans
réseau. Les tests de widgets sont ignorés si napari est absent (`pytest.importorskip`). Un job CI
`napari` séparé installe `.[napari,dev]` et `pytest-qt`, valide le manifeste npe2 et exécute la suite
sous affichage virtuel Xvfb (le backend `offscreen` de PyQt6 ne fournit pas toujours de contexte
OpenGL). Pour le reproduire :

```bash
python -m pip install -e '.[napari,dev]' pytest-qt
npe2 validate vesuvius-data-explorer
QT_QPA_PLATFORM=xcb xvfb-run -a pytest -q
```

Les tests napari utilisent un fichier de préférences temporaire (`NAPARI_CONFIG`), jamais vos
préférences réelles.

**Tests réseau.** Le marqueur `network` est exclu par défaut, y compris de la CI des pull
requests : un incident réseau ou de bucket ne doit pas bloquer une revue. Le workflow **Network**
(`.github/workflows/network.yml`) les exécute chaque lundi et à la demande (onglet Actions, « Run
workflow ») : volumes réels en S3 et HTTPS, codec `vc-delta3d`, catalogue, segments. Le job CI
`vcdelta3d` garde à chaque push le test synthétique du codec (écriture puis relecture).

Pour vérifier en plus un volume de votre choix :

1. Trouver un volume existant dans le [navigateur officiel](https://scrollprize.org/data_browser) et
   la [documentation S3](https://github.com/ScrollPrize/open-data).
2. Copier son URI `s3://` complète dans le bucket public `vesuvius-challenge-open-data`.
3. Lancer :

   ```bash
   read -r -p 'URI S3 Zarr publique exacte : ' VESUVIUS_TEST_ZARR
   export VESUVIUS_TEST_ZARR
   pytest -q -m network -rs -s
   ```

Le test ne lit que `VESUVIUS_TEST_ZARR`, vérifie les métadonnées et affiche l'URI utilisée. Sans
cette variable, il est ignoré ; une URI invalide ou inaccessible le fait échouer, sans jamais être
remplacée par une URI devinée.
