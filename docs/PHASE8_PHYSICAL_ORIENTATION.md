# Orientation physique de la pile CT

Aux dix témoins contrôlés depuis la phase 7, l’augmentation de l’indice de profondeur dans le rendu historique suit la direction `−N`, où `N` est la normale calculée dans le repère CT physique. La face anatomique du segment reste indéterminée.

## Repères et conventions

- Dans TIFXYZ, un nœud `P(U,V)` donne des coordonnées CT `(X,Y,Z)`. L’oracle définit `N = (dP/dU × dP/dV) / ||dP/dU × dP/dV||` dans ce repère droit. Il réordonne les composantes en `(Z,Y,X)` pour lire le volume brut.
- `Z` dans A+/A− désigne la profondeur échantillonnée le long de la normale locale. Le signe de la coordonnée verticale du tomographe dépend des composantes locales de cette normale.
- Nous utilisons le TIFXYZ historique de `20250919184428` projeté sur l’acquisition `20250526151718`, pas de 2,215 µm. L’origine du segment dans l’Atlas pointe vers l’acquisition `20250528085330`. L’audit Atlas conserve les transformations inter-acquisitions, les rôles et la révision. Le volume brut L0 a une forme ZYX `[28096,18209,18209]` et un pas d’en-tête `[1,1,1]` en unités de voxel. [Trace Atlas](validation/phase8-ink-references.json) · [Audit phase 7](PHASE7_Z_ORDER_EXPERIMENT.md)
- Le code public du moteur prévoit la bascule `flip-normals`. La convention de rendu vise une face interne pour les surfaces correctement orientées des rouleaux. Il faut attester l’orientation de ce maillage et le rattachement à la feuille physique du fragment avant de transférer cette convention. Les cartes A+/A− restent des profils de scores indexés par l’ordre d’entrée. [Moteur de rendu épinglé](https://github.com/ScrollPrize/villa/blob/530584554c031c982ba3aa243e1ea39c4bef9818/volume-cartographer/apps/src/vc_render_tifxyz.cpp#L1084)

## Contrôle dans le CT brut

La sélection ajoute le nœud le plus intérieur admissible de chaque quadrant, un nœud de bord avec au moins 12 pixels de marge et un témoin de forte courbure. Elle fixe les espacements et écarte les quatre témoins de la phase 7 avant tout examen des scores d’encre. Sur chaque nœud, l’oracle compare un voisinage de 13 × 13 CT aux deux signes de normale et aux cinq plans 43, 51, 59, 67, 75. Les centres, normales, bornes voxel et empreintes des briques sont conservés.

| V,U | Sélection | Pearson, `−N` | Pearson, `+N` | Erreur absolue CT moyenne, `−N`, sur 255 |
| --- | --- | ---: | ---: | ---: |
| 560,560 | Quadrant nord-ouest | 0,989 | 0,473 | 2,90 |
| 540,820 | Quadrant nord-est | 0,989 | 0,667 | 3,07 |
| 640,660 | Quadrant sud-ouest | 0,995 | 0,192 | 1,92 |
| 720,820 | Quadrant sud-est | 0,997 | −0,372 | 1,48 |
| 980,1080 | Bord | 0,998 | −0,067 | 1,66 |
| 360,600 | Forte courbure, 38,2° | 0,926 | −0,326 | 9,29 |

L’augmentation de l’erreur dans la zone courbe limite la précision à laquelle ce test peut localiser une lamelle. Il suffit ici à départager les directions. Les contrastes visibles entre couches, bords et faisceaux ne situent pas, à eux seuls, la face d’écriture. [Six témoins et empreintes](validation/phase8-orientation-windows.json) · [Oracle](validation/phase8_orientation.py)

## Références de face

Le jeu officiel `surface-labels` décrit des masques voxelisés de recto. Le Zarr `0500p2_5217.zarr` cite la même acquisition brute, avec la même forme L0 et une transformation identité en ZYX. Il constitue une piste géométrique indépendante des prédictions d’encre. Un sondage dans la grille commune sur les six témoins, à ±64 voxels le long de la direction mesurée et sur 25 positions tangentes, ne rencontre aucun voxel étiqueté. Les 17 objets requis renvoient HTTP 404 dans ce Zarr clairsemé, qui déclare un remplissage à zéro. Un autre objet listé, de 5 364 octets, a bien été lu et contient des étiquettes après décodage. Le chevauchement reste inconnu ailleurs sur le segment. [Description officielle](https://scrollprize.org/data/datasets/surface-labels-README.md) · [Attributs du masque](https://huggingface.co/buckets/scrollprize/datasets/resolve/surfaces/2um_032726/0500p2_5217.zarr/.zattrs) · [Sondage](validation/phase8-recto-windows.json)

Le jeu optique fournit une topographie calibrée et un champ clair du même fragment. Pour attester la face, il faut retrouver la zone dans le CT via des particularités de géométrie, identifier la couche et le côté visibles lors de la prise optique, contrôler la reconstruction dans le CT brut et mesurer l’erreur sur des points mis de côté. La concordance avec le TIFF A de production reproduit une recette d’inférence. Elle n’entre pas dans ce contrôle physique. [Référence optique et expérience suivante](PHASE8_INK_VALIDATION.md)
