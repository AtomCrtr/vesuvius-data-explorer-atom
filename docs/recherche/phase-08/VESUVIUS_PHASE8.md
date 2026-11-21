# Vesuvius Explorer · Phase 8

La phase 8 cartographie l’effet de l’ordre de profondeur sur le rendu historique de PHerc0500P2, vérifie son sens géométrique dans le CT brut et prépare une confrontation avec une mesure optique de l’encre.

## Résultats et portée

| Question | Résultat |
| --- | --- |
| Où l’ordre Z compte-t-il ? | 61 fenêtres fixées par la grille et le support CT. L’écart absolu moyen vaut 0,247 sur 790 200 pixels valides. La couverture et la distance au bord ont les associations régionales les plus fortes parmi les indicateurs testés, avec Spearman 0,396 et 0,388. L’effet persiste loin du bord et le motif exact reste inexpliqué. [Robustesse spatiale](../../PHASE8_SPATIAL_ROBUSTNESS.md) |
| Quel côté indique l’ordre Z ? | La profondeur croissante suit `−N` dans les six nouveaux voisinages CT et les quatre de phase 7. Le masque volumique de recto du même scan ne couvre aucun des six témoins sondés. La face physique et le côté d’écriture du segment restent à établir. [Orientation](PHASE8_PHYSICAL_ORIENTATION.md) |
| Quelles références d’encre sont utilisables ? | Deux fenêtres de contrôle géométrique et six exploratoires chez EduceLab. Quatre champs optiques annotés du même fragment dans un jeu public. Le lien vers la grille CT et l’exclusion de l’entraînement restent à vérifier. [Validation](PHASE8_INK_VALIDATION.md) |
| Quelles zones examiner ? | R02 et R04 présentent deux géométries distinctes. R03 présente le plus fort changement des quatre et R01 sert de témoin de faible réponse. Les archives permettent une première lecture CT sans scores, puis une lecture avec les cartes et les notes. [Relecture](PHASE8_CANDIDATE_REVIEW.md) |
| Quelles limites restent déterminantes ? | Un seul segment à une résolution, des scores non calibrés, une variabilité spatiale fortement autocorrélée et aucune référence d’encre admissible pour mesurer la généralisation. B reste indisponible sous forme de poids vérifiés. [Demande de reproductibilité](PHASE8_INK_VALIDATION.md#checkpoint-b-et-demande-de-reproductibilité) |
| Quelle est l’expérience prioritaire ? | Recaler un champ optique de PHerc0500P2 sur la feuille CT à partir de repères géométriques, contrôler la face et l’erreur sur des repères mis de côté, puis établir les exclusions d’entraînement avant de mesurer la performance. [Étapes](PHASE8_INK_VALIDATION.md#expérience-suivante) |

## Préservation

La branche locale `feat/vesuvius-phase8` reprend l’arbre de travail de la phase 7, au commit de base `eba4082134df544dc56b5f9d6622d9fd0161f36c`. Les travaux des phases précédentes étaient présents dans l’arbre de travail. Le point de restauration `data/phase8/phase7-before-phase8.zip` conserve 96 fichiers de l’arbre et quatre artefacts. Son `restore.json` indique les destinations et SHA-256. Les fichiers, leurs empreintes et les CRC de l’archive ont été vérifiés. Pour reconstruire l’état phase 7 dans une copie du dépôt au commit de base, vérifier l’empreinte du ZIP, l’extraire dans un répertoire distinct, puis recopier ses membres selon `restore.json`.

Archive de restauration (`data/phase8/phase7-before-phase8.zip`) · Empreinte (`data/phase8/phase7-before-phase8.sha256`)

## Reproduction

Depuis la racine sous PowerShell, utiliser l’environnement Windows CUDA établi en phase 6. Le plan lit la grille ZVU `[118,1160,1400]` du rendu historique et ne matérialise que les coupes `[28,90)`. Il épingle 110 objets Zarr dont 46 du cache phase 7. Le téléchargement de 26 nouveaux objets CT a transféré 50 266 112 octets. Les objets absents du Zarr sparse prennent la valeur de remplissage enregistrée. Le plan garde les URI, plages, tailles et empreintes. Le cache de phase 7 reste accessible en lecture. Les répertoires `data/phase8/cuda` et `data/phase8/cuda-repeat` contiennent les logits 64², les scores 256², les origines, les masques et les journaux en pleine précision. Les cartes assemblées flottantes sont dans `data/phase8/surface.npz`, `Z-signed.tif` et `Z-sensitivity.tif`.

```powershell
$phase8GpuPython = 'data/phase6-cuda/Scripts/python.exe'
$phase8Python = '.venv/Scripts/python.exe'
& $phase8GpuPython docs/validation/phase8_cuda.py data/phase8 --prepare
& $phase8GpuPython docs/validation/phase8_cuda.py data/phase8
& $phase8GpuPython docs/validation/phase8_cuda.py data/phase8 --repeat
Copy-Item data/phase8/input-plan.json docs/validation/phase8-input-plan.json
Copy-Item data/phase8/cuda/run.json docs/validation/phase8-cuda-windows.json
Copy-Item data/phase8/cuda-repeat/run.json docs/validation/phase8-cuda-repeat-windows.json
& $phase8Python docs/validation/phase8_spatial.py data/phase8 docs/validation/phase8-spatial-windows.json
& $phase8Python docs/validation/phase8_review.py data/phase8 docs/validation/phase8-spatial-windows.json docs/validation/phase8-review-windows.json
& $phase8Python docs/validation/phase8_visuals.py data/phase8/surface.npz docs/validation/phase8-spatial-windows.json docs/validation/phase8-review-windows.json docs/validation/phase8-Z-sensitivity.png docs/validation/phase8-candidates.png
& $phase8Python docs/validation/phase8_orientation.py data/phase8 docs/validation/phase8-orientation-windows.json
& $phase8Python docs/validation/phase8_recto.py data/phase8/recto docs/validation/phase8-orientation-windows.json docs/validation/phase8-recto-windows.json
& $phase8Python docs/validation/phase8_references.py docs/validation/phase8-ink-references.json
```

La procédure utilise le cache de phase 7 vérifié et le poids A `ink_canonical_2um` d’empreinte SHA-256 `36dd0de84b7b7aa6590184192c7415466cd8a1ba7c1e59f42c6373846373c3e0`. Le code de l’architecture est épinglé à `baf5e605bb42a3d55a62b7c5c728e0908137225c`. Les entrées CT uint8 sont écrêtées à 200 puis divisées par 200. Le passage en FP32 est déterministe, avec TF32 désactivé. La routine garde les logits et applique sigmoid puis interpolation bilinéaire avant assemblage. Pour une nouvelle exécution effective, fournir un espace de travail phase 8 séparé avec ses entrées préparées. Les commandes réutilisent une sortie déjà présente lorsque ses empreintes concordent.

### Mesures sur la RTX 4080 Laptop

| Mesure | Première campagne complète archivée | Processus de répétition |
| --- | ---: | ---: |
| Tuiles dans la sortie | 90 | 8 |
| Reprises de phase 7 | 32 | 0 |
| Tuiles recalculées dans les deux orientations | 54 | 8 |
| Tuiles vides | 4 | 0 |
| Médiane A+ par tuile calculée | 477,6 ms | 474,5 ms |
| Médiane A− par tuile calculée | 477,2 ms | 477,4 ms |
| Pic de VRAM allouée / réservée | 1,35 / 1,60 Gio | 1,35 / 1,60 Gio |
| Pic de RAM du processus | 1,17 Gio | 1,18 Gio |

Les durées CUDA sont mesurées entre synchronisations après transfert de la tuile, puis avant restitution CPU. Les 8 tuiles de répétition couvrent des positions réparties parmi les nouvelles tuiles non vides et reproduisent exactement les six tableaux attendus, y compris logits et scores dans les deux orientations. L’assemblage et les mesures prennent 7,3 s sur CPU avec un pic d’environ 406 Mio dans la trace jointe. Les durées reflètent la charge Windows de cette exécution.

CUDA utilise Python 3.11.9, PyTorch 2.8.0+cu126, CUDA 12.6 et cuDNN 9.10.2. L’interface Windows utilise Python 3.11 et napari 0.10.0. La campagne réseau tourne en Python 3.12. Python reste le moteur par défaut, avec Rust optionnel et Dask sur les chemins de chargement existants. La campagne n’a demandé aucun entraînement.

[Plan](../../validation/phase8-input-plan.json) · [Mesures CUDA](../../validation/phase8-cuda-windows.json) · [Répétition](../../validation/phase8-cuda-repeat-windows.json) · [Analyse CPU](../../validation/phase8-spatial-windows.json)

## Vérification Windows

| Suite | Résultat |
| --- | --- |
| Windows natif, Qt Windows, moteur Python | 347 réussis, 1 ignoré, 8 désélectionnés |
| Réseau en Python 3.12 | 8 réussis, 4 ignorés, 293 désélectionnés |
| Parité et intégration avec Rust optionnel | 73 réussis |

Les nouveaux tests couvrent la grille et ses limites, l’effet sur score constant, les masques, le rééchantillonnage par blocs et les exports vérifiables. Les tests Qt vérifient la sélection de la paire, le fond CT, l’ouverture de la couche et les métriques spatiales. Un contrôle natif a aussi chargé la session réelle de 1 160 × 1 400 pixels et navigué vers une cellule mesurée depuis la couche de sensibilité. Les tests historiques gardent la couverture des transformations Z, de la normalisation, des annotations et de Rust. La suite Windows signale une dépréciation de caméra napari et un avertissement de conversion de contraste.

Journal natif (`data/phase8/windows-tests.log`) · Journal réseau (`data/phase8/windows-network-tests.log`) · Journal Rust (`data/phase8/windows-rust-tests.log`)
