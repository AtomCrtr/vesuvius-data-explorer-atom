# Incertitude géométrique du recalage CT–optique

Aucun repère anatomique commun n’a été accepté pour ν2. Les résidus par repère, l’erreur médiane, le RMS, la couverture et la carte d’incertitude réelles sont donc indisponibles. Les scores de recherche sur la figure CT caractérisent une ambiguïté de localisation. Ils n’expriment pas une erreur physique. [Résultat pilote](PHASE9_CT_OPTICAL_REGISTRATION.md)

## Critères avant inspection des scores

1. Vérifier l’échelle latérale optique sur une source indépendante, définir les centres de pixels, l’origine et le pas de chaque modalité. Établir le côté physique dans le volume et relever l’éventuelle réflexion du repère image. Une réflexion dans le plan ne suffit pas à établir le recto ou le verso.
2. Choisir au moins quatre repères d’ajustement répartis dans deux directions et au moins trois repères de contrôle distincts. Préférer les jonctions de fissures, contours ou accidents de relief décrits dans les deux modalités. Reporter les identifiants, les coordonnées et l’origine de chaque observation. Fixer les groupes et la largeur minimale des structures à évaluer avant de charger les annotations et les scores.
3. Commencer par une transformation rigide dans un repère local CT orthorectifié. L’ajustement affine peut être choisi si le changement de projection l’exige et si plusieurs repères indépendants couvrent la zone. Le protocole affine borne les deux facteurs d’étirement singuliers entre 0,9 et 1,1. Le cas d’une feuille physiquement déformée demande une preuve et davantage de repères. Aucun ajustement non rigide n’a été utilisé.
4. Exiger que le RMS et le P90 réservés soient chacun inférieurs ou égaux au minimum de deux pas CT et du quart de la plus petite largeur étudiée. Sur le CT de 2,215 µm, le plafond est donc 4,43 µm. Exiger une enveloppe convexe d’ajustement couvrant au moins 25 % du rectangle d’évaluation et une enveloppe de contrôle couvrant au moins 5 %, avec les points réservés dans l’enveloppe d’ajustement. Retrancher les trous et zones invalides du support effectif. Pour les petits groupes, le P90 reste un diagnostic empirique.

La fonction d’ajustement prend un tableau de repères structuraux et deux grilles physiques. Elle écrit la transformation directe et l’inverse, la parité, les valeurs singulières, les résidus individuels en µm et en pixels CT, le RMS, la médiane et les couvertures. Les repères réservés ne contribuent jamais à l’ajustement. Elle recalcule les transformations en retirant successivement un repère d’ajustement. Les contrôles synthétiques couvrent rotation/réflexion, échelle et origine, résidus réservés, inverse et pixels manquants. [Code de recalage](../src/vesuvius_data_explorer/core/optical_registration.py) · [Tests](../tests/test_optical_registration.py)

## Trois sources d’incertitude

| Source | Mesure ou statut |
| --- | --- |
| Recalage | Sur la zone interpolée à l’intérieur de l’enveloppe et du support optique, la carte combine en quadrature le RMS réservé et le RMS du déplacement local obtenu en retirant successivement un repère. C’est un indicateur de stabilité conditionnel, sans interprétation d’intervalle de confiance. |
| Échelle physique | Les deux hypothèses impliquent une différence de fin de champ de 1,565 mm en X et 1,262 mm en Y. L’incertitude d’échelle reste distincte du RMS du recalage. Aucun choix n’est fait à partir d’un score d’encre. |
| Face et couche | Le sens `−N` concerne la profondeur du rendu historique. L’identité de la lamelle et le côté correspondant à l’acquisition optique restent indéterminés. Cette incertitude ne s’exprime pas en micromètres. |

En recalage, le masque discret utilise le plus proche voisin. Les intensités utilisent une interpolation linéaire là où les pixels nécessaires sont valides. Le code exclut l’extrapolation hors enveloppe des repères, les coordonnées hors champ et les données invalides. Pour toute mesure, utiliser la grille CT et déclarer le support fini dans les deux conditions. Un rééchantillonnage ne change ni la résolution physique, ni la taille minimale d’un motif attribuable.
