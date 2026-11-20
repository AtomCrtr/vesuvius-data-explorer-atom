# Phase 7 · Intervention sur l’ordre Z

Deux conditions ont été exécutées, **A+** (coupes 28 à 89 dans
l’ordre du stack publié) et **A−** (les mêmes coupes de 89 à 28).
B+ et B− restent sans mesure en l’absence des poids exacts de B.
Le contraste A+/A− isole l’effet de l’ordre Z pour le checkpoint
A public. L’effet du checkpoint, l’interaction checkpoint × Z et
la contribution de l’ordre Z au désaccord A/B de production
restent non identifiables dans cette campagne.
[Audit des poids](PHASE7_CHECKPOINT_AUDIT.md) · [Résultats de la matrice](validation/phase7-model-comparison.json)

## Protocole fixé avant l’inférence

Le plan couvre la fenêtre CT des phases 4–6
`[388,772[ × [508,892[` et une région distante
`[896,1024[ × [768,1024[` qui inclut les deux blocs riches en
scores A de la phase 6. Toutes les bornes sont [V,U], fin exclusive.
Ces zones sont disjointes spatialement. La région distante est une
vérification de sensibilité, sélectionnée avec connaissance de la
carte publique. Les deux régions appartiennent au même papyrus.

Les deux conditions utilisent les mêmes 32 fenêtres d’inférence
de 256², alignées sur la grille du stack complet au pas 128.
Les mêmes masques de validité sont dérivés des données CT avant
normalisation par la règle « au moins une coupe non nulle ».
Le plan lit 42 objets Zarr (77,44 Mio). Quatre positions sans
objet sont remplies avec la valeur 0 déclarée par Zarr. Les
empreintes, états des blocs et origines des tuiles sont archivés.
Pour chaque tuile, l’entrée est `[1,1,62,256,256]`, en FP32,
avec `min(CT,200)/200`. Les logits 64² sont sauvegardés.
La sortie est transformée par sigmoïde, interpolée par bilinéaire
à 256² et assemblée par la fenêtre de Hann normalisée du code
public. Les deux traitements partagent le même dénominateur
de recouvrement, calculé à partir des poids valides de chaque pixel.
Un pixel sans poids est représenté par NaN. Aucun changement UV,
déplacement ou inversion 2D n’a été choisi à partir des scores.
[Plan et SHA-256](validation/phase7-input-plan.json) · [Définition d’assemblage Villa](https://github.com/ScrollPrize/villa/blob/baf5e605bb42a3d55a62b7c5c728e0908137225c/ink-detection/optimized_inference/inference.py#L45)

## Contrôle physique de la normale

Le code de rendu épinglé à
`530584554c031c982ba3aa243e1ea39c4bef9818` construit ses offsets
pour 118 coupes autour de la coordonnée 58,5, au pas d’un voxel.
Il définit la normale géométrique en XYZ par
`N = dP/dU × dP/dV`. Le paramètre Atlas `flip-normals=true`
fait croître l’indice de profondeur le long de `−N).
[Code de rendu](https://github.com/ScrollPrize/villa/blob/530584554c031c982ba3aa243e1ea39c4bef9818/volume-cartographer/apps/src/vc_render_tifxyz.cpp#L275) · [Métadonnées Atlas](validation/phase5-provenance-windows.json)

Quatre témoins de 13 × 13 pixels ont été interpolés dans le
volume CT brut selon les deux signes autour du même point TIFXYZ,
aux couches 43, 51, 59, 67 et 75. Le Pearson agrège les cinq
plans CT entre le rendu publié et la reconstruction de chaque signe.

| Point V/U | Pearson dans le sens −N | Pearson dans le sens +N |
|---|---:|---:|
| [480,600] | 0,993 | −0,149 |
| [520,640] | 0,992 | 0,151 |
| [600,740] | 0,997 | −0,516 |
| [640,800] | 0,991 | −0,300 |

Les normales XYZ unitaires et les bornes des blocs CT sont
enregistrées pour chaque témoin. La coupe 59 de la tuile de
phase 6 est aussi identique au CT de référence dans le panneau.
Ces contrôles reposent sur le CT seul. Ils établissent le sens
géométrique local du stack et ne renseignent pas le recto ou
verso anatomique du fragment. La convention habituelle de
Villa présuppose un repère de lecture attaché à la surface.
Ce rattachement anatomique manque pour ce fragment.
[Mesures de signe et normales](validation/phase7-orientation.json) · [Tutoriel de rendu](https://scrollprize.org/tutorial5)

## Temps, mémoire et répétition

Sur RTX 4080 Laptop avec Python 3.11.9, PyTorch 2.8.0+cu126,
CUDA 12.6 et cuDNN 9.10.2, les médianes sont **242,6 ms** pour A+
et **242,9 ms** pour A− par tuile. Le chargement prend 2,23 s.
La mémoire GPU allouée atteint 1,35 Gio, la mémoire réservée
1,60 Gio. Le pic de mémoire résidente du processus est 1,08 Gio.
Les durées GPU sont synchronisées, hors transfert et écriture.
Les 64 passages produisent des tableaux de logits et de scores
identiques dans deux processus indépendants. La tuile
`[512,768[ × [512,768[` reproduit aussi les logits de la phase 6
bit pour bit dans chacun des deux ordres. Cette propriété est
mesurée dans cet environnement précis. Le plan, les réglages,
le runtime, le SHA-256 des poids et celui de la sortie sont
contrôlés pour réutiliser le cache.
[Trace CUDA](validation/phase7-cuda-windows.json) · [Comparaison des répétitions](validation/phase7-model-comparison.json)

## Reproduction

Les poids publiés et l’environnement CUDA sont ceux de la
[phase 6](CUDA_INFERENCE_VALIDATION.md). Le premier processus
laisse les logits et scores non quantifiés dans
`data/phase7/cuda/tiles.npz`.

```powershell
.venv/Scripts/python.exe docs/validation/phase7_experiment.py data/phase7 --prepare docs/validation/phase5-provenance-windows.json
data/phase6-cuda/Scripts/python.exe docs/validation/phase7_experiment.py data/phase7
data/phase6-cuda/Scripts/python.exe docs/validation/phase7_experiment.py data/phase7 --output data/phase7/cuda-repeat
.venv/Scripts/python.exe docs/validation/phase7_orientation.py data/phase7 data/phase6 docs/validation/phase4-ink-windows.json docs/validation/phase7-orientation.json
```
