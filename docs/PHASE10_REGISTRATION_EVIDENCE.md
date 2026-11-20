# État des preuves de recalage CT–optique

**ν2 reste bloqué par l’absence d’une référence de localisation.** Le JPEG M1050 n° 017 et le frontal historique avec IR aligné sont disponibles. La nouvelle provenance donne une voie concrète pour demander les emprises et les transformations. Elle ne fournit aucun nouveau repère optique–CT identifiable pour ν2. [Sources et empreintes](PHASE10_SOURCE_INVESTIGATION.md)

## Chaîne de coordonnées

| Lien | Preuve disponible | Élément encore nécessaire |
| --- | --- | --- |
| Coordonnées XY de ν2 sur le profilomètre | Identifiant `500P2_230925_N2`, 4 499 × 3 628 et positions XY explicitement exportées. | Calibration indépendante de la taille de pixel, convention des axes physiques, historique des exports. |
| Champ ν2 → photographie de situation | Même fragment identifié sous PHerc. 500P2. La photographie entière n° 017 montre la surface exposée. | Polygone annoté du champ, orientation ou coordonnées de platine vérifiables, et au moins un accident de matière commun pour borner la recherche sur cette face. Un cliché de campagne portant les emprises convient aussi. |
| Photographie → frontal historique | Le préprint décrit le recalage manuel du n° 017 vers un composite CT frontal. Le dossier ancien contient IR, couches, masque et annotations alignés. | Contrôles originaux ou transformation enregistrée, repère source exact, compensation de crop, parité et identification de la version utilisée dans la figure. Les images déjà alignées permettent un contrôle de co-grille dans ce repère historique. |
| Frontal historique → CT Atlas | Frontal `20250628074500-500P2_front` et volume `20250526151718`, avec deux révisions de TIFXYZ. Dimensions historiques 14 990 × 27 160 contre 15 060 × 26 440 pixels pour le rendu Atlas. La référence CT de lancer de rayons existe séparément. | Correspondance entre les repères du frontal historique et du rendu retenu. La comparaison peut rester dans le repère historique si la grille, la géométrie 3D locale et le lien optique y sont attestés. |
| Face et profondeur | Le champ optique documente une face d’écriture exposée. Le sens `−N` est vérifié sur le rendu historique `wrap01_0919`. | Confirmation de la face vue sur le cliché de situation et identification de la même lamelle dans les coupes CT. La profondeur vers le recto ou le verso de ν2 reste indéterminée. |

Entre les **2 181 nœuds valides échantillonnés** du TIFXYZ historique de `wrap01_0919` et les nœuds disponibles du maillage frontal, le plus proche est à 4,421 mm pour la première version et 4,427 mm pour t2. Cette mesure concerne ces deux géométries dans le même volume, à la résolution d’échantillonnage des nœuds. Elle favorise l’examen du frontal ou d’une autre surface documentée une fois le champ localisé. Elle laisse ouverte la position de ν2 sur le fragment. [Rapport géométrique initial](validation/phase9-localization.json)

## Reprise conditionnelle sur un seul champ

1. Résoudre la calibration optique et obtenir l’emprise de ν2 sur une photographie de référence ou un relevé de platine. Relier cette référence au CT à partir des contrôles d’origine, ou d’un nouvel appariement de structures identifiables et tracées.
2. Ouvrir un recadrage natif avec marge, masquer scores et annotations et vérifier la couche et la face à partir du CT brut. Réserver au moins trois repères indépendants et conserver quatre repères ajustés distribués dans la zone. Geler leur sélection et les conventions X,Y avant de choisir un modèle géométrique.
3. Appliquer le protocole rigide ou affine de phase 9 et enregistrer révisions, empreintes, transformation, inverse, résidus individuels, RMS et P90, couverture et zones invalides. Les seuils du pilote restent annoncés avant les scores. Un recalage fiable exige que le RMS et le P90 réservés restent sous deux pixels CT et sous le quart de la plus petite largeur d’intérêt.
4. Geler la géométrie et documenter les incertitudes de face, d’échelle et de recalage. L’évaluation des scores nécessite ensuite une preuve indépendante liée au poids exact. Une coïncidence en image ou une écriture visible ne suffit pas à ces deux contrôles.

Les sorties négatives de phase 9 demeurent la référence expérimentale. En phase 10, la vérification porte sur les fichiers et la compatibilité des repères publiés. Aucun ajustement de ν2, choix d’orientation optique ou test d’encre n’a été relancé. [Critères et code existants](PHASE9_GEOMETRIC_UNCERTAINTY.md)
