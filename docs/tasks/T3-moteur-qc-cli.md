# T3 — Moteur de contrôle qualité et CLI `vesuvius-qc`

- **Assigné à :** Développeur (GPT-6)
- **Revue :** Orchestrateur (Opus)
- **Référence :** [ADR 0001](../adr/0001-napari-interface-principale.md)
- **Branche :** `feat/t3-qc` (à partir de `main`, **après fusion de T1**)
- **Dépend de :** T1 · **Indépendante de :** T2 (peut être développée en parallèle) · **Débloque :** T4

## Objectif

Produire, **sans interface graphique**, un rapport de contrôle qualité reproductible pour un volume
OME-Zarr ou une grille de surface TIFXYZ, en lisant un volume de données **borné et annoncé**.
Le rapport doit pouvoir être relu par napari en T4 : chaque anomalie porte une **localisation**.

## Périmètre

### 1. Modèle de résultats (`src/vesuvius_data_explorer/qc/`)

```python
Status = Literal["pass", "warn", "fail", "error", "skipped"]

@dataclass(frozen=True)
class Location:          # où regarder dans napari
    level: str
    axis: str            # "z" | "y" | "x"
    index: int
    origin: tuple[int, int]
    size: tuple[int, int]

@dataclass(frozen=True)
class CheckResult:
    check_id: str        # ex. "volume.saturation"
    status: Status
    value: float | None
    threshold: dict[str, float]   # ex. {"warn": 1.0, "fail": 5.0}
    message: str                  # en français, lisible par un humain
    locations: tuple[Location, ...] = ()
```

- Chaque contrôle est une fonction pure enregistrée dans un registre (`qc/checks/`).
- Une exception dans un contrôle donne `status="error"` pour ce contrôle, **sans interrompre** les
  autres.
- `qc/` dépend de `core/` uniquement : ni napari, ni Qt, ni streamlit, ni matplotlib.

### 2. Contrôles sur un volume

**Métadonnées** (aucune lecture de données) :

| `check_id` | Vérifie |
|---|---|
| `volume.levels.present` | au moins un niveau 3D |
| `volume.levels.dtype` | même dtype sur tous les niveaux |
| `volume.levels.shape_ratio` | chaque niveau ≈ moitié du précédent sur chaque axe (tolérance ± 1 voxel) |
| `volume.levels.scale_consistency` | rapport des `scale` cohérent avec le rapport des formes (tolérance 5 %) |
| `volume.chunks.size` | taille d'un chunk entre 32 Kio et 64 Mio non compressés |

**Échantillons** (lecture bornée) : `N` ROI 2D tirées de façon **déterministe** (graine fixe) sur
un niveau choisi, via `read_slice`. Pour chaque contrôle, les ROI fautives sont listées dans
`locations`.

| `check_id` | Mesure | `warn` | `fail` |
|---|---|---|---|
| `volume.finite` | % de voxels non finis | > 0 % | > 1 % |
| `volume.saturation` | % de voxels au minimum ou au maximum du dtype (entiers) | > 1 % | > 5 % |
| `volume.empty` | % de ROI entièrement constantes (zones non remplies) | > 10 % | > 50 % |
| `volume.low_contrast` | % de ROI dont l'écart-type < 1 % de la plage du dtype | > 25 % | > 75 % |

### 3. Contrôles sur une surface TIFXYZ

À partir de `load_surface_patch` et `surface_metrics` (fenêtre bornée existante) :

| `check_id` | Mesure | `warn` | `fail` |
|---|---|---|---|
| `surface.valid` | % de points valides | < 95 % | < 80 % |
| `surface.stretch` | `p95_step / median_step` | > 2 | > 4 |
| `surface.normal_flips` | % de normales inversées | > 1 % | > 5 % |

> **Seuils provisoires.** Toutes les valeurs ci-dessus sont des heuristiques de départ, à valider
> par le Product Owner sur des données réelles. Elles doivent être définies **en un seul endroit**
> (`qc/thresholds.py`) et surchargeables par un fichier TOML (`--config`, lu avec `tomllib`).

### 4. Budget de lecture

- `--max-voxels` (défaut : 16 777 216, soit 16 Mi voxels) : plafond **dur** sur les voxels lus.
  Si `N` ROI dépassent le budget, réduire `N` et le signaler dans le rapport.
- Le rapport indique le nombre de voxels réellement lus et le nombre de chunks touchés quand le
  store permet de le mesurer.

### 5. Rapport

**JSON** (format principal), décrit par un **JSON Schema** versionné dans le dépôt
(`src/vesuvius_data_explorer/qc/report.schema.json`) :

```json
{
  "schema_version": "1.0",
  "tool": {"name": "vesuvius-data-explorer", "version": "…"},
  "created_at": "…", "duration_s": 0.0,
  "target": {"kind": "volume", "uri": "…", "level": "…"},
  "parameters": {"samples": 16, "seed": 0, "max_voxels": 16777216, "thresholds": {}},
  "budget": {"voxels_read": 0, "chunks_touched": null},
  "summary": {"pass": 0, "warn": 0, "fail": 0, "error": 0, "skipped": 0},
  "results": []
}
```

**HTML** (optionnel, `--html`) : un fichier unique et autonome, sans dépendance supplémentaire
(bibliothèque standard uniquement). Il contient un résumé coloré par statut et un tableau des
résultats avec leurs localisations. Toute chaîne issue de l'entrée (URI, messages) est échappée
(`html.escape`).

### 6. CLI

Point d'entrée `vesuvius-qc` (`[project.scripts]`), avec `argparse` (pas de dépendance nouvelle) :

```
vesuvius-qc volume  <chemin|s3://…zarr> [--level KEY] [--samples 16] [--seed 0]
                    [--max-voxels N] [--config seuils.toml] [-o rapport.json] [--html rapport.html]
vesuvius-qc surface <dossier> [--window 256] [--config seuils.toml] [-o rapport.json] [--html rapport.html]
```

- Niveau par défaut : le plus grossier (lecture minimale).
- Sans `-o`, le JSON est écrit sur la sortie standard ; les messages de progression vont sur la
  sortie d'erreur.
- **Codes de sortie :** `0` aucun `fail` ni `error` · `1` au moins un `fail` ou `error` ·
  `2` erreur d'utilisation ou d'entrée (chemin invalide, HTTPS, racine sans tableau 3D).

## Hors périmètre

Affichage dans napari (T4), contrôles croisés volume/surface (T5), détection d'encre, exécution
parallèle ou distribuée, traitement de plusieurs volumes en une commande.

## Critères d'acceptation

1. **Volume sain** : un OME-Zarr synthétique propre (≥ 3 niveaux, écrit dans `tmp_path`) donne
   uniquement des `pass`, et le code de sortie est `0`.
2. **Défauts injectés**, un test par défaut, chacun détecté par le bon `check_id` avec une
   `location` qui pointe sur la zone défectueuse :
   bloc de NaN (volume float), bloc saturé, bloc constant, niveau de forme incohérente,
   `scale` incohérente, dtype différent entre niveaux.
3. **Surface** : `demo_surface()` (trou volontaire) déclenche `surface.valid` ; une grille dont on
   inverse une partie déclenche `surface.normal_flips`.
4. **Déterminisme** : deux exécutions avec la même graine produisent des rapports identiques, à
   l'exception de `created_at` et `duration_s`.
5. **Budget** : avec un store instrumenté, le nombre de voxels lus ne dépasse jamais `--max-voxels`,
   et les contrôles de métadonnées ne lisent aucun chunk.
6. **Robustesse** : un contrôle qui lève une exception donne `status="error"` et les autres
   contrôles s'exécutent quand même.
7. **Schéma** : chaque rapport produit dans les tests est validé par `report.schema.json` avec
   `jsonschema` (ajouté à l'extra `dev`).
8. **HTML** : le fichier s'ouvre sans ressource externe, et une URI contenant `<script>` y
   apparaît échappée.
9. **CLI** : les codes de sortie 0, 1 et 2 sont testés (`subprocess` ou appel de `main(argv)`), ainsi
   que la surcharge des seuils par `--config`.
10. **Isolation** : le test d'isolation de T1 couvre aussi `qc/` (aucun import de napari, Qt,
    streamlit ou matplotlib).
11. **Test réseau optionnel** (`@pytest.mark.network`, URI lue dans `VESUVIUS_TEST_ZARR`) :
    `vesuvius-qc volume` sur un vrai volume termine avec un rapport valide. La PR indique
    l'URI, le niveau, la durée et les voxels lus.
12. `ruff check .` sans erreur ; `pytest -q` vert.

## Livrables

- Pull request vers `main`, reprenant chaque critère avec sa preuve.
- Un rapport JSON et un rapport HTML d'exemple, générés sur le volume synthétique, dans
  `docs/examples/`.
- README : section « Contrôle qualité en ligne de commande » (commandes, codes de sortie, budget de
  lecture, fichier de seuils, caractère provisoire des seuils).

## Points d'attention pour la revue

- Les contrôles sont des fonctions pures et testables isolément. Le CLI ne contient aucune logique
  de contrôle.
- Les seuils sont définis à un seul endroit ; aucune valeur en dur dans les contrôles.
- Le budget de lecture est un plafond strict, pas une indication.
- Les `locations` utilisent le même ordre d'axes (z, y, x) et les mêmes clés de niveau que T1, pour
  que T4 puisse naviguer directement vers une anomalie.
