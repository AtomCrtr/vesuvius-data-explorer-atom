# T1 — Restructuration du cœur et accès aux données réelles

- **Assigné à :** Développeur (GPT-6)
- **Revue :** Orchestrateur (Opus)
- **Référence :** [ADR 0001](../adr/0001-napari-interface-principale.md)
- **Branche :** `feat/t1-core` (à partir de `main`)
- **Dépend de :** rien · **Débloque :** T2 (plugin napari), T3 (moteur QC + CLI)

## Objectif

Préparer un cœur Python **sans interface graphique** capable d'ouvrir un volume OME-Zarr réel
(local ou S3 public) avec toutes les métadonnées dont napari aura besoin en T2 (niveaux, échelles,
chunks), sans jamais charger un volume entier.

## Périmètre

### 1. Restructuration

- Créer `src/vesuvius_data_explorer/core/` et y déplacer `volume.py`, `surface.py`, `demo.py`.
- Garder les anciens modules (`vesuvius_data_explorer.volume`, etc.) comme **réexports** pour que
  `app.py` et les tests existants continuent de fonctionner sans modification. Un commentaire
  indique qu'ils sont dépréciés.
- `core/` ne doit importer ni `streamlit`, ni `matplotlib`, ni `napari`, ni `qtpy`.

### 2. Dépendances

- `pyproject.toml` : déplacer `streamlit` et `matplotlib` dans un extra `[streamlit]`.
  Dépendances de base : `numpy`, `zarr`, `fsspec`, `s3fs`, `tifffile`, plus `dask[array]`.
- Mettre à jour le README (installation : `pip install -e '.[streamlit]'` pour la démo) et la CI
  (`pip install -e '.[dev]'` doit suffire pour les tests du cœur).

### 3. Métadonnées multi-échelles

Étendre `Level` (rester `frozen`) avec :

| Champ | Type | Source |
|---|---|---|
| `key` | `str` | existant |
| `shape` | `tuple[int, int, int]` | existant |
| `dtype` | `str` | existant |
| `chunks` | `tuple[int, int, int]` | `array.chunks` |
| `scale` | `tuple[float, float, float]` | `coordinateTransformations` de type `scale` (OME-NGFF), sinon `(1.0, 1.0, 1.0)` |

- `list_levels` renvoie les niveaux **du plus fin au plus grossier** (ordre attendu par napari).
- Ajouter `volume_summary(levels) -> dict` sérialisable en JSON : nombre de niveaux, et pour chaque
  niveau forme, dtype, chunks, scale et taille non compressée estimée en octets.

### 4. Accès paresseux pour napari

- `open_multiscale(path: str) -> tuple[list[dask.array.Array], list[Level]]` : un tableau dask par
  niveau (via `dask.array.from_zarr` ou équivalent), **aucune donnée lue** à l'appel.
- `read_slice` reste la seule fonction qui matérialise des données, avec sa limite 512 × 512.

### 5. Gestion des erreurs

Messages explicites (en français, cohérents avec l'existant) pour : chemin vide, URI HTTPS, racine
sans tableau 3D, tableau non 3D, métadonnées `multiscales` mal formées (repli sur les clés
numériques, comme aujourd'hui).

## Hors périmètre

Plugin napari (T2), moteur QC et CLI (T3), toute modification fonctionnelle de `app.py`.

## Critères d'acceptation

1. `pytest -q` passe **sans réseau** ; la CI est verte.
2. `python -c "import vesuvius_data_explorer.core"` fonctionne dans un environnement **sans**
   `streamlit`, `matplotlib` ni `napari` installés. Un test vérifie que ces modules ne sont pas
   importés par `core` (via `sys.modules` dans un sous-processus).
3. Tests sur un **OME-Zarr synthétique écrit dans `tmp_path`** (≥ 3 niveaux, attributs
   `multiscales` avec `scale`) : ordre des niveaux, valeurs de `scale` et `chunks`, contenu de
   `volume_summary`, sérialisation JSON.
4. Test de repli : un groupe Zarr sans attributs `multiscales` mais avec des tableaux `0`, `1`, `2`
   est correctement listé avec `scale = (1.0, 1.0, 1.0)`.
5. Test de paresse : `open_multiscale` sur le Zarr synthétique ne lit aucun chunk (par exemple via
   un store instrumenté ou un compteur d'accès) ; seul `compute()` ou `read_slice` déclenche la
   lecture.
6. Un test **réseau optionnel**, marqué `@pytest.mark.network` et ignoré par défaut, ouvre un vrai
   volume public du bucket `vesuvius-challenge-open-data` et vérifie `list_levels`. L'URI est lue
   dans la variable d'environnement `VESUVIUS_TEST_ZARR` ; le test est ignoré si elle est absente.
   **Ne pas inventer d'URI** : la documenter dans le README à partir de la documentation officielle.
7. Les tests existants (`test_volume.py`, `test_surface.py`, `test_levels.py`) passent sans
   modification de leurs imports.
8. `ruff check .` sans erreur.

## Livrables

- Pull request vers `main` décrivant les changements, la commande de test et le résultat du test
  réseau s'il a été exécuté localement (avec l'URI utilisée).
- README mis à jour : installation, extra `[streamlit]`, lancement du test réseau.

## Points d'attention pour la revue

- Pas de lecture de données dans `list_levels`, `volume_summary` ni `open_multiscale`.
- Compatibilité Zarr v3 (version actuellement épinglée `>=3.0.10,<4`) et Zarr v2 sur S3.
- Respect strict de l'ordre d'axes (z, y, x) pour `scale` et `chunks`.
