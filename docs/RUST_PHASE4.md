# Phase 4 · Géométrie, réactivité et cartes d’encre

19 novembre 2026. Branche `feat/rust-explorer-first-kernel`.

## Résultats

- **Géométrie.** Vingt-quatre comparaisons adjacentes établissent
  la moyenne 2×2×2 avec arrondi au pair sur les trois acquisitions
  et les deux formats Zarr testés. La transformation d’échantillonnage
  emploie le pas exact et le centre des supports pour les quatre
  URI contrôlées jusqu’à L3. Le diagnostic des données restantes
  garde le calcul historique identifié dans les rapports. Deux
  surfaces publiques et la copie shardée ont un rendu reproduit
  par une interpolation indépendante. [Géométrie](GEOMETRY_VALIDATION.md)
- **Napari.** La construction du modèle `Image` est effectuée
  par le worker avant insertion dans le viewer. La plus longue
  pause mesurée à froid descend de 435 à 207 ms sur trois
  répétitions. La médiane du p95 Qt reste autour de 17 ms.
  L’indicateur de chargement et les contrôles de révision
  protègent l’ouverture et le panneau des résultats dépassés.
  [Mesures et limites](NAPARI_PERFORMANCE_PHASE4.md)
- **Encre.** Deux cartes publiques PHerc0500P2 servent de
  test du panneau, avec les modes différence, consensus et
  désaccord. La pile UV est cohérente localement avec le
  maillage historique. La révision de projection des TIFF
  et la calibration des scores restent à établir. Les
  chiffres mesurent la stabilité entre sorties. Une campagne
  bornée sur RTX 4080 Laptop sépare validation et évaluation.
  [Corpus et protocole](INK_MODEL_COMPARISON.md)

## Portée scientifique

Le nom d’une acquisition et la taille d’un raster ne suffisent
pas pour recaler une nouvelle surface. L’étape préalable à
toute évaluation de l’encre est l’identité de la pile, de la
face, du repère UV et du split d’apprentissage. Pour les données
hors du corpus géométrique, élargir d’abord le contrôle de
voxels et ajouter des repères. Réévaluer les seuils T10 si
les régions proches des seuils changent sur un corpus de
validation. Les candidats restent des hypothèses de lecture.

## Architecture, dépendances et licences

Le chemin scientifique garde Python par défaut. Rust reste
activable avec `VESUVIUS_RUST_SAMPLER=1` et utilisable seulement
quand la roue est installée pour l’interpréteur. Zarr, Dask,
napari, NumPy et SciPy restent les dépendances de production
existantes. L’inférence se configure à part en PyTorch/CUDA.
La phase 4 conserve `pyproject.toml` et le verrou Cargo.

Le dépôt utilise MIT. Les métadonnées des distributions
Windows déclarent MIT pour Zarr, BSD-3-Clause pour Dask et
napari, et MIT-CMU pour Pillow. Le backend PyQt6 installé déclare
GPL-3.0-only. Les licences embarquées des roues NumPy et
SciPy et les conditions de distribution de Qt se vérifient
pour un paquet redistribué. Les scripts gardent les TIFF
Open Data et les captures de travail hors du dépôt.
Les scans et produits Open Data suivent l’attribution et
les conditions CC BY-NC 4.0. Le code et les poids Reader
publiés suivent leur licence propre et les entrées conservent
leurs conditions de source.
[Architecture et roue Rust](RUST_ARCHITECTURE.md) · [Open Data](https://github.com/ScrollPrize/open-data#support-and-citation) · [Reader V3](https://github.com/DomRusso2/reader-v3/blob/main/LICENSE)

## Configuration Windows et WSL2

Sous Windows natif, installer le projet avec `[napari,dev]`
dans un environnement isolé. Pour le codec shardé `vc-delta3d`,
utiliser Python 3.12 avec `[vcdelta3d]`. La roue Rust doit être
construite dans le même environnement. Les scripts de mesure
réutilisent aussi `psutil`. Pour le profil Qt, employer le
backend Windows et isoler les réglages et le dossier de test.

```powershell
$env:LOCALAPPDATA = Join-Path $PWD 'data/phase4-qt-appdata'
$env:QT_QPA_PLATFORM = 'windows'
$env:PYTHONIOENCODING = 'utf-8'
$env:VESUVIUS_RUST_SAMPLER = '0'
.venv/Scripts/python.exe -m pytest -q --basetemp data/phase4-tests
```

La suite Windows avec Qt natif et moteur Python par
défaut donne **317 réussites**, un test ignoré pour le
codec optionnel et huit tests réseau sélectionnables à part.
Les huit tests réseau passent séparément sous Python 3.12,
avec le codec et le volume PHerc0800 configurés. Les tests
ciblés géométrie, Zarr et Rust en Python 3.12 donnent 82
réussites. Le test qui attend un codec absent est alors
ignoré. Les traces réelles restent liées dans les rapports.

Pour l’inférence WSL2, prendre une distribution Linux dédiée,
un environnement Python Linux et les roues Linux du projet.
Vérifier `wsl -l -v` depuis Windows puis `nvidia-smi` dans
la distribution avec le pilote Windows qui expose CUDA.
Choisir la roue PyTorch Linux/CUDA compatible avec le
pipeline épinglé, puis contrôler
`torch.cuda.is_available()` et `torch.cuda.get_device_properties(0)`.
Garder les sources, le cache et l’environnement Python dans
le système de fichiers Linux pour le profil disque. Pour
un test napari Linux sans bureau, utiliser le parcours Xvfb
de la CI. La machine de validation dispose d’une distribution
Docker Desktop arrêtée et les mesures de phase 4 ont été
réalisées sous Windows natif.
[CUDA avec WSL](https://learn.microsoft.com/en-us/windows/wsl/tutorials/gpu-compute) · [Sélecteur PyTorch](https://pytorch.org/get-started/locally/) · [Tests CI](../.github/workflows/tests.yml)

## Revue GitHub

La description à reprendre en Pull Request couvre les changements
des phases 3 et 4 présents dans l’arbre de travail, les mesures
et les conditions qui bloquent les interprétations scientifiques.
[Corps de la Pull Request](PHASE4_PR.md) · [Passation](CLAUDE_HANDOFF.md)
