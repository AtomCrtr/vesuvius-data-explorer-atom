# T6 — Performance S3 : lecture Zarr directe, cache local de chunks, contraste hors fond

- **Origine :** [investigation I1](../investigations/I1-ecosysteme-donnees.md) (chunks non compressés de
  2 Mio, navigation lente), T5.1 (mesure d'alignement d'environ 40 s), décision du PO du
  18 novembre 2026.
- **Statut :** validée par le PO le 18 novembre 2026 ; implémentée par l'orchestrateur
  ([validation](../validation/T6-performance.md) : objectifs atteints).
- **Périmètre réduit**, comme décidé : rendre l'outil sensiblement plus rapide, sans chercher à égaler
  `vesuvius-gui`.

## Faits mesurés

Mesures de l'orchestrateur du 18 novembre 2026 depuis l'environnement cloud (4 cœurs). Volume
PHerc0800 `20250521135224` (8,64 µm, chunks de 128³ non compressés : 2 Mio chacun). Scripts dans
le dossier de travail de l'orchestrateur ; ils seront versés dans la validation.

**1. S3 répond lentement par chunk, mais bien en parallèle.**

| Lecture | Durée |
|---|---|
| 1 chunk (2 Mio) | 0,27 s |
| 8 chunks, un appel Zarr | 0,54 s |
| 27 chunks, concurrence Zarr 10 (défaut) | 1,34 s |
| 27 chunks, concurrence Zarr 64 | 0,66 s |

**2. Dask est le goulot d'étranglement.** Nos tableaux passent par `dask.array.from_zarr` : chaque
chunk devient une tâche Dask lue de façon synchrone, avec au plus 4 lectures en parallèle (une par
cœur).

| Opération | Dask (actuel) | Zarr direct, concurrence 64 |
|---|---|---|
| Mesure d'alignement, 22 patchs (40 Mi-voxels) | 25,7 s | **4,6 s** |
| Vue 2D de 1024 × 1024 au niveau 0 (64 chunks) | 5,2 s | **1,9 s** |

**3. Un cache local de chunks rend les relectures quasi instantanées.** Une coupe 2D lit des chunks
de 128 coupes d'épaisseur : les 127 coupes suivantes réutilisent les mêmes chunks.

| Opération (Zarr direct et cache) | Durée |
|---|---|
| Vue 2D, premier affichage | 1,62 s |
| Coupe suivante | **0,13 s** |
| 10 coupes suivantes | 0,47 s au total |
| Mesure d'alignement, première fois | 6,6 s |
| Même mesure relancée | **0,8 s** |
| Même mesure, **nouveau processus** (cache sur disque) | **0,9 s** |

- Le cache testé est `zarr.experimental.cache_store.CacheStore`, avec un `LocalStore` comme
  stockage. Il est présent dans zarr 3.1.6, la version installée par la CI en Python 3.11, et dans
  zarr 3.4.2.
- Taille sur disque : 151 Mio pour la mesure d'alignement ci-dessus.
- **Le cache de fsspec (`filecache::`) est incompatible** avec les lectures asynchrones de Zarr 3 :
  il provoque des erreurs de boucle d'événements dès que les lectures sont concurrentes. Il est
  écarté.

**4. Le contraste initial est écrasé par le fond masqué.** La coupe d'estimation contient 73 à 76 %
de fond à 0 :

| Volume | Contraste actuel | Hors fond |
|---|---|---|
| PHerc0800 `20250521135224` | (0, 121) | **(12, 128)** |
| PHerc0332 `20251211183505` | (0, 122) | **(31, 132)** |

## Périmètre

### 1. Lecture Zarr directe

- Nouvelle fonction du cœur `open_levels(path, *, cache=True) -> (arrays, levels)`, qui renvoie les
  **tableaux Zarr** des niveaux, et non des graphes Dask.
- Elle sert au widget d'ouverture et au lecteur npe2 (calques napari), ainsi qu'à la mesure
  d'alignement (napari et CLI).
- `open_multiscale`, qui renvoie des tableaux Dask, reste disponible et inchangée pour l'API Python.
- Concurrence des lectures Zarr : **64**, appliquée à l'ouverture d'un volume distant. Le réglage est
  global au processus (configuration Zarr) ; il est documenté et réglable par la variable
  `VESUVIUS_ZARR_CONCURRENCY`.
- À vérifier dans les tests : napari affiche un calque multi-échelles de tableaux Zarr, en 2D et en
  3D, avec le chargement asynchrone ; aucune lecture n'a lieu sur le thread graphique (test T2
  existant).

### 2. Cache local de chunks (`core/cache.py`)

- Volumes **distants seulement** (S3, HTTPS) ; un volume local n'est jamais copié.
- Emplacement : `$XDG_CACHE_HOME/vesuvius-data-explorer/chunks/<empreinte de l'URI>/`, par
  défaut sous `~/.cache/`. Un dossier par volume ; l'URI est notée dans un fichier `source.txt`.
- Construit sur `CacheStore` de Zarr (lectures complètes de clés sur disque, lectures partielles en
  mémoire). Si `CacheStore` est absent (version de Zarr trop ancienne), le cache est désactivé
  avec un avertissement en français, sans erreur.
- **Limite de taille : 10 Gio** par défaut pour l'ensemble des volumes (variable
  `VESUVIUS_CACHE_MAX_GB`). À l'ouverture, les fichiers les plus anciens (par date d'accès, à défaut
  de modification) sont supprimés jusqu'à repasser sous la limite, car la comptabilité LRU de
  `CacheStore` ne survit pas au processus. Pendant la session, `CacheStore` applique la même limite.
- **Expiration : 30 jours.** Un volume republié sous la même URI est relu au plus tard après ce délai.
- Désactivation par `VESUVIUS_CACHE=0`. Bouton **Vider le cache** dans le widget d'ouverture, avec
  la taille actuelle du cache.
- Écritures concurrentes (deux sessions napari) : à tester ; en cas d'entrée illisible, elle est
  supprimée et relue depuis la source.

### 3. Contraste initial hors fond

- `estimate_contrast` ignore les voxels à la valeur de fond (0, la même règle que le QC, réglable
  par le fichier de seuils) quand ils représentent au moins 5 % de la coupe et qu'il reste au moins
  1 % de voxels hors fond. Sinon, le calcul est inchangé.
- La règle est documentée dans le README : le fond masqué reste noir et la matière gagne en contraste.

### Hors périmètre

- Préchargement du niveau grossier pour la vue 3D (le cache le rend inutile après le premier
  affichage).
- Lecture décimée des grandes surfaces tifxyz : une requête par ligne, environ 50 s pour les plus
  grandes (T5) ; regroupement des requêtes à évaluer séparément.
- Conversion ou recompression des volumes.

## Critères d'acceptation

1. **Tests sans réseau :**
   - `open_levels` renvoie des tableaux Zarr ;
   - le cache est rempli à la première lecture, puis utilisé, y compris par un second store sur le
     même dossier ;
   - la limite de taille est appliquée à l'ouverture (fichiers anciens supprimés) ;
   - le cache est désactivé par la variable d'environnement, et en repli sans `CacheStore` ;
   - un volume local n'est pas mis en cache ;
   - le contraste hors fond s'applique sur une coupe masquée et pas sur une coupe sans fond.
2. **Tests napari :**
   - calque de tableaux Zarr ;
   - aucune lecture sur le thread graphique ;
   - bouton **Vider le cache**.
3. **Mesures de validation** sur données réelles, avant et après (napari scripté et mesure
   d'alignement) :
   - vue 2D, coupe suivante, 10 coupes suivantes ;
   - mesure d'alignement, première fois et relancée ;
   - contraste initial sur 3 volumes masqués.
   L'objectif est d'**au moins diviser par 3** la mesure d'alignement à froid, et de passer **sous
   0,5 s pour une coupe suivante** en cache.
4. CI verte, Ruff propre, README et feuille de route à jour.

## Points à valider par le PO

1. **Cache local activé par défaut**, 10 Gio au plus, expiration 30 jours, bouton pour le vider.
2. **Lecture Zarr directe** à la place de Dask dans napari et pour la mesure d'alignement.
3. **Concurrence de 64 lectures**, réglage global au processus.
4. **Contraste initial hors fond.**
5. Utiliser `CacheStore`, une API **expérimentale** de Zarr, derrière notre module, avec repli sans
   cache si elle disparaît ou change.
