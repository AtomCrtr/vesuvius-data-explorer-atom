# Documentation de Vesuvius Data Explorer

## Utiliser et développer l’explorateur

| Besoin | Ressource |
| --- | --- |
| Installer le plugin, ouvrir un volume ou comprendre une alerte | [Guide illustré](guide.md) · [Référence des commandes et de l’API Python](reference.md) |
| Comparer des cartes dans le même repère de surface | [Panneau de comparaison](COMPARAISON_PREDICTIONS.md) · [Rapports d’exemple](examples/README.md) |
| Comprendre l’architecture et les performances | [Vue d’ensemble de l’explorateur](VESUVIUS_EXPLORER.md) · [Moteur Rust](ingenierie/RUST_ARCHITECTURE.md) · [Benchmarks](RUST_BENCHMARKS.md) · [Profil S3 et Dask](S3_DASK_PROFILING.md) |
| Retrouver les spécifications et les décisions | [Feuille de route](ROADMAP.md) · [Tâches techniques](tasks/) · [Décisions d’architecture](adr/) |
| Préparer une distribution | [Publication sur PyPI et napari hub](publication.md) |

## Suivre les expériences

| Sujet | Par où commencer |
| --- | --- |
| Géométrie des niveaux de résolution et des surfaces | [Validation géométrique](ingenierie/GEOMETRY_VALIDATION.md) · [Carte d’alignement en anglais](en/alignment-map.md) |
| Données d’encre et provenance des prédictions | [Jeu d’évaluation](recherche/encre/INK_EVALUATION_DATASET.md) · [Audit de provenance](recherche/encre/INK_PROVENANCE_AUDIT.md) |
| Phases 4 à 8 | [Géométrie et réactivité](ingenierie/RUST_PHASE4.md) · [Consensus](recherche/phase-05/VESUVIUS_PHASE5.md) · [Désaccord](recherche/phase-06/VESUVIUS_PHASE6.md) · [Ordre des couches](recherche/phase-07/VESUVIUS_PHASE7.md) · [Robustesse spatiale](recherche/phase-08/VESUVIUS_PHASE8.md) |
| Phases 9 et 10 | [Recalage CT et optique](recherche/phase-09/VESUVIUS_PHASE9.md) · [Recherche de références indépendantes](recherche/phase-10/VESUVIUS_PHASE10.md) |
| Phases 11 à 13 | [Frag4 et référence infrarouge](VESUVIUS_PHASE11.md) · [Première évaluation d’encre](PHASE12_INK_EVALUATION.md) · [Généralisation sur trois fragments](PHASE13_INK_GENERALIZATION.md) |
| Expériences à venir | [Feuille de route scientifique](ROADMAP_SCIENTIFIC_NEXT_STEPS.md) |

Les scripts de reproduction, protocoles gelés, métriques et captures se trouvent dans [validation/](validation/). Les chemins commençant par `data/` désignent des fichiers produits localement lors des expériences. Les documents cités par empreinte dans le [manifeste de phase 11](validation/phase11-manifest.json) gardent leur chemin d’archive.

## Travailler sur le code

| Composant | Emplacement |
| --- | --- |
| Lecture des volumes, surfaces et géométrie | [Noyau Python](../src/vesuvius_data_explorer/core/) |
| Contrôles qualité et génération des rapports | [Moteur QC](../src/vesuvius_data_explorer/qc/) · [Commandes disponibles](../src/vesuvius_data_explorer/cli.py) |
| Interface napari | [Panneaux et lecteur](../src/vesuvius_data_explorer/napari/) · [Tests de l’interface](../tests/gui/) |
| Interpolation native des voxels | [Extension Rust](../rust/) · [Tests de parité avec Python](../tests/test_rust_sampler.py) |
