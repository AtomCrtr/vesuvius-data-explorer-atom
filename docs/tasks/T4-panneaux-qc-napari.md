# T4 — Contrôle qualité dans napari : rapport, navigation vers les anomalies, mesure de la vue

- **Assigné à :** Développeur
- **Revue :** Orchestrateur — **fusion uniquement après validation**
- **Référence :** [ADR 0001](../adr/0001-napari-interface-principale.md)
- **Branche :** `feat/t4-qc-napari` (à partir de `main`)
- **Dépend de :** T2 (plugin), T3 (moteur QC, `Location`) — toutes deux fusionnées
- **Débloque :** T5, retrait de l'app Streamlit (avec T5)

## Objectif

Réunir exploration et contrôle qualité dans napari : lancer ou charger un rapport QC, voir les
anomalies **sur l'image**, y naviguer en un clic, et mesurer la région affichée. Ce qui couvre
aussi la fonction « statistiques de coupe » de l'app Streamlit.

## Périmètre

### 1. Fonctions pures (dans `qc/`, sans napari ni Qt)

Nouveau module `qc/locate.py`, testable sans interface :

- `location_to_world(location, levels, layer_scale) -> WorldBox`
  convertit une `Location` (niveau, axe, index, origine, taille, coordonnées du niveau `k`) en
  coordonnées **monde** du calque napari :
  `index_niveau0 = index_k × forme_0 / forme_k` (par axe), puis `monde = index_niveau0 × layer_scale`.
  Cette règle fonctionne avec ou sans métadonnées d'échelle. `levels` est la liste
  `volume_summary(...)["levels"]` stockée dans `layer.metadata`.
  `WorldBox` contient le plan (axe + coordonnée monde) et les deux coins du rectangle.
- `visible_region(level_shapes, layer_scale, view_box, max_side=512) -> (level_key, axis, index, origin, width)`
  choisit le niveau **le plus fin** dont la région visible tient dans `max_side × max_side`,
  et renvoie les arguments de `read_slice` correspondants (bornés au volume). Si même le niveau
  le plus grossier dépasse, prendre la fenêtre centrale de `max_side` de ce niveau.
- `view_metrics(data, background) -> dict` : `slice_stats` + pourcentage de fond (même règle que
  `volume.background` de T3).

### 2. Widget « Vesuvius — Contrôle qualité » (nouvelle contribution du manifeste)

**Cible :** liste déroulante des calques `Image` ouverts par le plugin (ceux qui ont
`metadata["source"]` et `metadata["volume_summary"]`). Message clair si aucun.

**Obtenir un rapport, deux voies :**
- **Lancer le QC** : paramètres `niveau` (défaut : le plus grossier), `ROI`, `graine`,
  `budget de voxels`, fichier de seuils TOML optionnel. Appelle `run_volume` sur
  `open_volume_store(metadata["source"])` **hors du thread de l'interface**, bouton désactivé
  pendant le calcul.
- **Charger un rapport JSON** produit par `vesuvius-qc` : validé par `validate_report`. Si
  `target.uri` ne correspond pas à `metadata["source"]`, afficher un avertissement mais charger
  quand même (le volume peut avoir été déplacé). Un rapport `surface` est refusé (traité en T5).

**Affichage :**
- résumé par statut (pass / warn / fail / error / skipped), coloré ;
- tableau des contrôles : identifiant, statut, valeur, message ; les lignes `warn`, `fail` et
  `error` en premier ;
- un calque `Shapes` unique **« QC — anomalies »** : un rectangle par localisation, dans son plan
  (napari ne l'affiche que sur la coupe concernée), orange pour `warn`, rouge pour `fail`,
  avec le `check_id` en texte. Relancer ou recharger **remplace** ce calque, sans en ajouter un
  second. Les contrôles de métadonnées, qui concernent un niveau entier, n'ont pas de rectangle.

**Navigation :** sélectionner une ligne puis une de ses localisations (liste sous le tableau)
place la vue sur la bonne coupe (`viewer.dims`), centre la caméra sur le rectangle et règle le
zoom pour qu'il occupe environ la moitié de la vue.

### 3. Mesurer la vue

Bouton **« Mesurer la vue »** : calcule `visible_region` à partir de la caméra et de la coupe
courante (2D uniquement ; en 3D, message expliquant que la mesure est 2D), lit la région
**hors du thread de l'interface** avec `read_slice` (≤ 512 × 512), puis affiche `view_metrics` :
niveau utilisé, taille, % de valeurs finies, p1, p99, écart-type, % de fond.

### 4. Règles reprises de T2

- La préférence `experimental.async_` n'est jamais modifiée silencieusement.
- Aucun calcul dask sur le thread de l'interface ; messages d'erreur en français, sans trace.
- Le widget ne contient pas de logique métier : il appelle `qc/` et `core/`, puis affiche.

## Hors périmètre

Rapports de surface et superposition des surfaces (T5) ; mesures en vue 3D ; édition des seuils
dans l'interface (seul un fichier TOML est accepté) ; performance du chargement S3 (T6) ;
suppression de l'app Streamlit.

## Critères d'acceptation

1. `npe2 validate vesuvius-data-explorer` passe ; `napari -w vesuvius-data-explorer` propose les
   deux widgets.
2. **Tests purs (job sans napari)** pour `location_to_world` : plusieurs niveaux, rapports de
   formes non entiers, échelles de repli unitaires, `layer_scale` non uniforme ; et pour
   `visible_region` : choix du niveau, bornage aux limites du volume, repli sur la fenêtre centrale.
3. **Lancer le QC** sur un volume synthétique comportant un bloc saturé (fixture inspirée de
   `tests/test_qc.py`) : tableau rempli, calque « QC — anomalies » avec le bon nombre de
   rectangles, au bon plan et en coordonnées monde ; calcul hors du thread de l'interface
   (même méthode de test qu'en T2).
4. **Charger un rapport** : un JSON valide produit le même affichage ; un JSON invalide ou un
   rapport `surface` donnent un message en français et aucun calque ; une URI différente donne
   un avertissement et l'affichage.
5. **Navigation** : après sélection d'une localisation, `viewer.dims.point` est sur le plan
   attendu et le centre de la caméra est dans le rectangle.
6. **Mesurer la vue** : au plus 512 × 512 voxels lus (store instrumenté comme en T1/T3), lecture
   hors du thread de l'interface, valeurs égales à `view_metrics` calculé directement sur la même
   région.
7. Relancer le QC deux fois laisse **un seul** calque « QC — anomalies ».
8. Le test d'isolation couvre `qc/locate.py` (aucun import de napari ou de Qt) ; `NAPARI_CONFIG`
   reste isolé dans les tests ; préférence `async_` non modifiée par le widget.
9. **Validation manuelle sur PHerc0332**, décrite dans `docs/validation/T4-donnees-reelles.md` :
   lancer le QC avec `volume.background.enabled = 0` (ce qui produit des anomalies de saturation
   localisées dans le fond masqué), vérifier qu'un clic amène bien la vue dans une zone noire hors
   du rouleau, puis relancer avec la configuration par défaut (aucune anomalie). Capture d'écran
   avec l'attribution de licence, comme en T2.
10. CI verte (jobs `tests` et `napari`), `ruff check .` sans erreur.

## Livrables

- Pull request **en brouillon** vers `main`, chaque critère avec sa preuve.
- README : section « Contrôle qualité dans napari ».

## Points d'attention pour la revue

- Exactitude de la conversion niveau `k` → monde : c'est la base de toute la navigation.
- Un seul calque d'anomalies, remplacé et non empilé.
- Aucune lecture non bornée : le QC respecte le budget de T3, la mesure de vue est plafonnée à 512².
