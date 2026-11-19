# Vesuvius Challenge — audit et expérimentation du 19 novembre 2026

**Décision proposée à Claude Opus.** Poursuivre la voie First Letters avec VC3D pour produire les
fenêtres CT, Vesuvius Data Explorer pour contrôler leur géométrie, puis deux modèles publics pour
comparer la détection sur des régions indépendantes. Évaluer HerculeX pour ses diagnostics de
raccordement avant d'envisager une chaîne de déroulement complète.

Le prototype local `vesuvius-qc encre` compare deux cartes et trois fusions. Sur deux fenêtres
simulées, le produit réduit le taux de faux positifs de **10,16 % à 2,46 %** face à la carte de
gauche, avec un rappel de **100 % à 94,26 %**. Un artefact commun aux deux cartes persiste.
Ces mesures décrivent l'expérience synthétique. La précision sur de l'encre réelle reste à mesurer.

## État des preuves

| Statut | Observation |
|---|---|
| Discord, d'après les notes transmises | KLAVIS décrit une ouverture intérieure mieux définie sur une forme évoquant un P, sur le même scan et la même surface. Le candidat V4 aurait perdu 0,02 à 0,03 d'AUC par rapport à V3. Les images brutes, poids, annotations et paramètres de ce test n'étaient pas joints. |
| Discord, d'après les notes transmises | Adam Betka estime 50 à 70 % de surface récupérée par HerculeX et signale un ajustement global difficile. La définition du dénominateur et la vérité terrain de couverture restent inconnues. |
| Publications officielles | Le Challenge a annoncé les prix de PHerc. 343, 306B et 211 et le déroulement intégral du papyrus conservé de PHerc. 1667. Voir les sources et méthodes ci-dessous. |
| Déclarations publiques des auteurs | Les chiffres de Reader V3, HerculeX et des lauréats proviennent de leurs protocoles respectifs. Leurs masques, tâches et machines diffèrent. |
| Hypothèses du projet | Une fusion peut écarter des artefacts propres à un modèle. Deux modèles partageant leurs données, pseudo-labels ou erreurs de surface peuvent produire la même fausse structure. Un contour plus continu peut provenir de l'encre, du lissage ou du contexte appris. |

## A. Audit du dépôt GitHub et de Windows

Le dépôt distant est [AtomCrtr/vesuvius-data-explorer-atom](https://github.com/AtomCrtr/vesuvius-data-explorer-atom).
La branche principale publique était sur `625db53` (fusion T10, PR #28). L'audit local a commencé
sur `4c7b5cf` avec le suivi T10 en cours. Le suivi apparaît ensuite dans le commit `426e712`
sur `feat/t10-gel-napari`. Le prototype s'appuie sur les interfaces existantes et se branche sur
la CLI `vesuvius-qc`.

| Étape | Existant | Résultat documenté / interface manquante |
|---|---|---|
| Ingestion CT | Catalogue, Zarr / OME-Zarr local, HTTPS et S3, napari avec Dask, cache et lecture bornée de régions | T6 sur PHerc0800 en cloud 4 cœurs, coupe suivante 0,20 s à chaud et première vue 3,24 s à froid après ouverture. Codec récent `vc-delta3d` optionnel et absent du venv Python 3.11. Préférer un volume standard pour le pilote. [T6](validation/T6-performance.md) |
| Segmentation et contrôle | Import des surfaces `tifxyz`, repères volume/segment, superposition, contrôles de trous, replis, étirement et limites, batch par volume | La segmentation est produite en amont. Il manque le traçage de feuilles, l'identité globale des tours et le contrôle des coutures. [T5](validation/T5-surfaces.md) · [T7](validation/T7-qc-en-lot.md) |
| Alignement | Profils CT le long des normales, carte par tuile, zones à revoir, recalage borné | T10 sur huit segments, rampe imposée retrouvée sur 1 588 / 1 649 tuiles fiables, résidu médian 3,5 à 5,8 µm sur sept segments mesurables, 10 à 80 s par carte. L'analyse de phase ne s'est activée sur aucun des huit segments. Un saut vers une feuille voisine peut échapper au contrôle. [T10](validation/T10-carte-alignement.md) |
| Aplatissement et rendu | Interpolation d'une grille déjà paramétrée et échantillonnage CT, possibilité de moyenner plusieurs décalages normaux | `core.flatten.flatten` retourne un plan 2D. Reader et Studio exigent une pile orientée, un pas physique explicite et une normalisation compatible. Employer le renderer VC3D pour le premier essai. [Code du rendu](../src/vesuvius_data_explorer/core/flatten.py) |
| Encre | Le projet de départ ne contient ni modèle ni poids ni annotations d'encre. L'ajout évalue des cartes importées. | Inférence, export d'une pile compatible et corpus indépendant à raccorder. |

Inventaire du venv Windows vérifié avec `pip list` et inspection de `pyproject.toml`. Python 3.11,
NumPy 2.4.6, SciPy 1.17.1, Zarr 3.1.6, Dask 2026.8.0, fsspec / s3fs 2026.9.0,
TIFFfile 2026.3.3, Pillow 13.0.0, napari 0.10.0 et PyQt6 6.12.1. PyTorch, `villa` et
`vc-delta3d` sont absents du venv. `nvidia-smi` a détecté la RTX 4080 Laptop, **12 282 Mio** et
le pilote **616.64**. Environ 270 Gio libres étaient visibles sur C:. `wsl --list --verbose`
n'a listé que `docker-desktop`, arrêté, en version 2. CUDA a été identifié côté hôte par le
pilote, sans test d'inférence ni test CUDA dans une distribution Linux.

## B. Matrice technique

Les coûts indiqués comme estimés sont des budgets de pilote. Les autres chiffres sont ceux des
publications citées et ne sont pas des mesures sur la RTX 4080 du projet.

| Solution et rôle | Disponibilité et licences | Matériel, calcul et stockage | Résultat documenté | Intérêt et priorité |
|---|---|---|---|---|
| **Data Explorer** · lecture, rendu local, contrôle QC | Dépôt public MIT, scans selon leur licence | Windows natif CPU. Cache par défaut de 10 Gio, lecture par blocs. | T6 / T10 mesurent navigation et alignement, sans métrique d'encre historique. | **P0** · contrôler les surfaces et les entrées du benchmark. |
| **Reader V3** · encre sur volume de surface à ~9 µm | Code et poids MIT. `reader-v3.pth` public, **138 379 659 octets**. Labels d'origine à vérifier séparément. | Python/PyTorch et inférence villa / `koine_machines`. L'auteur indique `--no-compile` sous Windows. Commencer sur une petite fenêtre, batch 1 et pic VRAM mesuré. | AUC 0,930 contre 0,897 pour V2 sur PHerc0139 w047. Sur le papyrus vierge PHerc0139 w053, 5,5 % contre 9,2 % pour V2 et 57,6 % pour Hecate, au rappel fixé par l'auteur. | **P0** · première référence publique. [Dépôt](https://github.com/DomRusso2/reader-v3/tree/4a9f1c633d2f30d9b522922ec1cb52c082013183) · [Poids](https://huggingface.co/domenicor046/reader-v3) |
| **Reader V4** · candidat encre | Aucun code, checkpoint, carte de modèle ou release publique correspondant trouvé. | Besoins inconnus. | Delta d'AUC rapporté sur Discord, sans reproduction. | **Veille** · reprendre les mêmes pixels et contrôles si un checkpoint apparaît. |
| **VC3D / GrowPatch** · inspection, croissance locale, correction et rendu | Code disponible dans `villa/volume-cartographer`. VC3D sous GPL-3.0. Données et poids en amont sous leurs propres termes. | Croissance depuis une graine et une prédiction surfacique. Des correctifs Windows existent. La lecture des blocs, le renderer et les guides nécessaires dominent le coût selon la fenêtre. | PHerc. 306B a utilisé GrowPatch sur m7 avec retouche au bout d'un patch. Pas de mesure transversale de qualité publiée dans cette annonce. | **P0** · utiliser l'exécutable et les exports tifxyz. [Retour officiel](https://scrollprize.org/from_ash_to_text) · [Licence VC3D](https://github.com/ScrollPrize/villa/blob/main/volume-cartographer/LICENSE) |
| **Spiral Fitting** · ajustement global déformable | Code public dans `villa/spiral-fitting`, dépôt racine MIT, détails par composant à vérifier. Contraintes et guides publics selon le rouleau. | PyTorch et extension C++ de villa. Linux CUDA et voie Windows documentée avec Triton communautaire, optimisations 12 Go signalées. Un ensemble d'entrées Paris. 4 publié représente ~49,6 Go. | Fit de 130 tours sur Paris. 4 dans le tutoriel. Sorties par tour, contraintes satisfaites et variante avec patches vérifiés. | **P1** · référence géométrique et génération de témoins pour les coutures. [Tutoriel](https://scrollprize.org/tutorial_spiral) · [Données](https://scrollprize.org/data_datasets) · [Prix de progrès](https://scrollprize.org/winners) |
| **HerculeX** · détecteur CT, graphe des tours, mise à plat et Reader V3 | Code MIT, version `0.1.0`, tests publics dont C/CUDA et solveur. Scans et Reader sous licences distinctes. | Apple Silicon ou Linux NVIDIA, Python 3.11. Environ 40 Go de fichiers par rouleau et plusieurs centaines de Go de trafic complet annoncés. L'environnement Windows du projet demande une validation séparée. | 81–86 % des longueurs voisines à ±10 % de la cible selon l'auteur. PHerc0826 sur M1 Pro 16 Go, 1,7 h jusqu'à la disposition et 1,6 h pour les cartes. L'identité des tours reste incertaine sur les rouleaux sans maillage de référence. | **P1** · tester le détecteur de nœuds et le contrôle de coutures sur un cube. [Code épinglé](https://github.com/adambetka2/HerculeX/tree/9f59e9669a2273e3bed6bbc39b519604f2a675b3) |
| **ScrollFiesta** · maillage surfacique par cubes, assemblage et dépliage | Dépôt C/C++ public, code propre MIT. Conditions séparées pour GCoptimization et Triangle. | CPU par défaut, outils Windows/Visual Studio et Linux, projection MLS accélérable par CubeCL CUDA/HIP. Prédiction de surface Zarr et exports intermédiaires sur disque. Taille dépendante du jeu. | Le Challenge signale des surfaces propres sur de grandes régions. Comparer les métriques d'assemblage sur le même cube avant de généraliser. | **P2** · comparer coutures et export tifxyz sur des zones où GrowPatch dérive. [Pipeline](https://github.com/Hob3rMallow/scrollfiesta_public) · [Dépendances](https://github.com/Hob3rMallow/scrollfiesta_public/blob/main/THIRD_PARTY_LICENSES.md) |
| **PHerc. 211 / Studio** · U-Net résiduel 3D, 16 plans natifs, apprentissage multi-rouleaux | Code MIT, checkpoints et données publiés séparément sous CC BY-NC 4.0 selon l'annonce. | Reproduction intégrale publiée pour Linux, **96 Go VRAM**, **128 Go RAM**, **200 Go disque libre** et **~120 Go de téléchargements**. À tester en inférence sur un extrait avant d'estimer le coût local. | 11 lettres annoncées, PHerc. 211 exclu de l'entraînement dans le dépôt de reproduction. | **P1** · reprendre l'ablation sur la sélection des données, tester les poids sur fenêtre. [Annonce](https://scrollprize.substack.com/p/first-letters-emerge-from-pherc-211) · [Code](https://github.com/priyankaranke/vesuvius-studio-multiscroll-cpt) |
| **PHerc. 306B / TRACE v3B × A-hn** · consensus multi-modèles | Code MIT. Poids, données et cartes dérivées du scan sous CC BY-NC 4.0. | La publication indique ~6 Go d'artefacts de poids, ~17 Go de données/artefacts et ~0,4 Go pour le dépôt de soumission. Test local par cartes recadrées, VRAM à vérifier pour l'inférence. | Sur le texte connu PHerc. 0841, AUC 0,874, AP 0,731 et 6,1 % de faux positifs à 80 % de rappel sur l'axe des traits, contre 8,5 % pour TRACE seul et 12,1 % pour v8-in. | **P0** · tester le consensus, à rappel égal. [Code et mesures](https://github.com/SirProdigle/pherc0306b-first-letters) |
| **PHerc. 343 / Nieuwlaar** · géométrie ajustée, ensemble et balayage de profondeur | Script, maillage, images et liens poids publics. Code MIT, maillages et images CC BY-NC 4.0. | Reproduction publiée Linux NVIDIA **24 Go VRAM**, VC3D AppImage et lecture CT niveau 0 locale ou distante. 31 profondeurs et deux phases de tuilage dans la méthode complète. | Seuil des 10 caractères atteint sur la ligne la plus lisible selon l'annonce. Pas de mesure d'encre comparable au test 306B. | **P1** · reprendre une petite ablation de profondeur et de couture. [Annonce](https://scrollprize.substack.com/p/50k-first-letters-prize-awarded-for) · [Code et données](https://github.com/Nieuwlaar/pherc343-first-letters) |
| **PHerc. 1667** · chaîne complète de référence | Prépublication, code et données accessibles. Vérifier la licence de chaque volume, annotation et illustration. | Travail d'échelle rouleau. Les petits extraits suffisent à vérifier les échanges de formats. | Environ 1,4 m et 22 colonnes de la partie conservée, lecture continue avec des lacunes du support. | **P2** · étudier les sorties et les critères de reconstruction. [Annonce](https://scrollprize.org/firstscroll) · [Prépublication](https://arxiv.org/abs/2606.29085) · [Termes des données](https://scrollprize.org/data) |

### Reader et fidélité au signal

L'architecture de Reader V3 conserve celle de Reader V2, un stem 3D local et un U-Net 2D
(`Local3DStem2DUNet` dans villa). La configuration publique fixe une fenêtre de **17 plans**
et une tuile de **384 × 384** au dernier stade. Le préentraînement repris de V2 a continué sur
256 px pendant 30 000 itérations puis 384 px pendant 20 000 itérations, avec les mêmes données
et labels selon l'auteur. Le moteur accepte un volume de surface OME-Zarr en couches normales
et produit une carte 8 bits. Les niveaux de gris sont des scores relatifs depuis un entraînement
avec lissage des labels. Le repère du recto et les paramètres d'affichage doivent être fixés
indépendamment de la lisibilité de la zone testée. [Recette et résultats Reader V3](https://github.com/DomRusso2/reader-v3/tree/4a9f1c633d2f30d9b522922ec1cb52c082013183)
· [Implémentations de l'architecture](https://docs.rs/inkrs/latest/inkrs/)

La recette de l'auteur pointe vers la branche `merge-ink-pipelines` de villa, relevée à
`47a9c37f6f8e99afdab47bb46ad425aa726f5dc0`. Le SHA-256 annoncé dans les métadonnées HF pour
`reader-v3.pth` est `ea405417450abd8ace1b8ff79ebce3adb646c5e48ab95da46844d77efe984d8a`.
Le pilote devra vérifier ce hash sur le fichier chargé. [Branche villa](https://github.com/ScrollPrize/villa/tree/47a9c37f6f8e99afdab47bb46ad425aa726f5dc0)
· [Métadonnées du checkpoint](https://huggingface.co/api/models/domenicor046/reader-v3/tree/main)

Le relevé public de vitesse donne 13,96 s (V3) et 20,66 s (V2) sur le même extrait de 5,98 Mpix,
24 couches et un seul ordre des couches, sur RTX 5070 Ti.
Sur les régions inconnues 0841 et 1447, le taux de fond marqué à 80 % de rappel est **30,4 %**
pour V3 selon l'auteur. La variation entre essais justifie les résultats par rouleau et par
strate. Les essais de Russo sur les ouvertures, les coupures remplies avec du papyrus vierge
et l'inversion des couches donnent des contrôles à reproduire. Une inversion mesure une
sensibilité à l'orientation. Une perturbation de la profondeur, un second rendu et les coupes CT
permettent aussi de vérifier la stabilité locale. La recherche du 19 novembre a porté sur les
répertoires GitHub de l'auteur, sa liste de modèles Hugging Face et la recherche publique sous
Reader V4, KLAVIS et Domenico Russo. [Temps publiés](https://github.com/DomRusso2/reader-v3/blob/main/results/speed.json)
· [Liste GitHub](https://github.com/DomRusso2?tab=repositories)
· [Profil HF](https://huggingface.co/domenicor046)

Tester d'abord le rendu à plusieurs profondeurs prédéfinies, le recouvrement des tuiles et la
fusion Hann pour diminuer les coutures d'inférence. Comparer ensuite une augmentation miroir
inversée au retour et un filtre faible de la carte, avec masques et seuils gelés. Une fermeture
ou un amincissement morphologique exige un test sur anneaux, ouvertures et traits interrompus.
Conserver la carte brute et mesurer chaque transformation avec la même référence annotée.
L'inpainting, la vectorisation générative et les patrons de lettres ne font pas partie de cette
étape de détection.

### HerculeX et validation des coutures

Le tenseur de structure et le profil CT dans chaque cellule de huit voxels donnent des nœuds
orientés. Les arêtes de voisinage restent sur la feuille et les rayons normaux donnent des
contraintes entre tours. Une coupe minimale oriente les normales. Pour des indices entiers de
tour `f`, le solveur minimise la somme pondérée `|f[b] - f[a] - k|`, via un flot à coût minimum.
Les votes répétés sélectionnent les arêtes stables. Les pièces sont paramétrées localement,
raccordées entre unités puis placées dans un repère global. Le pipeline prélève 31 plans,
identifie la face par les fibres et passe une fenêtre de 17 plans à Reader V3. Le certificat
d'optimalité porte sur l'objectif et les contraintes fournis. Des arêtes erronées ou une
contrainte manquante peuvent toujours relier deux tours différents. [Détection](https://github.com/adambetka2/HerculeX/tree/main/unwrapping/detection)
· [Solveur et garde contre les plis](https://github.com/adambetka2/HerculeX/tree/main/unwrapping/level)
· [Assemblage](https://github.com/adambetka2/HerculeX/tree/main/unwrapping/layout)

Les chiffres publics distinguent l'aire étalée de celle en mosaïques d'au moins 4 cm². Sur huit
rouleaux, **39 428 / 69 290 cm²**, soit 56,9 %, de l'aire étalée se trouve dans ces mosaïques.
Le dénominateur nécessaire pour mesurer la couverture est l'aire recto réelle, avec détection des
recouvrements et doubles comptages. L'annonce Discord de 50 à 70 % de couverture reste donc non
vérifiée. Le dépôt publie du code C, des kernels et des tests, mais aucune validation indépendante
des tours sur ces huit rouleaux n'a été trouvée. [Résultats HerculeX](https://github.com/adambetka2/HerculeX#results)

Composants à évaluer à la frontière `tifxyz` existante, dans cet ordre.

1. Export local par pièce et journal des raccords avec identifiants de nœuds, unités et tours.
2. Score de raccordement sur distance médiane/p95 en µm, angle des normales, continuité des
   fibres, recouvrement et auto-intersections. Comparer aux mêmes coupes CT et aux maillages
   témoins VC3D. Faire vérifier les coutures aveuglément par deux lecteurs de coupes.
3. Détecteur de nœuds pour proposer un recalage local là où la carte T10 manque de signal.
   Comparer dérive et changements de tour séparément. Le solveur global devient pertinent
   seulement si les arêtes locales et les raccords sont suffisamment fiables.

La version auditée fixe Python 3.11 et la voie d'inférence requiert Zarr 2 et PyTorch. Le projet
emploie Zarr 3 et le code natif CUDA d'HerculeX utilise un hôte C/GCC et NVRTC fourni par les
roues PyTorch, avec OpenMP côté calcul CPU. Tester dans un environnement dédié WSL2/Linux.
Le test `test_cuda_unwrap_e2e.py` simule les jobs. Le test `test_sheet_nodes_golden.py` compare
les nœuds de la voie GPU à la référence C sur une spirale synthétique. Sous WSL2, vérifier
`nvidia-smi` et `torch.cuda.is_available()` dans une distribution de travail puis lancer ce
test avant d'essayer un scan. Le pilote GPU est fourni par l'hôte Windows. [Dépendances HerculeX](https://github.com/adambetka2/HerculeX/blob/main/pyproject.toml)
· [Test C/GPU](https://github.com/adambetka2/HerculeX/blob/main/tests/test_sheet_nodes_golden.py)
· [Guide CUDA WSL de NVIDIA](https://docs.nvidia.com/cuda/wsl-user-guide/index.html)

#### Pilote reproductible sur PHerc. 0814

Le lecteur Data Explorer a extrait, au niveau 0, le cube de **128³ voxels à 9,362 µm** autour du
point `[44, 140]` de la grille du segment `20260226110425`, volume `20250804134230`. Coordonnées
CT `(z,y,x)`, bornes supérieures exclues. **11,35 s**, catalogue et grille compris, avec le
cache de blocs désactivé. Huit blocs, budget de décodage de 16 Mio, cube résultant de 2 Mio
en `uint8`. Les percentiles P1/P50/P99 sont 14/76/211. Le SHA-256 des voxels en ordre C est
`c392fe848132b6418d08cc18ac79dd08586bc30a566b217cbe0ad2e5ed607428`.
[Contrôle de la dérive sur le segment](validation/T10-carte-alignement.md#dérive-naturelle-sur-pherc0814)
· [Source et conditions d'utilisation des scans](https://scrollprize.org/data)

```python
import hashlib
import numpy as np
from vesuvius_data_explorer.core.volume import open_levels

uri = ("s3://vesuvius-challenge-open-data/PHerc0814/volumes/"
       "20250804134230-9.362um-1.2m-113keV-masked.zarr")
arrays, _ = open_levels(uri)
roi = np.asarray(arrays[0][3079:3207, 2117:2245, 2523:2651])
assert roi.shape == (128, 128, 128) and roi.dtype == np.uint8
assert hashlib.sha256(roi.tobytes()).hexdigest() == (
    "c392fe848132b6418d08cc18ac79dd08586bc30a566b217cbe0ad2e5ed607428"
)
```

1. Dans le clone HerculeX épinglé, reprendre l'adaptateur `write_store` du test golden.
   Comparer `detect_store(..., device="cpu")` et `device="gpu"` sur le même cube, avec le même
   budget et les mêmes options. Conserver temps, pic RAM/VRAM, comptage, médiane et p95 des
   écarts de nœud dans les cellules communes, ainsi que les différences de normales.
   Réintégrer l'origine `(3079, 2117, 2523)` avant de superposer les nœuds au scan et au tifxyz.
2. Faire annoter les feuilles coupées par quelques transects CT, dont la tuile T10 de dérive
   connue. Évaluer le rappel local des feuilles, les faux raccords entre feuilles et les
   nœuds sans référence. Avec un second cube contigu et un recouvrement de 32 voxels, comparer
   les raccords dans la région commune et mesurer distorsion, intersections et sauts de tour
   après raccord. Réserver une autre zone pour contrôler les seuils ainsi établis.
3. Le numéro absolu du tour et le pourcentage de recto couvert exigent des références
   plus étendues et restent indéterminés sur ce cube. Les essais HerculeX proposés
   n'ont pas été exécutés.

## C. Annonces officielles et expériences à reprendre

### PHerc. 211 — 15 novembre

Le prix de 50 000 $ correspond à 11 lettres lisibles. Studio applique un U-Net résiduel 3D à
16 plans natifs à ~9 µm. Le DINO 3D auto-supervisé, appris sur CT en résolution native, sert à
classer les rouleaux par distance cosinus. PHerc0009B et PHerc0841 figurent dans les trois plus
proches parmi les rouleaux avec encre sur les 23 cibles non lues de l'expérience rapportée.
PHerc0814 figure souvent quatrième ou cinquième. L'auteur a recalé les prédictions d'encre
et annotations d'environ 2 µm de ces trois sources sur les surfaces ~9 µm, puis corrigé les
labels à la main. La phase multi-rouleaux ajoute 12 groupes avec rejeu des trois sources,
puis un court ajustement pour les traits faibles. PHerc. 211 est resté hors entraînement.
Le segment gagnant provient d'un ajustement spiralé, de raccords entre tours, de retouches
VC3D et d'une croissance guidée par DinoVol. [Annonce et entretien](https://scrollprize.substack.com/p/first-letters-emerge-from-pherc-211)
· [Recette et checkpoints](https://github.com/priyankaranke/vesuvius-studio-multiscroll-cpt)

Reprendre la sélection avant tout entraînement coûteux. Comparer, à taille d'échantillon et
volume d'annotation égaux, trois politiques **tirage stratifié**, **proximité de protocole**
(µm, énergie, reconstruction) et **proximité DINO**. Échantillonner les embeddings dans
plusieurs zones du rouleau pour éviter un classement dominé par un anneau ou une seule couche.
Geler la sélection avant de voir les labels de test, puis retirer un rouleau complet à chaque
évaluation. Contrôler aussi les acquisitions, le même fragment sous un autre nom, et la
provenance des enseignants. Pour le transfert haute → basse résolution sur les sources
autorisées, conserver les transformations 3D et mesurer l'erreur de reprojection sur des
repères indépendants. Écarter les pixels où le recalage est incertain du dénominateur de vérité.
Pour une soumission Grand Prize, exclure les dérivés des scans plus fins du rouleau soumis.

### PHerc. 306B — 2 novembre

Warner et Bodill ont choisi une zone à partir de cartes issues des tours du spiral fitter.
Le segment GrowPatch utilise la prédiction m7, puis la surface a été corrigée dans une zone
de dérive avant le rendu. A-hn est une moyenne de trois fine-tunings v8-in de 600 pas,
mélangeant annotations PHerc. 1447 et pseudo-labels multi-enseignants de cinq autres surfaces
de PHerc. 306B, avec une pénalité pour les réponses sur papyrus vierge. Le rendu final est le
produit TRACE v3B × A-hn. L'exclusion de la région soumise et le fait qu'un enseignant fasse
aussi partie du consensus imposent des contrôles complémentaires de contamination et
d'erreurs corrélées. Comparer d'abord les deux modèles seuls, la moyenne, le minimum et le
produit. Abaisser le seuil du produit sur le jeu de développement uniquement pour atteindre
le même rappel cible, puis geler le seuil avant l'évaluation. [Annonce](https://scrollprize.substack.com/p/writing-seen-in-pherc-306b-for-the)
· [Soumission et contrôles](https://github.com/SirProdigle/pherc0306b-first-letters)
· [Données et zone d'exclusion](https://huggingface.co/datasets/Prodigle/pherc0306b-first-letters)

Le rappel de 80 % dans cette comparaison est mesuré sur l'axe des traits. Le même fichier de
résultats montre un contre-exemple sur le témoin `f9h`, où TRACE donne 2,42 % de faux positifs
contre 3,14 % pour le produit au rappel spécifié. Pour PHerc0841, la publication des résultats
fournit les métriques et des chemins de travail, sans les cartes sources dans le dossier
`known_text`. Une reproduction indépendante exige de recalculer les cartes sur les rendus
et masques correspondants. [Résultats bruts et définition du rappel](https://huggingface.co/datasets/Prodigle/pherc0306b-first-letters/blob/main/results/known_text/known_product.json)

### PHerc. 343 — 8 octobre

Erwin Nieuwlaar a travaillé sur le scan 8,64 µm, avec son propre axe, puis projection des
windings sur m7, aplatissement Lasagna et raccord de w047/w048 à la couture angulaire.
VC3D a rendu 66 couches. Quatre modèles (dense_native, ink_9um seeds 42/43 et Hecate)
ont été comparés sur 31 décalages. Deux phases de tuilage réduisent l'effet du raccord.
L'image publiée combine les scores standardisés à un décalage de +1 voxel. Les scripts,
maillages et images permettent d'étudier l'effet de l'orientation, du décalage et du tuilage.
La zone U08 de Reader V3 est une démonstration distincte de la zone du prix. [Annonce officielle](https://scrollprize.substack.com/p/50k-first-letters-prize-awarded-for)
· [Reproduction et maillages](https://github.com/Nieuwlaar/pherc343-first-letters)
· [Démonstration Reader V3](https://github.com/DomRusso2/reader-v3#real-first-letters-ink-found-in-a-real-search-pherc0343)

### PHerc. 1667 — 25 juin

La chaîne de référence relie microtomographie à contraste de phase sur BM18 à l'ESRF,
géométrie des tours, aplatissement, prédiction, montage en
colonnes et revue papyrologique. La lecture couvre le noyau préservé, avec les lacunes physiques
documentées. Les données et le code publics sont utiles pour tester les conventions `tifxyz`,
les raccords et la pagination. Le papier décrit aussi, pour PHerc. Paris. 4, la confirmation
indépendante par imagerie plus fine de traits lus auparavant. Le contraste entre ces deux cas
motive la présentation d'indices CT, de résultats du modèle et de lectures évaluées avec leurs
provenances. [Annonce](https://scrollprize.org/firstscroll) · [Prépublication](https://arxiv.org/abs/2606.29085)

## D. Prototype et validation scientifique

`vesuvius-qc encre` reçoit deux cartes de score TIFF 2D et un masque de référence dans un
repère commun. Les cartes gauche et droite, leur moyenne, leur minimum et leur produit sont
évalués sur les mêmes pixels. Le produit est un score de concordance. Même pour des cartes
allant de 0 à 1, il dépend de leur calibration et des erreurs que les modèles ont en commun.
Le rapport fixe les seuils, enregistre les empreintes SHA-256, l'identité des données et des
poids déclarée dans le manifeste, les comptes par strate, l'AUC ROC, la précision, le
rappel, le taux de faux positifs et des mesures de forme par boîte annotée.

### Reproduction locale

```powershell
.\.venv\Scripts\python.exe docs/examples/generate_ink_example.py data/encre-demo
.\.venv\Scripts\vesuvius-qc.exe encre data/encre-demo/manifest.toml -o data/encre-resultat
```

Le générateur crée deux fenêtres de 72 × 104 pixels et recopie le [manifeste TOML](examples/ink_benchmark.toml).
La commande écrit dans un nouveau dossier. Code de sortie 0 quand le calcul aboutit,
2 si une entrée ou une sortie est invalide. L'exemple a pris environ **1,7 s** sur Windows,
chargement Python compris, sur CPU. Le [rapport JSON](validation/ink-synthetic/rapport.json),
la [planche de l'anneau](validation/ink-synthetic/comparaison-001.png) et la
[planche de l'arc](validation/ink-synthetic/comparaison-002.png) ont été produits par la CLI.
Les fenêtres simulent un trait incomplet, une zone vierge, une erreur de géométrie, un
artefact partagé et une zone d'interprétation incertaine.

La suite Windows a terminé avec **288 tests réussis**, un ignoré et huit exclus par le filtre
réseau habituel. Les huit tests ajoutés couvrent notamment les métriques et leurs cas limites,
l'exclusion des pixels inconnus, la topologie, les TIFF incompatibles et la reproductibilité
du rapport. Une génération complète dans un autre dossier a produit les mêmes empreintes
pour le JSON et les deux PNG.

| Score | Seuil | AUC ROC | Précision | Rappel | Faux positifs |
|---|---:|---:|---:|---:|---:|
| Carte gauche | 0,50 | 0,9574 | 27,49 % | 100,00 % | 10,16 % |
| Carte droite | 0,50 | 0,9698 | 51,96 % | 94,26 % | 3,35 % |
| Moyenne | 0,50 | 0,9882 | 46,14 % | 96,93 % | 4,36 % |
| Minimum | 0,50 | 0,9846 | 59,76 % | 94,26 % | 2,44 % |
| Produit | 0,30 | 0,9885 | 59,54 % | 94,26 % | 2,46 % |

Les moyennes donnent le même poids à chaque rouleau simulé. Le produit ramène les faux
positifs de 120 à 24 par fenêtre de papyrus vierge, contre 84 pour la carte droite.
Sur l'artefact commun, le produit marque toujours 140 pixels par fenêtre. Dans la boîte de
l'anneau, le nombre de trous passe de 30 à 1 pour un trou annoté et le F1 de contour passe de
0,678 à 0,993, avec trois composantes prédites pour une annotée. Le produit perd 28 des
244 pixels d'encre de l'arc et le minimum obtient ici un taux de faux positifs légèrement
plus faible. Les seuils sont ceux de la démonstration, sans ajustement à rappel égal entre
toutes les méthodes et sans estimation d'incertitude sur deux fenêtres.

### Format d'entrée et interprétation

- `dataset_kind` vaut `synthetic` ou `real`. Chaque entrée `[[crops]]` indique rouleau,
  volume, surface, provenance et résolution effective du rendu. Pour le réel, renseigner
  aussi dans la provenance le repère du recadrage, la révision du maillage, l'origine
  du masque et les paramètres du renderer, ou référencer un manifeste qui les contient.
- Une image TIFF locale monochrome `YX` par entrée. Même dimensions, orientation, échelle et
  origine pour tous les plans. Le code vérifie les dimensions. La correspondance géométrique
  doit être vérifiée sur le maillage et les repères CT. Limite par défaut de 1 048 576 pixels
  par image. Le facteur `scale` vaut par exemple 255 pour les scores Reader 8 bits et 1 pour
  des scores flottants dans [0, 1]. Pas d'étirement par fenêtre pour les mesures.
- Le masque entier `labels` utilise 0 pour le fond annoté, 1 pour l'encre annotée, 255 pour
  l'inconnu. Convertir explicitement les étiquettes externes avant usage. Un fond sombre
  et un pixel jamais examiné ont des conséquences différentes sur les métriques.
- Le TIFF optionnel `strata` code 0 surface standard, 1 papyrus vierge, 2 artefact du scan,
  3 erreur géométrique et 4 lecture incertaine. Les strates 2 et 3 ne prétendent pas fournir
  un label d'encre. L'annotateur renseigne 0/1 uniquement si le signal le justifie. La
  strate 4 exige le label 255. Sur les pixels inconnus, seuls leurs nombres et leurs
  franchissements de seuil sont comptés.
- Les rectangles `glyphs` de coordonnées `[x0,y0,x1,y1]` à bords supérieurs exclus sont
  facultatifs. Chaque boîte est entièrement annotée et contient des traits. Le F1 de
  contour utilise une distance bidirectionnelle avec tolérance en pixels, par défaut un
  pixel. On mesure aussi les composantes connexes et les trous pour repérer fragmentation
  et fermeture accidentelle. Comparer à résolution effective égale ou justifier la
  tolérance physique. Ces mesures donnent la cohérence géométrique des traits.
- Le plan `ct` facultatif permet de vérifier visuellement l'alignement. Il ne change aucun
  score. Les cartes de la planche partagent l'échelle de rendu [0, 1]. Les erreurs pixel
  et les mesures utilisent leurs seuils du manifeste.
- Une métrique indéfinie donne `null` dans le JSON, par exemple l'AUC d'un contrôle
  exclusivement négatif. Les moyennes écartent les valeurs indéfinies et indiquent
  le nombre de rouleaux contributeurs. Pour comparer les méthodes, consulter les
  dénominateurs, métriques par fenêtre et comptes absolus de faux positifs.

### Passage aux données réelles

1. Constituer des ensembles de réglage et d'évaluation avec des rouleaux disjoints pour la
   mesure inter-rouleaux et des régions 3D disjointes pour chaque modèle, y compris les
   enseignants de pseudo-labels. Figer volumes, masques, checkpoints, orientations et seuils.
   Utiliser les régions publiques présentant du texte connu, comme w058 de PHerc1447 pour
   Reader V3, uniquement si elles restent indépendantes des poids et de nos réglages.
   PHerc0841 est une source de développement de Studio. Les tests entre Reader et Studio
   exigent donc un autre témoin commun. Documenter tout jeu déjà utilisé pour choisir un modèle.
   [Plan de comparaison Reader V3](https://github.com/DomRusso2/reader-v3#head-to-head)
   · [Entraînement Studio](https://github.com/priyankaranke/vesuvius-studio-multiscroll-cpt)
2. Faire annoter, à l'aveugle des cartes candidates, les traits exploitables, le papyrus vierge
   et les artefacts comme les fibres, fissures et bandes. Vérifier les erreurs géométriques sur
   les coupes, les normales et un second mesh. Marquer comme incertains les traits plausibles
   sans accord. Conserver les désaccords et l'identité des annotateurs dans le registre.
3. Comparer profondeur nominale, variations de quelques voxels et normales inversées sur les
   mêmes fenêtres. Insérer une coupure locale de largeur connue à partir d'un contrôle sans
   encre de la même feuille et vérifier qu'un modèle ne comble pas la coupure. Garder un contrôle
   intact. Permuter les couches dans un essai séparé, car un résultat dégradé hors distribution
   ne démontre pas à lui seul la présence d'encre. Rechercher la continuité des fibres et des
   traits à travers les coutures, puis vérifier en coupe.
4. Sélectionner des seuils à rappel cible prédéfini sur développement et les figer dans le TOML.
   Sur test, publier précision, taux de faux positifs à rappel observé, différences appariées,
   AUC, F1 de contour, fragmentation et trous. Calculer des intervalles avec rééchantillonnage
   des rouleaux ou des surfaces selon le plan de collecte. Éviter le rééchantillonnage de
   pixels adjacents comme s'ils étaient indépendants. Soumettre séparément les lectures à une
   expertise papyrologique à l'aveugle.

## E. Assistance paléographique facultative

La planche intitulée **Greek Literary Alphabets (No. 2)** a été retrouvée au feuillet numérique
`n162` de l'édition de 1912 d'**Edward Maunde Thompson**, *An Introduction to Greek and Latin
Palaeography*. Le fac-similé montre notamment les colonnes Philodème, Métrodore et Bacchylide.
Le fichier vu sur Discord n'était pas joint, ce qui empêche d'attribuer sa reproduction
numérique exacte. HathiTrust classe son édition d'origine dans le domaine public et signale
que Google demande de ne pas redistribuer ses images et son OCR. Wellcome affiche « In copyright »
pour sa propre notice numérique. Le rapport référence la planche d'Internet Archive. Avant
d'intégrer une image au module, relever les droits de la numérisation effectivement choisie.
[Planche n° 2](https://archive.org/details/introductiontogr00thomuoft/page/n162/mode/1up)
· [Image de contrôle](https://archive.org/download/introductiontogr00thomuoft/page/n162/size/800)
· [Édition HathiTrust](https://hdl.handle.net/2027/mdp.39015011050633)
· [Notice Wellcome](https://identity.wellcomecollection.org/works/mt6artgv)

Un module de revue pourrait enregistrer trois champs séparés pour chaque région.

1. **Traits observés.** Points et segments visibles, orientation, connexions, lacunes et
   extraits CT ou cartes qui les étayent, avec coordonnées et versions.
2. **Hypothèses de glyphes.** Références datées et sourcées en vis-à-vis, avec critères
   observables. Pour Μ, Ν et ΑΙ, relever par exemple le nombre de fûts visibles, la position
   et le sens des diagonales, une éventuelle traverse, les attaches aux traits voisins et
   l'espacement qui pourrait indiquer deux caractères. Prendre en compte le sens de lecture,
   l'échelle et les parties absentes. Reporter « indéterminé », « possible » ou « probable »
   selon les traits et l'accord entre réviseurs, sans convertir cette échelle en probabilité
   numérique sans calibration.
3. **Interprétation.** Lectures linguistiques éventuelles, proposées dans une étape distincte
   par un spécialiste et reliées aux observations qui les soutiennent. Le module d'annotation
   ne doit jamais transformer une hypothèse de lecture en label d'encre.

## F. Position dans la compétition

Règles publiques consultées le **19 novembre 2026**. Échéance des deux voies le
**25 juin 2027 à 23 h 59 heure du Pacifique**, soit le **26 juin à 8 h 59 à Paris**.
Vérifier la liste par **identifiant du volume** au moment de choisir une cible et juste
avant de soumettre. [Règles First Letters et Grand Prize](https://scrollprize.org/prizes)

| | A · First Letters | B · Grand Prize 2027 |
|---|---|---|
| Enjeu et admissibilité | 50 000 $ par rouleau, jusqu'à sept prix supplémentaires et 19 volumes admissibles affichés. Exemples admissibles à cette date, PHerc0800 `20250521135224` et PHerc0826 `20250821151701`. | 800 000 $ pour la première place et 13 volumes affichés. PHerc0211 `20250821151803`, PHerc0800 et PHerc0826 y figurent. |
| Géométrie et lisibilité | Au moins 10 lettres lisibles dans une seule zone de 4 cm². Maillage tifxyz local à faible distorsion, dimensions et barre d'échelle, rendu issu du CT et du maillage. Validation technique et papyrologique. | 100 % du recto à dérouler, exception prévue pour les fragments externes détachés sous 10 % de l'aire totale. Maillages tifxyz à l'échelle de la colonne, ordre des tours et intégration VC3D. Au moins 70 % des caractères conservés de chaque colonne comptée doivent être lisibles individuellement. |
| Effort humain et calcul | Contrôles locaux, préparation du masque, temps d'annotation et revue indépendante à prévoir. Les critères de la section First Letters consultée demandent une méthodologie et des contrôles documentés. | Automatisation du déroulement avec au plus 8 h d'apport humain documenté. Suivre couverture, contraintes, coutures, lisibilité et ressources par étape. |
| Reproductibilité et droits | Publier code, poids, données et résultats après le prix. Documenter témoins, absence de recouvrement entraînement/prédiction et mesures contre les faux positifs. | Pipeline reproductible et publication sous licence permissive. Respecter les licences des composants et données. Geler les graines, publier les journaux, ainsi que jeux et checkpoints de pseudo-étiquetage à chaque stade sous CC BY-NC 4.0. Les dérivés d'un scan plus fin du rouleau soumis sont exclus. |
| Décision | **Voie prioritaire**. GrowPatch + QC + inférence sur fenêtre et validation indépendante correspondent à la géométrie et au matériel disponibles. | **Voie de recherche**. La couverture fiable, l'identité des tours, les coutures et le contrôle de lisibilité à l'échelle des colonnes restent à établir. |

PHerc. 211 est absent de la liste First Letters après son prix. PHerc. 306B, 343 et 1667
ne figurent sur aucune des deux listes consultées. Ces cas servent à comprendre ou vérifier
les méthodes selon la provenance des poids. Les deux prix soumettent les découvertes à une
revue avant publication. [Listes et modalités officielles](https://scrollprize.org/prizes)

## G. Passage de relais à Claude Opus

| Priorité | Livrable suivant | Critère de vérification |
|---|---|---|
| **P0** | Inventorier deux checkpoints et un jeu de petites fenêtres indépendantes avec les licences, splits, contrôles négatifs et coordonnées CT. | Manifeste versionné, aucune intersection avec des données d'entraînement ou de réglage. |
| **P0** | Rendre la même surface pour Reader V3 et un second modèle public de famille ou d'entraînement suffisamment différent. Mesurer sur la RTX le pic VRAM à batch 1 et le temps par Mpix. | Deux TIFF précisément superposables, profondeur et orientation fixées, tests par strate et seuils gelés. |
| **P0** | Mesurer le consensus sur réel et faire relire les cas discordants. | Delta apparié de taux de faux positifs au rappel observé, contrôle papyrus vierge, stabilité en profondeur et conservation des traits faibles. |
| **P1** | Exécuter HerculeX C/CUDA sur la spirale de référence puis le cube PHerc0814. Comparer avec VC3D/T10 sur les mêmes coupes. | Écarts C/GPU quantifiés, temps et mémoire, rapport de topologie et de raccordement établi sur témoins. |
| **P1** | Essai inter-rouleaux en trois politiques de sélection pour Studio. | Même budget d'annotation, résultats sur rouleaux tenus à l'écart, provenance des labels et transferts enregistrée. |
| **P2** | Examiner ScrollFiesta et les sorties de PHerc1667 pour les coutures et la couverture. Ouvrir la revue paléographique facultative quand le fac-similé et ses droits sont identifiés. | Géométrie comparée sur les mêmes régions. Les hypothèses de lettres restent traçables jusqu'aux traits réellement observés. |

Compte rendu à transmettre à Claude. La commande d'évaluation accepte les cartes sorties
d'un moteur externe. L'extraction d'un cube CT réel est démontrée.
Les performances réelles des modèles, l'exécution HerculeX sous WSL2 et la provenance exacte
de l'image Discord restent à vérifier. Aucune lecture nouvelle n'est revendiquée.
