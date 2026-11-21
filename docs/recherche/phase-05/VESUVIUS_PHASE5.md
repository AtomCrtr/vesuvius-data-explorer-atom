# Phase 5 · Validation de l’encre et expérimentation

L’audit PHerc0500P2 rattache les deux cartes au même rendu historique
et établit leurs réglages de profondeur opposés. Le recouvrement
à 50 % est de 0,477 et les top 1 % sont disjoints. Il manque encore
une référence d’encre sur cette grille, la face anatomique, les
empreintes des poids utilisés et une calibration commune.
[Provenance](../encre/INK_PROVENANCE_AUDIT.md) · [Analyse des seuils](../encre/MODEL_CONSENSUS_ANALYSIS.md)

## Expérience réalisée sur RTX 4080 Laptop

Le prototype relit le recadrage public 384 × 384, compare les deux
modèles et leur intersection et union sur 19 seuils, puis affiche la
concordance, le désaccord et l’incertitude dans napari. Il utilise
NumPy sur CPU pour les statistiques et la RTX pour le rendu OpenGL.
Le traitement ne charge aucun poids et ne transfère aucun voxel
depuis le réseau pendant la mesure.

| Mesure sur Windows natif | Valeur |
|---|---:|
| Matériel reconnu par OpenGL | NVIDIA GeForce RTX 4080 Laptop GPU |
| Pilote / VRAM annoncée | 616.64 / 12 282 Mio |
| Calcul des 19 seuils, histogrammes et rangs, 7 répétitions | 14,3 ms médiane, 15,9 ms p95 |
| RSS Python avant/après la série CPU | 100,8 / 101,2 Mio |
| Ouverture du manifeste dans napari 0.10 / Qt 6.12 | 441 ms |
| Première couche de consensus, jusqu’à la capture | 142 ms |
| Bascules suivantes, jusqu’à la capture | 43–56 ms |
| Timer Qt de 8 ms, bascules avec captures | 7,9 ms médiane, 21,7 ms p95, 119 ms max |
| Timer Qt, plus grand intervalle à l’ouverture | 358 ms |
| Allocation GPU dédiée du processus WDDM à la fin | 45,6 Mio |

Les sept rapports statistiques ont la même empreinte. Les trois
rendus par mode ont des couches identiques bit pour bit. Le timer
inclut la publication des couches et les captures synchrones.
Le maximum à l’ouverture persiste sur ce parcours. La mesure
WDDM est un instantané après rendu et n’est pas un pic de VRAM.
[Méthode et mesures](../encre/MODEL_CONSENSUS_ANALYSIS.md#reproduction-locale) · [Trace Windows](../../validation/phase5-consensus-windows.json)

### Résultat scientifique du pilote

- L’intersection raccourcit la relecture à 45 060 pixels à 50 %,
  contre 94 429 pour l’union. Une sélection par intersection peut
  omettre les traces qu’un seul réseau relève. Le top 1 % disjoint
  motive une relecture séparée des modèles. [Courbes](../encre/MODEL_CONSENSUS_ANALYSIS.md#seuils-et-stratégies)
- Les faux positifs et le rappel restent inconnus sur PHerc0500P2.
  Le test des stratégies A, B, intersection et union devra employer
  les mêmes fenêtres indépendantes et fixer les seuils sur un autre
  rouleau que celui du test. Pour comparer le rappel, mesurer aussi
  le FPR à rappel égal, puis rapporter les effectifs par strate.
- Le jeu EduceLab fournit huit témoins pour contrôler la chaîne de
  données. Les bords et le fond avec zéros CT justifient de contrôler
  séparément le support d’acquisition et le masque d’annotation.
  Les traces clairsemées fournissent des exemples à suréchantillonner
  dans un futur jeu d’entraînement, uniquement au sein des rouleaux
  attribués à ce jeu. [Témoins et admission](../encre/INK_EVALUATION_DATASET.md)
- La relecture manuelle commence par les régions exposées de Frag3.
  La galerie napari conserve les observations, hypothèses, niveaux
  de confiance et références de relecture. La phase 5 n’attribue
  aucune nouvelle lettre et ne publie aucune transcription.

### Protocole CUDA à partir de checkpoints existants

Une fois la face, le rendu cible, les poids publics et le rouleau
réservé établis, retenir au plus quatre fenêtres de 256² par modèle
sur une surface, avec le nombre de coupes exact du checkpoint.
Précharger localement les plages Zarr autorisées, conserver leur
empreinte et consigner la configuration de résolution. Utiliser
`eval()`, des gradients désactivés et un lot de 1 sur la RTX.
Utiliser la précision FP32 comme référence, puis comparer un passage
en précision mixte si la configuration du modèle la prend en charge.
Consigner les digests de poids et de code, deux échauffements,
trois passages chronométrés avec synchronisation et le pic alloué
et réservé du GPU. Proposer comme plafonds 10 Gio réservés, 128 Mio
de données CT et 10 minutes pour la campagne de tuiles. Les poids
sont à mettre en cache au préalable. Ce protocole de suivi ne
demande aucun entraînement. L’inférence CUDA est différée tant
que les poids, la face et le jeu indépendant ne satisfont pas
les conditions de comparaison.

## Vérification et livrables

Le module statistique réutilise les coordonnées V/U et la lecture
TIFF de la comparaison. Les calculs lourds du panneau se font dans
les workers napari. Les vignettes sont limitées à 128 pixels de côté
et produites à partir du recadrage déjà chargé. Le cache S3, le chemin
Dask et les moteurs d’échantillonnage Python et Rust continuent
d’utiliser les parcours validés en phase 4.

La suite Windows native sous Python 3.11 et backend Qt Windows
donne **328 tests réussis**, un test ignoré pour le codec optionnel
et huit tests réseau réussis séparément sous Python 3.12 avec
`vc-delta3d`. Cet environnement réseau n’installe pas napari et
ignore ses quatre modules de tests à la collecte. Les nouveaux tests couvrent
les orientations TIFF, les faces et révisions incompatibles, les
seuils et ex æquo, l’incertitude, le déclenchement Qt de l’accord
et de la galerie, ainsi que la conservation de la provenance dans
les exports. [Passation](../../CLAUDE_HANDOFF.md)

```powershell
$env:QT_QPA_PLATFORM = 'windows'
$env:LOCALAPPDATA = Join-Path $PWD 'data/phase5-appdata-full'
$env:VESUVIUS_RUST_SAMPLER = '0'
.venv/Scripts/python.exe -m pytest -q --basetemp data/phase5-full
$env:VESUVIUS_TEST_ZARR = 's3://vesuvius-challenge-open-data/PHerc0800/volumes/20250521135224-8.640um-1.2m-116keV-masked.zarr/'
data/phase3-py312/Scripts/python.exe -m pytest -q -m network --basetemp data/phase5-network
```

- [Audit de provenance](../encre/INK_PROVENANCE_AUDIT.md)
- [Analyse du consensus, courbes et galerie](../encre/MODEL_CONSENSUS_ANALYSIS.md)
- [Jeu de référence et sélection pour la relecture](../encre/INK_EVALUATION_DATASET.md)
- [Passation et points à vérifier](../../CLAUDE_HANDOFF.md)
