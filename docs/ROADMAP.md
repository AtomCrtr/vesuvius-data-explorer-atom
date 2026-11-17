# Feuille de route

Objectif : un outil d'**exploration** et de **contrôle qualité** des données CT du Vesuvius
Challenge, basé sur napari ([ADR 0001](adr/0001-napari-interface-principale.md)).

## Rôles et méthode

- **Product Owner** : objectifs scientifiques, arbitrages, validation des fonctionnalités.
- **Orchestrateur** : architecture, découpage, spécifications (`docs/tasks/`), revue de code.
- **Développeur** : implémentation, tests, documentation, une branche par tâche.

Cycle : spécification dans `docs/tasks/` → branche dédiée → pull request → revue → corrections →
fusion après validation.

## Décisions du Product Owner

- **Interface :** napari, application de bureau ([ADR 0001](adr/0001-napari-interface-principale.md)).
- **Fond masqué :** la valeur 0 des volumes `*-masked.zarr` est du fond, exclue des contrôles
  d'intensité (réglable par TOML). Validé sur PHerc0332 ([T3](validation/T3-donnees-reelles.md)).
- **Seuils QC :** provisoires, à réviser sur davantage de volumes réels. `surface.valid` signale à
  tort les segments VC3D sains (bords irréguliers, I1) : à revoir en T5.
- **Accès aux données :** HTTPS accepté pour le seul domaine officiel `data.aws.ash2txt.org` ;
  codec `vc-delta3d` pris en charge en option (extra `[vcdelta3d]`, Python 3.12 ou plus).
- **Positionnement :** pas de concurrence avec `vesuvius-gui` sur la vitesse de navigation ; la valeur
  du projet est le contrôle qualité reproductible dans l'écosystème Python et napari.

## Tâches

| # | Tâche | Statut |
|---|---|---|
| T1 | [Cœur sans interface + accès aux données réelles](tasks/T1-core-donnees-reelles.md) | Fusionnée (PR #3) |
| T1.1 | [Corrections de revue : OME-NGFF 0.5, chemin inexistant](tasks/T1.1-corrections-revue-t1.md) | Fusionnée (PR #5) |
| T2 | [Plugin napari minimal : ouvrir un OME-Zarr réel multi-échelles](tasks/T2-plugin-napari-minimal.md) | Fusionnée (PR #6) |
| T3 | [Moteur QC + CLI `vesuvius-qc` → rapport JSON/HTML](tasks/T3-moteur-qc-cli.md) | Fusionnée (PR #7), avec gestion du fond masqué |
| T4 | [QC dans napari : rapport, navigation vers les anomalies, mesure de la vue](tasks/T4-panneaux-qc-napari.md) | Fusionnée (PR #9) |
| I1 | [Investigation : formats réels, catalogue officiel, surfaces VC3D](investigations/I1-ecosysteme-donnees.md) | Terminée |
| T4.1 | [Accès aux données : HTTPS officiel (Scroll 1), codec `vc-delta3d` optionnel](tasks/T4.1-acces-donnees.md) | Fusionnée (PR #11) |
| T4.2 | [Sélecteur de volume par le catalogue officiel, taille de voxel en µm](tasks/T4.2-catalogue-volumes.md) | En revue |
| T5 | Surfaces VC3D (TIFXYZ LZW, `meta.json`, points à −1, ordre [x, y, z]) superposées au volume, avec leurs indicateurs | À re-spécifier d'après I1 |
| T6 | Performance S3, périmètre réduit : cache local, préchargement, contraste hors fond | À spécifier |

L'app Streamlit (`app.py`) est gelée et sera retirée lorsque T4 et T5 couvriront ses fonctions
(statistiques de coupe : T4 ; métriques de surface : T5).
