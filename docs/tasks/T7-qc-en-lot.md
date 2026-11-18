# T7 — Contrôle qualité en lot des segments d'un volume

- **Origine :** proposition de l'orchestrateur, retenue par le PO le 18 novembre 2026 (avec le guide
  d'utilisation et la publication).
- **Implémentée par :** orchestrateur ; [validation](../validation/T7-qc-en-lot.md).

## Objectif

Contrôler en une commande **tous les segments publiés pour un volume** du catalogue, et obtenir une
synthèse lisible pour repérer les segments à revoir.

## Périmètre

- `vesuvius-qc lot <identifiant du volume> -o <dossier>` :
  - segments actuels (`tifxyz-transformed` non remplacés) du catalogue officiel pour ce volume ;
  - rapport complet `run_surface` par segment : trous, bornes comparées à la couverture du catalogue,
    étirement, replis, alignement noté (T5.3) ;
  - volume ouvert une seule fois (lecture Zarr et cache local de T6), segments traités en parallèle
    (`--workers`, 4 par défaut) ;
  - une erreur sur un segment est notée dans sa ligne, sans arrêter le lot.
- Options : `--max-segments`, `--sans-alignement`, `--max-bytes`, `--config` (seuils TOML),
  `--catalogue` (fichier `metadata.json` local).
- Sorties dans le dossier : `synthese.json`, `synthese.csv`, `synthese.html` (tableau coloré, les
  messages s'affichent au survol), et `rapports/<segment>.json`.
- Code de sortie : 1 si au moins un segment est en `fail` ou en `error`, sinon 0.
- API Python : `qc.batch.run_batch`, `to_csv`, `to_html`.

## Hors périmètre

Lot depuis napari ; lot sur plusieurs volumes ; segments hors catalogue.
