# Valider la géométrie CT et réduire les pauses napari

Branche de travail `feat/rust-explorer-first-kernel`. Le lot
inclut les changements de phase 3 présents dans le même arbre
de travail.

## Changements

- S3 résout chaque niveau une seule fois et évite les requêtes
  de taille préalables sur les petits objets.
- Les profils, cartes et rendus utilisent le pas dyadique au
  centre du support mesuré pour les pyramides et niveaux contrôlés.
  Les exports de carte gardent la convention et le facteur.
- Le modèle napari `Image` se construit dans le worker. Qt
  possède l’insertion et le rendu. Le chargement est visible
  et les requêtes périmées sont écartées.
- Le panneau compare des scores sur une même grille UV. Il
  affiche différences signées, consensus et désaccords, conserve
  les scores, la calibration déclarée et les annotations candidates.

## Vérifications à relire

317 tests Windows natifs réussis avec le moteur Python par
défaut. En Python 3.12, 82 tests ciblés et 8 tests réseau
réussis, avec vérification de la copie Zarr v3 shardée.

- [Comparaisons de voxels et oracles de surfaces](../../ingenierie/GEOMETRY_VALIDATION.md)
- [Traces Windows des pauses Qt](../../ingenierie/NAPARI_PERFORMANCE_PHASE4.md)
- [Paire de cartes Atlas et protocole RTX](../encre/INK_MODEL_COMPARISON.md)
- [Architecture, licences et commandes de test](../../ingenierie/RUST_PHASE4.md)

## Limitations scientifiques

Le contrôle de centres couvre quatre URI, trois acquisitions
et les niveaux 0 à 3. La validation CT indépendante des TIFF
d’encre demande encore la révision du rendu, la face et les
labels indépendants. La campagne d’évaluation et de faux positifs
reste conditionnée à ces repères et à des splits documentés.
Les annotations représentent des candidats à relire.
