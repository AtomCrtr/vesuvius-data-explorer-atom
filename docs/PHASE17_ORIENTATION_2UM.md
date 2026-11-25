**Sur PHerc0343P, la règle de texture situe l’air côté 02–14 (r = 5,83). Sur PHerc0500P2, elle désigne aussi les couches basses (r = 2,50).**

# Phase 17 · Orientation physique des piles frontales à 2 µm

Sur PHerc0343P, lire les fichiers de 63 vers 02 correspond donc à `Z_out` selon la règle figée. En combinant cette orientation avec la comparaison d’encre rapportée par EconLearn, six des sept fragments vont dans ce sens. Les protocoles d’évaluation diffèrent entre les séries. La phase 17A mesure la texture du CT et n’estime aucune ROC-AUC. [Commentaire d’EconLearn](https://github.com/ScrollPrize/villa/issues/2627#issuecomment-7146662786)

## Chronologie

| Étape | Commit local |
| --- | --- |
| Base du dépôt | `7ea4013` |
| Inventaire, protocole, lecteur et tests synthétiques avant toute lecture de pixels de couche | `e18fb52` |
| Profils, empreintes et vérification du chargeur Villa | `f00fd65` |
| Rapport, passation et réponse en anglais | Présent commit |

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

**Correspondance plausible.** Villa configure `2um_dataset/500p2a/layers/` avec `layer_range=(1,63)`, 62 canaux et `reverse_layers=True` (lignes 296–297). Le chargeur sélectionne 01–62, puis applique `images[:, :, ::-1]` après la lecture (lignes 165–166). Le test d’EconLearn utilise 63–02. Les deux fenêtres existent dans la pile publique de 14 990 × 27 160 px. Le chargeur lit les dimensions dans le premier plan. La valeur `pred_shape=[4608,13824]` provient du masque rembourré de validation de `l5_0_crop`. Il manque un lien de provenance entre les deux répertoires, par exemple un manifeste de rendu ou des empreintes de fichiers. Le sens physique d’entraînement de A pour ce segment reste ouvert. [Configuration](https://github.com/ScrollPrize/villa/blob/c8f3ba45304f0a317a49a155929e30d294f201eb/deprecated/ink-detection/train_resnet3d_3d_decoder.py#L264-L297) · [Chargeur](https://github.com/ScrollPrize/villa/blob/c8f3ba45304f0a317a49a155929e30d294f201eb/deprecated/ink-detection/train_resnet3d_lib/data_ops.py#L150-L166) · [Vérification](validation/phase17-500p2a.json)

## Limites et suite

La règle identifie un côté par sa texture sur huit régions. Une validation physique demanderait, par exemple, le sens de la normale du rendu dans le volume CT. Cette étape utilise uniquement les couches et le masque. Les scores d’encre rapportés par EconLearn étaient connus avant le gel. L’étape B attend l’accord du PO, l’examen des licences et un protocole distinct qui fixe les négatifs et la tolérance de recalage. [Projet non figé](validation/phase17b-protocol.json)

## Reproduction

Depuis la racine, installer le paquet avec ses dépendances de développement, puis lancer `python docs/validation/phase17_orientation.py`. Le téléchargement se fait par blocs dans `data/phase17/`. Les plans tiennent chacun en mémoire et sont décodés un à un. L’option `--stream` permet également un décodage PNG ligne par ligne. La suite hors réseau a donné 314 tests réussis, dont les quatre contrôles de la phase 17. Treize tests ont été ignorés et huit tests réseau désélectionnés.
