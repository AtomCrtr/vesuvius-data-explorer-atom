# Feuille de route

Objectif : un outil d'**exploration** et de **contrôle qualité** des données CT du Vesuvius
Challenge, basé sur napari ([ADR 0001](adr/0001-napari-interface-principale.md)).

## Rôles et méthode

- **Product Owner** : objectifs scientifiques, arbitrages, validation des fonctionnalités.
- **Orchestrateur** : architecture, découpage, spécifications (`docs/tasks/`), revue de code.
- **Développeur** : implémentation, tests, documentation, une branche par tâche.

Cycle : spécification dans `docs/tasks/` → branche dédiée → pull request → revue → corrections →
fusion après validation.

## Tâches

| # | Tâche | Statut |
|---|---|---|
| T1 | [Cœur sans interface + accès aux données réelles](tasks/T1-core-donnees-reelles.md) | À faire |
| T2 | [Plugin napari minimal : ouvrir un OME-Zarr réel multi-échelles](tasks/T2-plugin-napari-minimal.md) | Spécifiée (après T1) |
| T3 | [Moteur QC + CLI `vesuvius-qc` → rapport JSON/HTML](tasks/T3-moteur-qc-cli.md) | Spécifiée (après T1, parallèle à T2) |
| T4 | Panneaux QC dans napari : métriques de la vue, anomalies affichées sur l'image | À spécifier |
| T5 | Superposition des surfaces TIFXYZ sur le volume, avec leurs indicateurs | À spécifier |

L'app Streamlit (`app.py`) est gelée et sera retirée lorsque T2 et T4 couvriront ses fonctions.
