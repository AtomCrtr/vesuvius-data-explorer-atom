# I2 — État de l'art (novembre 2026) : ce que fait la communauté, l'IA, et ce qui manque

- **Date :** 18 novembre 2026 · **Demandée par :** PO · **Menée par :** orchestrateur.
- **Questions :** que publie la communauté du Vesuvius Challenge ? quelles techniques d'IA ont servi
  à lire les rouleaux ? quelles lois mathématiques peuvent nous servir ? qu'est-ce qui a pu être
  manqué ? Où notre projet peut-il apporter une contribution primable ?
- **Sources :** pages officielles (prix, gagnants, problèmes ouverts 2026), articles arXiv et Kaggle,
  dépôts GitHub des projets primés, consultés le 18 novembre 2026. Liens en fin de document.

## Résumé

1. **Les grands prix sont hors de notre portée** (dérouler un rouleau entier, lire de l'encre).
   Les **Progress Prizes** mensuels (250 $ à 20 000 $, prochaine échéance le 30 novembre 2026)
   sont accessibles, mais **découragent explicitement les outils autonomes d'audit** : il faut
   faire avancer directement le déroulement ou la lecture.
2. **Le contrôle qualité générique de surfaces existe déjà et a été primé** : TIFXYZ Doctor
   (métadonnées, distorsion, topologie), windcheck (auto-intersections), scroll-data-audit
   (catalogue). Notre QC de surface seul ne serait pas une nouveauté.
3. **Le manque le plus clairement identifié par l'équipe** : la **qualité des surfaces annotées**,
   « l'un des principaux goulots du déroulement ». Les surfaces tracées dérivent de la vraie feuille
   et passent parfois d'une feuille à l'autre. L'équipe demande du **« label snapping »** (recaler
   une surface sur la feuille à partir du signal CT) et de l'**apprentissage actif** (désigner aux
   humains les zones à corriger).
4. **Notre mesure d'alignement (T5.1, calibrée deux fois) est exactement la brique manquante**
   pour une carte dense de dérive, la détection locale des sauts de feuille et un recalage mesuré.
   C'est l'objet de la spécification [T10](../tasks/T10-carte-alignement.md).
5. **Audit du 18 novembre 2026** (section 4) : le décalage d'environ −10 µm des surfaces publiées
   est réel mais s'explique très probablement par la face suivie, pas par un défaut ; l'écart de
   forme de Scroll 1 dans le catalogue est une incohérence mineure, pas un catalogue faux.

## 1. Ce que publie la communauté (prix 2026)

Projets primés proches de nos sujets (montant, mois) :

| Projet | Ce qu'il fait | Rapport avec nous |
|---|---|---|
| TIFXYZ Doctor (1 000 $, juil.) | QA déterministe des grilles tifxyz : métadonnées, cohérence, distorsion, topologie | Recouvre une partie de notre QC de surface |
| windcheck (1 000 $, juil.) | Auto-intersections des surfaces, réparation certifiée | Complémentaire (topologie, pas alignement) |
| scroll-data-audit (1 000 $, juil.) | Cohérence du catalogue, des tableaux Zarr et des noms | Recouvre notre audit du catalogue |
| Optimising patch connectivity, W. Stevens (2 500 $, juil. ; 20 000 $, août) | Retire les zones qui causent des sauts de feuille à partir de l'incompatibilité géométrique des patchs | Détection **géométrique** ; nous proposons une détection **par le signal CT** |
| ScrollFiesta, B. Kyles (20 000 $ juil., 5 000 $ sept.) | Maillage automatique qui « s'accroche » au papyrus dans le scan | Produit des surfaces ; nous mesurons et corrigeons des surfaces existantes |
| nnInteractive label refinement, B. Hamm (1 000 $, août) | Raffinement des labels de surface par un modèle de segmentation interactif | Même but (labels plus justes), méthode lourde (GPU, modèle) |
| winding-field, L. Wainer (1 000 $, oct.) | Champ scalaire dont les isosurfaces entières sont les spires | Idée voisine de notre « phase » (section 3.3), mais globale |
| Automated fiber extraction, S. Lerognon (20 000 $ sept., 2 500 $ oct.) | Fibres de papyrus extraites et intégrées à VC3D et au spiral fit | Les fibres pourraient valider notre recalage |
| Zarr downsampling issue, E. Nathaniel (250 $, oct.) | Niveaux sous-échantillonnés qui ne gardaient que les premières coupes | **Défaut de données trouvé à la main** : notre moteur pourrait l'automatiser (section 4) |

Tendances : outils intégrés à **VC3D / villa** (le logiciel officiel), portabilité (Windows, Apple
Silicon, AMD), modèles d'encre distillés à 9 µm, fibres, spiral fit, et nombreuses petites
corrections de code primées de 250 à 500 $.

## 2. Machine learning et IA utilisés pour lire les rouleaux

### 2.1 Les familles d'apprentissage en jeu

| Famille de machine learning | Où elle sert dans le Vesuvius Challenge |
|---|---|
| **Apprentissage supervisé** (réseaux convolutifs 3D, U-Net, nnU-Net) | Prédire la surface du papyrus et l'encre à partir d'étiquettes humaines |
| **Apprentissage semi-supervisé** (pseudo-étiquettes, mean-teacher, étiquetage itératif) | Étendre l'encre trouvée sur un rouleau aux zones et rouleaux voisins sans annotation |
| **Apprentissage auto-supervisé** (DINO 3D, apprentissage contrastif) | Apprendre des représentations du scan sans étiquettes, puis fabriquer des cibles |
| **Transfert et distillation** | Passer d'un modèle 2,4 µm à 9 µm, des fragments ouverts aux rouleaux fermés |
| **Ensembles et moyennes de modèles** | Stabiliser les prédictions d'encre (moyennes de checkpoints, ensembles) |
| **Apprentissage actif** (demandé par l'équipe) | Désigner aux humains les zones dont la correction rapporte le plus |
| **Recherche automatisée d'architectures** (agents autonomes) | Explorer des variantes de modèles d'encre sans intervention humaine |
| **Grands modèles de langue** | Restaurer les lacunes des textes grecs une fois lus |
| **Méthodes classiques sans apprentissage** (filtres de hessienne, diffusion anisotrope, optimisation géométrique) | Nettoyer les prédictions, tracer et aplatir les surfaces, dont nos propres mesures |

Le fil conducteur : **les étiquettes sont rares et approximatives**. Le progrès vient autant de
meilleures étiquettes (raffinement, recalage, apprentissage actif) que de plus gros modèles.

### 2.2 Techniques et résultats récents

- **Segmentation de surface en 3D** : U-Net 3D / **nnU-Net**, entraînés sur des maillages humains ;
  concours Kaggle « Surface Detection » (200 000 $, mars 2026) évalué par des **métriques
  topologiques** ; post-traitements gagnants : filtre de « feuillité » de Frangi (valeurs propres de
  la hessienne : |λ1| ≈ |λ2| ≈ 0, |λ3| ≫ 0), diffusion anisotrope (CED), fermetures anisotropes,
  correction topologique par distance signée.
- **Apprentissage auto-supervisé 3D** : **DINOv2 adapté en 3D** (`dinovol`), dont les plongements
  servent à fabriquer des cibles de segmentation (fibres) et à filtrer des pseudo-labels.
- **Segmentation interactive** : **nnInteractive** pour raffiner des labels à partir de quelques
  indications.
- **Détection d'encre** : modèles 3D→2D conditionnés par la surface, entraînés sur des fragments
  ouverts puis étendus par **pseudo-étiquetage** (mean-teacher), **distillation** 2,4 µm → 9 µm,
  ensembles et moyennes de checkpoints ; **segmentation 3D directe** de l'encre visible dans les
  scans 2,4 µm de PHerc. Paris 4 (prétirage arXiv:2606.29085).
- **Encre sans encre** : la **topographie seule** de la surface suffit à prédire l'encre sur des
  fragments ouverts (Dice 0,88 à 0,90, *Scientific Reports* 2026).
- **Lecture complète** d'un rouleau fermé, **PHerc. 1667** (2026) : scan synchrotron optimisé,
  maillage corrigé, aplatissement quasi isométrique, encre par modèles et revue papyrologique.
- **Agents de recherche autonomes** (inspirés de karpathy/autoresearch, mars 2026) : un essaim
  d'agents a trouvé une architecture d'encre qui **double presque le Dice** en généralisation
  inter-rouleaux.
- **Modèle de langue pour le grec** : **Apollo Restore** (24 milliards de paramètres, sept. 2026)
  restaure les lacunes des textes grecs fragmentaires.
- **Rappel historique** : le Grand Prix 2023 a été gagné avec des modèles d'encre 3D→2D de type
  **TimeSformer** (transformer vidéo) et réseaux convolutifs, entraînés sur des fragments ouverts
  puis par étiquetage itératif sur les rouleaux.

### 2.3 Ce que le machine learning peut apporter à notre outil

Notre mesure d'alignement est aujourd'hui **sans apprentissage** : moyenne de profils, recherche
de pic, statistiques. C'est un atout (aucun GPU, résultat explicable), mais le machine learning
peut l'améliorer à trois endroits, du plus simple au plus ambitieux :

1. **Signal plus propre en entrée.** Remplacer l'intensité CT brute par une **probabilité de
   surface** prédite par un modèle existant (nnU-Net du concours Kaggle, publié par l'équipe).
   Le pic devient plus net, donc plus de mesures fiables (aujourd'hui 31 %). Coût : un modèle
   à faire tourner sur les zones lues.
2. **Profils appris.** Apprendre la forme typique du profil d'une feuille (modèle de régression
   léger, ou simple filtre adapté estimé sur les 42 segments calibrés) pour reconnaître une feuille
   même peu contrastée, et estimer l'espacement des feuilles.
3. **Boucle d'apprentissage actif.** Les zones à revoir de T10 sont exactement les données qui
   manquent aux modèles de surface : chaque correction humaine guidée par la carte devient une
   **étiquette de meilleure qualité**. Les surfaces recalées peuvent servir de **pseudo-étiquettes**
   filtrées par la fiabilité, comme dans les approches mean-teacher.

T10 commence sans apprentissage (point 1 de la validation : mesurable, reproductible) ; les pistes
1 et 2 sont des étapes ultérieures, à décider selon les résultats.
- Architectures récentes primées : HercUNet / HercuViT (20 000 $, oct.), PLatS (plongements
  d'instance des feuilles), ScrollFiesta, champ de spires.

## 3. Lois mathématiques utiles (et ce qu'elles nous disent)

### 3.1 Modèle du profil le long de la normale

Le long de la normale d'une surface bien placée, l'intensité suit approximativement
`I(s) = b + Σ_k A·g(s − s₀ − kΔ) + ε(s)` : des feuilles de profil `g`, espacées de `Δ`, sur un fond
`b`, avec un bruit `ε` d'écart-type `σ`. La mesure de T5.1 estime `s₀`.

### 3.2 Borne de Cramér-Rao : pourquoi 36 patchs valent mieux que 12

Pour un pic de forme connue, la précision de `s₀` est bornée par
`σ(ŝ₀) ≥ σ / (A·√(N·Σ g′(s)²))`, avec N le nombre de profils moyennés. La précision varie en
**1/√N** : passer de 12 à 36 patchs l'améliore d'un facteur √3 ≈ 1,7. C'est ce que la
calibration a observé (69 % → 88 % de récupération). La borne donne aussi l'**intervalle de
confiance attendu** de chaque mesure : on peut l'afficher au lieu d'un bootstrap.

### 3.3 Le « saut de feuille » est un problème de déroulement de phase

Le profil est périodique de période `Δ` : un décalage `d` et un décalage `d + kΔ` sont
indiscernables localement. On peut donc écrire le décalage comme une **phase**
`φ = 2π·d/Δ (mod 2π)`. Sur une surface correcte, cette phase varie doucement d'une région à
l'autre. Quand une surface passe d'une feuille à la voisine, la phase saute de 2π : c'est
exactement un **résidu** au sens du **déroulement de phase** utilisé en interférométrie radar
(InSAR) et en IRM (algorithme de Goldstein). La somme des différences de phase « repliées »
autour d'une petite boucle de régions vaut 0 sur une surface saine, et ±2π autour d'un point de
saut. **Cela localise les sauts de feuille à partir du seul signal CT**, sans modèle appris.
Nous n'avons trouvé aucune publication de la communauté qui l'exploite ; c'est l'idée la plus
neuve de ce rapport, à vérifier expérimentalement.

### 3.4 Surfaces en couches : la recherche de surface optimale par graphe

Les feuilles de papyrus ressemblent aux **couches de la rétine** en tomographie par cohérence
optique (OCT). En OCT, on segmente des surfaces en couches par **recherche de surface optimale
sur graphe** (Li et al. 2006 ; Garvin et al. 2009, « LOGISMOS ») : optimum global d'une énergie
« attache au signal + régularité », avec des contraintes de séparation entre couches, calculé
exactement par coupe minimale. Pour recaler une surface sur sa feuille, cela donne un champ de
décalages **globalement optimal et lisse**, plutôt qu'une correction point par point. Le domaine
de la rétine est mûr ; nous n'avons pas vu ce transfert dans la communauté.

### 3.5 Le papyrus est une feuille développable

Une feuille de papyrus ne s'étire pas : avant déformation, elle est **développable**, à
**courbure de Gauss nulle** (théorème remarquable de Gauss). Une région de segment à forte
courbure intrinsèque, ou dont l'aplatissement exige un étirement, signale probablement un défaut :
déchirure, pli ou saut de feuille. C'est un critère de qualité simple, invariant par la pose, qui
complète notre indicateur d'étirement.

### 3.6 Échantillonnage

À 9 µm par voxel, une feuille (environ 100 à 200 µm) et l'espace entre deux feuilles ne couvrent
que quelques voxels. Le **théorème d'échantillonnage** explique pourquoi la classe 8 µm a été la
moins bien calibrée (récupération 10 / 14 contre 14 / 14 à 2,4 µm, second échantillon) : il faut
l'interpolation sous-voxel et, quand il existe, un scan plus fin.

## 4. Ce que d'autres ont pu manquer (après audit)

Les constats ci-dessous ont été **audités le 18 novembre 2026** à la demande du PO ; deux affirmations
de la première version de ce rapport ont été corrigées.

1. **Localiser les sauts de feuille par le signal CT** (phase, section 3.3), là où les outils
   existants raisonnent sur la géométrie des patchs. Non vu dans la communauté ; à vérifier.
2. **Mesurer avant de corriger.** Les outils qui « accrochent » une surface au papyrus ne publient
   pas de carte chiffrée de ce qu'ils déplacent, ni d'incertitude. Une carte de décalages avec
   intervalle de confiance permet d'auditer un recalage et de nourrir l'apprentissage actif.
3. **Position des surfaces publiées par rapport à leur feuille : ce n'est pas un biais à corriger.**
   - Sur 41 segments publiés déterminés, la feuille la plus claire est en médiane à **−10 µm** de
     la surface le long de sa normale, estimation sous-pas comprise (quartiles −20 et −2,6 µm).
     Ce n'est donc pas un artefact du pas d'échantillonnage (environ 9 µm).
   - Les normales de grille sont orientées **vers le centre du rouleau** pour 35 segments sur 37.
     Le centre clair de la feuille se trouve donc environ 10 µm **vers l'extérieur** de la surface.
   - Lecture la plus probable : les segments suivent **une face de la feuille** (côté centre du
     rouleau) plutôt que son centre clair. Nous n'avons pas trouvé la convention de VC3D écrite ;
     c'est une hypothèse, pas une erreur des annotateurs, et rien qui ait été « manqué ».
   - Réserves : axe du rouleau estimé grossièrement (centre du volume), et la règle de pic actuelle
     a un défaut (point 7).
   - **Conséquence pour T10** : recaler sur le pic de brillance déplacerait les surfaces d'environ
     10 µm à tort. Le recalage doit corriger la dérive locale **par rapport au décalage habituel
     du segment**, pas viser le centre de la feuille.
4. **Forme de Scroll 1 dans le catalogue : incohérence mineure, pas un catalogue « faux ».**
   - La fiche annonce `shape` = (14 369, 7 888, 8 096). La même fiche décrit un recadrage
     `z_crop_start = 0`, `z_crop_end = 14 257`. Le Zarr publié a bien 14 258 coupes.
   - Pour les deux autres volumes recadrés du catalogue, `shape` reflète le recadrage ; pour
     Scroll 1, non.
   - Le schéma du catalogue précise que `shape` est « relevé à l'ingestion ; lire les métadonnées
     Zarr, qui font foi ».
   - L'outil primé scroll-data-audit fait ce contrôle, mais n'a audité que les volumes du bucket
     S3 ; Scroll 1, publié en HTTPS, n'y figure pas. Signalement possible aux mainteneurs, de faible
     portée.
   - Les 4 volumes dont `shape` est absent (relevés par notre T4.2) étaient déjà signalés
     (villa#1516).
5. **Intégrité des pyramides : déjà couverte.** La première version de ce rapport la présentait comme
   un manque ; scroll-data-audit vérifie déjà la justesse numérique des niveaux (`--deep`,
   320 transitions sur 320 exactes). Retiré des manques.
6. **Trous des segments `auto_grown`.** Notre contrôle en lot montre que 12 des 19 segments de
   septembre 2025 de PHerc0814 ont 2 à 8 % de trous intérieurs : une information utile aux
   annotateurs (T7).
7. **Défaut de notre propre mesure, trouvé par cet audit.** Quand l'espacement des feuilles est plus
   petit que la fenêtre de recherche, la règle « maximum le plus clair de la fenêtre » peut choisir
   une feuille voisine. C'est le cas sur des feuilles synthétiques serrées au niveau 3 (−48 voxels au
   lieu de 0). Sur les 42 segments réels, la règle « maximum local le plus proche » donne la même
   médiane ; T10 l'adoptera.

## 5. Recommandation

Viser un Progress Prize avec la **carte d'alignement et le recalage des surfaces tifxyz**
(spécification [T10](../tasks/T10-carte-alignement.md)) :

- répond à un problème ouvert nommé par l'équipe (qualité des labels, label snapping,
  apprentissage actif, sauts de feuille) ;
- s'appuie sur une mesure déjà **calibrée deux fois** sur 42 segments réels ;
- produit des formats de la communauté (tifxyz recalé, carte alignée sur la grille) et une preuve
  visuelle exigée par le règlement : les **fibres de papyrus visibles** sur la surface aplatie.

Diffusion : dépôt public et paquet PyPI, message illustré sur le Discord du Vesuvius Challenge,
puis formulaire de candidature mensuel.

## Sources

- Prix et règlement : https://scrollprize.org/prizes
- Gagnants : https://scrollprize.org/winners
- Problèmes ouverts 2026 : https://scrollprize.org/2026_open_problems
- Lecture complète de PHerc. 1667 : https://arxiv.org/abs/2606.29085
- Encre par la topographie : https://arxiv.org/abs/2603.27698 (*Scientific Reports*, 2026)
- Apollo Restore : https://arxiv.org/abs/2609.22455
- Kaggle Surface Detection (solutions) :
  https://www.kaggle.com/competitions/vesuvius-challenge-surface-detection
- TIFXYZ Doctor : https://github.com/aviad12g/tifxyz-doctor
- windcheck : https://github.com/joe-carr-data/windcheck
- scroll-data-audit : https://github.com/Bullo27/scroll-data-audit
- scrollreading (W. Stevens) : https://github.com/WillStevens/scrollreading
- ScrollFiesta : https://github.com/Hob3rMallow/scrollfiesta_public
- nnInteractive label refinement :
  https://github.com/hammb/vesuvius-surface-detection-nninteractive-refinement
- Références mathématiques : Goldstein, Zebker & Werner (1988), *Satellite radar interferometry:
  two-dimensional phase unwrapping* ; Li, Wu, Chen & Sonka (2006), *Optimal surface segmentation in
  volumetric images — a graph-theoretic approach* ; Garvin et al. (2009), segmentation des couches
  de la rétine en OCT ; Kay (1993), *Fundamentals of Statistical Signal Processing* (borne de
  Cramér-Rao).
