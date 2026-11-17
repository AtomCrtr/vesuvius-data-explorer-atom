# T2 — Plugin napari minimal : ouvrir un volume OME-Zarr réel

- **Assigné à :** Développeur (GPT-6)
- **Revue :** Orchestrateur (Opus)
- **Référence :** [ADR 0001](../adr/0001-napari-interface-principale.md)
- **Branche :** `feat/t2-napari` (à partir de `main`, **après fusion de T1**)
- **Dépend de :** T1 (`open_multiscale`, `Level.scale`, `volume_summary`) · **Débloque :** T4, T5

## Objectif

Ouvrir dans napari un volume OME-Zarr réel (local ou S3 public) en **multi-échelles paresseux**,
avec une navigation 2D fluide, sans jamais charger le volume entier ni bloquer l'interface.

## Périmètre

### 1. Packaging du plugin

- Créer `src/vesuvius_data_explorer/napari/` avec un manifeste **npe2** (`napari.yaml`) déclaré
  dans `pyproject.toml` (`[project.entry-points."napari.manifest"]`).
- Ajouter un extra `[napari]` : `napari[all]>=0.5`. Les dépendances de base ne changent pas.
- Le plugin dépend de `core/` uniquement ; `core/` n'importe toujours ni napari ni Qt.

### 2. Widget « Ouvrir un volume »

Contribution `widgets` du manifeste, nommée **« Vesuvius — Ouvrir un volume »** :

- un champ texte pour un chemin local ou une URI `s3://…/<volume>.zarr` ;
- un bouton **Ouvrir** ;
- une zone d'information qui affiche, après ouverture, le résumé `volume_summary` sous forme de
  tableau (niveau, forme, dtype, chunks, échelle, taille estimée) ;
- une zone de statut pour les messages d'erreur (texte en français, sans trace Python brute).

L'ouverture (`open_multiscale` et l'estimation du contraste) s'exécute **hors du thread principal**
(`napari.qt.threading.thread_worker` ou équivalent). Le bouton est désactivé pendant le chargement.

### 3. Lecteur (glisser-déposer)

Contribution `readers` pour les **dossiers locaux** se terminant par `.zarr` : même résultat que
le widget. Les URI S3 passent uniquement par le widget.

### 4. Calque image

Pour un volume ouvert, ajouter **un seul** calque `Image` :

- `multiscale=True`, données = liste des tableaux dask de `open_multiscale` (du plus fin au plus
  grossier) ;
- `scale` = `Level.scale` du niveau le plus fin, ordre (z, y, x) ;
- `contrast_limits` **fournis explicitement** (napari ne doit pas les calculer lui-même sur les
  données) ;
- `name` = nom du dossier `.zarr` ;
- métadonnées du calque (`layer.metadata`) : URI source et `volume_summary`.

### 5. Estimation du contraste (dans `core/`)

Ajouter `estimate_contrast(levels_arrays, max_side=512) -> tuple[float, float]` dans `core/` :

- lit **une seule coupe centrale bornée** (≤ `max_side` × `max_side`) du niveau le plus grossier,
  via `read_slice` ;
- renvoie les percentiles 1 et 99 des valeurs finies ;
- repli sur les bornes du dtype si la coupe est vide ou constante.

### 6. Documentation

README : section « Explorer avec napari » (installation `pip install -e '.[napari]'`, lancement
`napari -w vesuvius-data-explorer`, ouverture d'un volume local et S3, limites connues).

## Hors périmètre

Panneaux QC (T4), surfaces TIFXYZ (T5), CLI QC (T3), annotations, rendu 3D spécifique.
En 3D, napari affiche le niveau le plus grossier d'un multi-échelles : c'est accepté et à mentionner
dans les limites connues du README.

## Critères d'acceptation

1. Après `pip install -e '.[napari]'`, `napari -w vesuvius-data-explorer` ouvre le widget sans
   erreur, et `npe2 validate vesuvius-data-explorer` passe.
2. **Test widget** (pytest-qt, fixture `make_napari_viewer`) : ouvrir un OME-Zarr synthétique
   (≥ 3 niveaux, écrit dans `tmp_path`) ajoute un calque `Image` multi-échelles avec le bon nombre
   de niveaux, le bon `scale` et des `contrast_limits` définis.
3. **Test lecteur** : le lecteur accepte un dossier `.zarr` local et refuse un fichier quelconque
   (renvoie `None`).
4. **Test de lecture bornée** : avec un store instrumenté, l'ouverture lit **uniquement** les chunks
   nécessaires à `estimate_contrast` (aucune lecture des niveaux fins).
5. **Tests `estimate_contrast`** (sans napari) : volume normal, volume constant, volume avec NaN.
6. **Erreurs** : chemin vide, chemin inexistant, URI HTTPS, racine sans tableau 3D → message dans la
   zone de statut, aucun calque ajouté, aucune exception non gérée.
7. **CI** : un job séparé `napari` installe `.[napari,dev]` + `pytest-qt` et lance les tests en mode
   headless (`QT_QPA_PLATFORM=offscreen` ou affichage virtuel). Le job existant reste léger et ignore
   les tests napari (`pytest.importorskip("napari")`). Le test d'isolation de `core/` de T1 passe
   toujours.
8. **Validation manuelle sur données réelles**, décrite dans la PR : URI utilisée (issue de la
   documentation officielle, non inventée), capture d'écran du calque affiché, temps jusqu'au
   premier affichage, et constat sur la fluidité du zoom/déplacement en 2D.
9. `ruff check .` sans erreur ; `pytest -q` vert dans les deux jobs.

## Livrables

- Pull request vers `main` reprenant chaque critère avec sa preuve (sortie de tests, capture).
- README mis à jour.

## Points d'attention pour la revue

- Aucun appel bloquant sur le thread de l'interface.
- Aucun calcul napari automatique sur l'ensemble des données (contraste, histogramme).
- Ordre des niveaux et des axes (z, y, x) cohérent avec T1.
- Pas de logique métier dans le widget : il appelle `core/` et affiche le résultat.
