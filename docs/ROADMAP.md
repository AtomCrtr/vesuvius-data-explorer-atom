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
  L'app Streamlit d'origine est retirée depuis T5.
- **Fond masqué :** la valeur 0 des volumes `*-masked.zarr` est du fond, exclue des contrôles
  d'intensité (réglable par TOML). Validé sur PHerc0332 ([T3](validation/T3-donnees-reelles.md)).
- **Seuils QC :** provisoires, à réviser sur davantage de volumes réels. `surface.valid` est
  informatif depuis T5 ; `surface.holes` note les trous intérieurs.
- **Surfaces (T5) :** seules les copies `tifxyz-transformed` sont superposées ; budget de 64 Mio par
  grille, lecture décimée au-delà ; Pillow et scipy dans le cœur. Écarts acceptés : trace sur la
  coupe calculée par le plugin ; `surface.normal_flips` local (warn 0,5 %, fail 2 %).
- **Alignement (T5.1) :** pic de brillance le plus proche ; 36 patchs par défaut, budget de
  80 Mi-voxels (écarts acceptés) ; mesure informative, non notée avant
  calibration ; un saut de feuille entière n'est pas détectable ; portée ±200 µm, voxel ≤ 10 µm.
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
| T4.2 | [Sélecteur de volume par le catalogue officiel, taille de voxel en µm](tasks/T4.2-catalogue-volumes.md) | Fusionnée (PR #12) |
| T5 | [Surfaces VC3D superposées au volume, indicateurs révisés (trous, bornes)](tasks/T5-surfaces-vc3d.md) | Fusionnée (PR #14) |
| R1 | Retrait de l'app Streamlit (`app.py`, extra `[streamlit]`) | Fusionnée (PR #15) |
| T5.1 | [Alignement surface–volume : profil d'intensité le long des normales](tasks/T5.1-alignement-surface-volume.md), exploratoire | Fusionnée (PR #17), 36 patchs, informatif |
| A1 | Corrections de l'audit de GPT-6 : mesure de la vue, rapport sur un autre volume, échelles OME absentes, budget tifxyz, préférence async, tests réseau hebdomadaires ; alignement indéterminé (dans T5.1) | Fusionnée (PR #18) |
| T6 | Performance S3, périmètre réduit : cache local, préchargement, contraste hors fond | À spécifier |
