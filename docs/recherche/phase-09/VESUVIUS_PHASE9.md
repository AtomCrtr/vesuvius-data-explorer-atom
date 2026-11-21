# Vesuvius Explorer · Phase 9

Le pilote ν2 a vérifié la grille optique et testé la localisation sur le frontal CT publié. Le champ n’a pas fourni de correspondances physiques vérifiables. Aucune transformation ni métrique d’encre réelle n’est déclarée.

## Résultats

| Question | Résultat |
| --- | --- |
| Peut-on localiser un champ ? | Le fragment est identifié. La recherche sur le frontal publié donne plusieurs localisations pour ν2, y compris à échelle et orientation différentes. Aucun appariement n’est retenu. [Recherche CT–optique](PHASE9_CT_OPTICAL_REGISTRATION.md) |
| Peut-on mesurer une erreur de recalage ? | Aucun repère matériel apparié. Les résidus, l’erreur en µm et la zone de validité restent indisponibles sur le pilote. Les tests synthétiques valident le calcul et les critères de rejet. [Incertitude](PHASE9_GEOMETRIC_UNCERTAINTY.md) |
| Quelle face ? | Le champ optique observe une surface exposée portant de l’écriture. Sa face anatomique et sa correspondance au sens de profondeur CT restent indéterminées. Le frontal Atlas et `wrap01_0919` sont espacés d’au moins 4,42 mm entre les nœuds sondés, sur deux révisions frontales. [Repères et face](PHASE9_CT_OPTICAL_REGISTRATION.md#statuts-et-données-nécessaires) |
| Indépendance d’A ? | Inconnue pour le poids exact. Le préprint et la fiche d’un modèle apparenté documentent PHerc0500P2 dans leur entraînement. Une séparation à l’échelle du manuscrit doit être attestée pour A. [Indépendance](PHASE9_DATA_INDEPENDENCE.md) |
| Peut-on mesurer la détection d’encre ? | Les contrôles de localisation, d’échelle, de face et de recalage n’autorisent pas de mesure. Les vues présentent les modalités dans leurs repères natifs. [Mesures conditionnelles](PHASE9_INK_VALIDATION.md) |
| Quelle donnée débloque le pilote ? | Une photo de situation localisant `500P2_230925_N2`, idéalement sur le cliché IR Naples M1050 n° 017, accompagnée des points de contrôle ou de la transformation IR→CT, de la révision et de la calibration du profilomètre. [Audit optique](PHASE9_PROFILOMETER_AUDIT.md) |
| R02 et R04 | R02 mérite un contrôle de continuité du faisceau ou de la lamelle. R04 demande de distinguer les fentes, les vides et les contours de couche. Les cubes d’origine et les notes de relecture sont réunis sans scores. [Dossier neutre](PHASE9_HUMAN_REVIEW.md) |

## Préservation

La branche locale `feat/vesuvius-phase9` reprend l’arbre de travail de la phase 8 au commit de base `eba4082134df544dc56b5f9d6622d9fd0161f36c`. L’archive de restauration contient 137 fichiers, dont les traces de phase 8, les deux archives de relecture, le plan, les tenseurs CUDA et les couches de surface. Les CRC et SHA-256 des fichiers ont été vérifiés. Pour restaurer la phase 8 dans une copie au commit de base, vérifier l’empreinte du ZIP et recopier `tree/` selon `restore.json`. Les caches et volumes d’origine restent nécessaires pour reproduire les étapes antérieures.

Archive (`data/phase9/phase8-before-phase9.zip`) · SHA-256 (`data/phase9/phase8-before-phase9.sha256`)

## Reproduction Windows

Depuis la racine du dépôt en PowerShell et dans l’environnement de la phase 8. Le téléchargement se limite à ν2, aux métadonnées optiques et à des pièces géométriques de référence. Le frontal n’a pas été téléchargé comme pile CT. Le code réutilise `data/rust2/catalog.json`, le TIFXYZ historique de `data/phase6/historical.tifxyz` et les sorties de phase 8.

```powershell
$phase9Python = '.venv/Scripts/python.exe'
& $phase9Python docs/validation/phase9_fetch.py data/phase9
& $phase9Python docs/validation/phase9_optical.py data/phase9/optical docs/validation/phase9-optical.json data/phase9/optical-preview.npz
& $phase9Python docs/validation/phase9_localize.py data/phase9 docs/validation/phase9-optical.json docs/validation/phase9-localization.json
& $phase9Python docs/validation/phase9_front_search.py data/phase9 docs/validation/phase9-optical.json docs/validation/phase9-front-search.json
& $phase9Python docs/validation/phase9_bundle.py data/phase9
```

Le paquet napari s’ouvre depuis le panneau de comparaison. Il réutilise les couches et les mécanismes de chargement du visualiseur. Les sources optiques sont conservées sous leurs noms originaux dans `data/phase9/optical`. Les manifestes d’export lient les SHA-256 du CT, du relief, de l’annotation et des scores. Les entrées de phase 8 restent en lecture et aucun poids n’a été entraîné ni téléchargé de nouveau. Python reste le moteur par défaut, avec Rust optionnel et les chemins Dask/S3 préexistants.

Dossier napari portable (`data/phase9/validation-CT-optique-phase9.zip`) · Relecture CT de R02 et R04 (`data/phase9/relecture-neutre-R02-R04-phase9.zip`) · [Empreintes](../../validation/phase9-exports.json)

## Tests

Les 355 tests Windows natifs ont réussi, dont huit nouveaux contrôles visant la géométrie, le masque, le risque de fuite, les métriques conditionnelles, l’intégrité de l’export et le chargement napari. Un test est ignoré dans cet environnement Python 3.11, où `vc_delta3d` est absent. Le groupe ciblé avec Rust activé a validé 80 tests. Les huit tests réseau ont réussi dans l’environnement Python 3.12 dédié. Les journaux conservent les avertissements de dépendances Qt/napari et Pydantic.

Windows natif (`data/phase9/windows-tests.log`) · Rust optionnel (`data/phase9/windows-rust-tests.log`) · Réseau (`data/phase9/windows-network-tests.log`)
