# Phase 3 · Ouverture distante et validation scientifique

19 novembre 2026. Travail réalisé sur
`feat/rust-explorer-first-kernel`, à partir de `eba4082`.

## Ouverture et navigation

Sur PHerc0800, les métadonnées isolées passent de 4,13 à 1,54 s à
froid et de 3,24 à 0,41 s après réouverture, sur trois répétitions
par version. Les niveaux distants non consolidés sont lus en
parallèle et les mêmes tableaux servent à construire les couches
ou graphes. Le client S3 lit chaque petit objet en une requête
`GET`, en conservant le parallélisme entre blocs.

| Parcours napari | Avant | Après |
| --- | ---: | ---: |
| Première trame utile à froid | 15,16 s | 5,49 s |
| Première trame utile après réouverture | 4,63 s | 1,11 s |
| HTTP à froid, du clic à la première trame | 168 | 77 |
| HTTP à chaud, du clic à la première trame | 86 | 36 |
| Navigation, 12 coupes | 733 ms | 383 ms |

Le trafic utile à froid est de 56 Mio de voxels, plus 4 477
octets de métadonnées. Les données utiles de la réouverture sont
servies par le cache. Les vues et les ROI comparées gardent les
mêmes empreintes. Le p95 de la minuterie Qt reste proche de
17 ms et une pause ponctuelle atteint 444 ms après modification.
Deux essais avec une latence ajoutée et une erreur injectée
valident l’affichage de l’erreur et la réouverture manuelle.
[Protocole, chronologie et mesures brutes](../S3_DASK_PROFILING.md)

## Validation de la lecture scientifique

Les régions testées du Zarr v3 shardé public PHercParis4
`20260310170716` sont identiques à sa copie v2 aux niveaux 0,
1 et 3. Un recadrage de CT EduceLab `uint16` prélevé directement
dans les TIFF de `20230205180739` conserve chaque voxel à travers
un réencodage local en Zarr v3 shardé `vc-delta3d` et les ROI
Dask. Les cinq rendus de surfaces publiées coïncident bit pour
bit entre Python et Rust. Le protocole vérifie aussi le
trilinéaire `uint16` contre SciPy à `1e-8` unité CT.

La comparaison des conventions de coordonnées a identifié un
écart de jusqu’à 0,4375 voxel de niveau à L3 entre la projection
historique et l’échelle NGFF seule. Le calcul historique reste la
référence T10 tant que des repères indépendants n’ont pas établi
la convention géométrique des niveaux publiés. La parité des
deux moteurs couvre les mêmes coordonnées d’entrée.
[Corpus, géométrie et limites](ZARR_V3_UINT16_VALIDATION.md)

## Comparaison des prédictions

Les cartes A et B partagent la grille V/U et le point de vue.
Le panneau règle leur opacité, affiche les décisions opposées
au même seuil et associe les candidats à une boîte UV. La
session JSON restitue les paramètres et vérifie les empreintes
des sources. La capture PNG exporte la boîte à la résolution
des données, avec des coordonnées et la provenance intégrées.
Le statut des candidats exige une validation indépendante.
Les tests du panneau utilisent des cartes de référence
contrôlées. [Manifeste et mode d’emploi](../COMPARAISON_PREDICTIONS.md)

## Architecture

Napari conserve les lectures Zarr asynchrones et Dask sert les
consommateurs de graphes paresseux. Le noyau d’échantillonnage
Rust reste facultatif, avec Python comme moteur de repli.
L’inférence Reader/PyTorch/CUDA demeure dans son pipeline.
Les changements utilisent les dépendances existantes.
La branche reste disponible pour revue avant intégration.

## Tests Windows

Suite complète en Python 3.11 et Qt `windows`, moteur Rust activé.
312 tests réussis, 1 ignoré pour le codec optionnel et 8 tests réseau
hors de la sélection par défaut. La première exécution a rencontré
un refus d’accès Windows lors du remplacement d’un fichier temporaire
Zarr dans un fixture. La suite a réussi intégralement dans un nouveau
dossier de test. En Python 3.12, les tests ciblés donnent 80 réussites
et 1 test ignoré car il vérifie le message en l’absence du codec.
Le test réseau `vc-delta3d` réel a été lancé séparément avec succès.

Exécuter la suite avec le backend Qt natif et un dossier
d’application isolé dans l’espace de travail.

```powershell
$env:LOCALAPPDATA = Join-Path $PWD 'data/phase3-qt-appdata'
$env:QT_QPA_PLATFORM = 'windows'
$env:PYTHONIOENCODING = 'utf-8'
$env:VESUVIUS_RUST_SAMPLER = '1'
.venv/Scripts/python.exe -m pytest -q --basetemp data/phase3-tests
```
