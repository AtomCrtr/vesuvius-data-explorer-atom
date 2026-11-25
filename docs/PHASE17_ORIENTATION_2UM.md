**Sur PHerc0343P, la règle de texture situe l’air côté 02–14 (r = 5,83). Sur PHerc0500P2, elle désigne aussi les couches basses, avec une marge faible (r = 2,50 pour un seuil de 2).**

# Phase 17 · Orientation physique des piles frontales à 2 µm

Sur PHerc0343P, lire les fichiers de 63 vers 02 correspond donc à `Z_out` selon la règle figée. EconLearn rapporte une ROC-AUC de 0,599 en ordre stocké et de 0,936 en ordre inversé. Cette comparaison externe concorde avec nos résultats sur cinq des six fragments évalués dans notre chaîne. Notre mesure sur PHerc0343P porte uniquement sur l’orientation. Les ROC-AUC d’EconLearn restent à reproduire. [Commentaire d’EconLearn](https://github.com/ScrollPrize/villa/issues/2627#issuecomment-7146662786)

## Chronologie

| Étape | Commit local |
| --- | --- |
| Base du dépôt | `7ea4013` |
| Inventaire, protocole, lecteur et tests synthétiques avant toute lecture de pixels de couche | `e18fb52` |
| Profils, empreintes et vérification du chargeur Villa | `f00fd65` |
| Rapport, passation et première réponse en anglais | `7dc0eb4` |

## Écarts-types dans les patchs du masque

| Fragment | Bas, 02–14 | Haut, 51–63 | Rapport | Côté air selon le seuil ≥ 2 | Contrôle secondaire (rapport) |
| --- | ---: | ---: | ---: | --- | --- |
| PHerc0343P | 3,60 | 21,02 | 5,83 | bas | bas (4,46) |
| PHerc0500P2 | 8,64 | 21,60 | 2,50 | bas | bas (4,15) |

Les écarts-types sont exprimés en niveaux de gris du PNG 8 bits. Chaque colonne d’extrémité est la moyenne des médianes par couche. Le budget comptabilisé, masque et en-têtes compris, est de 0,72 Gio sur PHerc0343P et de 2,31 Gio sur PHerc0500P2.

## Comment lire le résultat

| Côté air retenu | Ordre des couches 63 → 02 | Conséquence pour PHerc0343P |
| --- | --- | --- |
| Bas (02–14) | `Z_out` | Le résultat d’EconLearn irait dans le sens observé sur cinq des six fragments précédents. |
| Haut (51–63) | `Z_in` | Le sens favorable serait le même que sur Frag3. |
| Indéterminé | Sens physique inconnu | On peut comparer les ordres de fichiers, sans ajouter de fragment au décompte physique. |

L’inventaire porte sur 66 couches par pile, numérotées de 00 à 65. Le serveur a fourni les 33 octets d’en-tête PNG pour chaque plan et masque. Les autres fichiers du répertoire frontal figurent dans l’inventaire avec leur taille HTTP. Seuls le masque et les 26 couches prévues ont ensuite été téléchargés en entier. Chaque fichier a une empreinte SHA-256 dans les résultats. [Inventaire](validation/phase17-inventory.json)

La décision utilise la moyenne de 13 écarts-types médians à chaque extrémité. Le calcul reprend directement `phase13_eval.direction` avec une correspondance d’indices. La grille primaire de huit positions est déterministe. Pour le contrôle de sensibilité, huit autres centres ont été tirés dans le même masque érodé, avec la graine 1701. Les moyennes de gris, les maxima et les fractions proches de zéro dans le JSON décrivent les patchs. Un maximum porte uniquement sur les 26 couches mesurées. [Protocole](validation/phase17-protocol.json) · [Profils et empreintes](validation/phase17-orientation.json)

## Le rendu d’entraînement de 500P2

**Correspondance plausible.** Villa configure `2um_dataset/500p2a/layers/` avec `layer_range=(1,63)`, 62 canaux et `reverse_layers=True` (lignes 296–297). Le chargeur sélectionne 01–62, puis applique `images[:, :, ::-1]` après la lecture (lignes 165–166). Les plans arrivent donc dans l’ordre 62 → 01 à l’entraînement et 63 → 02 dans l’essai inversé d’EconLearn. Le décalage d’une couche (environ 2 µm) déplace la fenêtre et conserve le sens de parcours. Les deux fenêtres existent dans la pile publique de 14 990 × 27 160 px. Le chargeur lit les dimensions dans le premier plan. La valeur `pred_shape=[4608,13824]` provient du masque rembourré de validation de `l5_0_crop`. Il manque un lien de provenance entre les deux répertoires, par exemple un manifeste de rendu ou des empreintes de fichiers. Si le rendu d’entraînement est la pile publique avec la même numérotation, A aurait donc été entraîné en `Z_out` sur ce segment. [Configuration](https://github.com/ScrollPrize/villa/blob/c8f3ba45304f0a317a49a155929e30d294f201eb/deprecated/ink-detection/train_resnet3d_3d_decoder.py#L264-L297) · [Chargeur](https://github.com/ScrollPrize/villa/blob/c8f3ba45304f0a317a49a155929e30d294f201eb/deprecated/ink-detection/train_resnet3d_lib/data_ops.py#L150-L166) · [Vérification](validation/phase17-500p2a.json)

## Limites et suite

La règle identifie un côté par sa texture sur huit régions. Une validation physique demanderait, par exemple, le sens de la normale du rendu dans le volume CT. Cette étape utilise uniquement les couches et le masque. Les scores d’encre rapportés par EconLearn étaient connus avant le gel. Pour préparer l’étape B, le [commentaire publié](https://github.com/ScrollPrize/villa/issues/2627#issuecomment-7154345093) demande à EconLearn son script et sa sélection des négatifs. La référence 9 µm de Russo repart du tracé de l’équipe sur un autre canevas. Une comparaison appariée demande le support exact utilisé par EconLearn. Le projet de protocole consigne les licences consultées avant toute lecture des références optiques. [Projet non figé](validation/phase17b-protocol.json)

## Reproduction

Depuis la racine, installer le paquet avec ses dépendances de développement, puis lancer `python docs/validation/phase17_orientation.py`. Le téléchargement se fait par blocs dans `data/phase17/`. Les plans tiennent chacun en mémoire et sont décodés un à un. L’option `--stream` permet également un décodage PNG ligne par ligne. La suite hors réseau a donné 314 tests réussis, dont les quatre contrôles de la phase 17. Treize tests ont été ignorés et huit tests réseau désélectionnés.


### Pourquoi le bilan de phase 11 annonçait 359 réussites

La comparaison a été refaite avec `python -m pytest -q -rs` sous Linux, dans le même environnement Python 3.12 et en chargeant le code de chaque révision. Le bilan historique correspond au commit `b33337a`, antérieur à la fusion de la phase 11. [Bilan de phase 11](VESUVIUS_PHASE11.md)

| Révision | Environnement | Réussis | Ignorés signalés par pytest | Réseau désélectionnés |
| --- | --- | ---: | ---: | ---: |
| `b33337a`, bilan historique | Windows, Python 3.11, chiffres de la passation | 359 | 1 | 8 |
| `b33337a`, bilan reproduit | Linux, Python 3.12 | 296 | 13 | 8 |
| `e13fc36`, fusion de la phase 11 | Même environnement Linux | 297 | 13 | 8 |
| `7dc0eb4`, phase 17 | Même environnement Linux | 314 | 13 | 8 |

Les 13 entrées ignorées se répartissent ainsi.

| Motif donné par pytest | Entrées | Cas concernés |
| --- | ---: | ---: |
| napari absent à l’import des modules de comparaison, contrôle qualité, surface et ouverture | 4 modules | 8 + 7 + 17 + 23 = 55 |
| napari absent dans le test de recalage optique | 1 test | 1 |
| Extension `vesuvius_explorer_rust` absente | 7 tests | 7 |
| Codec `vc_delta3d` absent | 1 test | 1 |

Pytest signale chaque module ignoré à l’import une seule fois. Ses cas individuels restent hors collecte. En phase 17, pytest a collecté 331 cas individuels, dont 8 réseau et 9 ignorés à l’exécution. Les quatre modules contiennent 55 cas supplémentaires. CUDA ne figure dans aucun motif d’exclusion de ce run.

La comparaison Git de `b33337a` à `7dc0eb4` retrouve les tests de phase 11. Cinq fichiers napari ont été déplacés dans `tests/gui/`. Un test d’alignement a été renommé et adapté au déplacement par bloc. Un cas de tolérance de recalage a été ajouté avant la fusion de phase 11, puis 17 cas dans les phases suivantes. À environnement identique, les 18 cas ajoutés expliquent exactement le passage de 296 à 314 réussites. Le bilan Windows publié ne donne pas le nom du seul test ignoré sur cette machine.
