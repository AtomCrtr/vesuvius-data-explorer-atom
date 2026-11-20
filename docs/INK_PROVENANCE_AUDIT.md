# Provenance des cartes PHerc0500P2

Les deux TIFF ont été produits à partir du même rendu UV, celui du
maillage historique du segment `20250919184428-0500P2-wrap01_0919`.
Ils partagent la grille du rendu et diffèrent notamment par le modèle
et par le sens de lecture de la profondeur. La face anatomique et la
calibration restent indéterminées. Le Jaccard 0,477 mesure le recouvrement
de deux décisions dans une fenêtre, sans vérité terrain. [Audit reproductible et empreintes](validation/phase5-provenance-windows.json)

## Modèles et exécutions

| | A | B |
|---|---|---|
| Identifiant Atlas | `20260417190342-new_canon_autoresearch_recipe` | `20260709123958-mrg20736-1um-s1z2` |
| Clé d’inférence | `new_canon_autoresearch_recipe` | `mrg20736_1um_s1z2` |
| Architecture Atlas | ResNet3D-152, décodeur 3D | ResNet3D-152 |
| Résolution cible du modèle | 2–3 µm | 1–1,5 µm, niveau de rendu 1 indiqué dans la fiche |
| Exécution Atlas le 21 juillet 2026 UTC | `ink-detect-pherc0500p2-d5b71a09`, 14:35:24 | `ink-detect-pherc0500p2-95ba6c57`, 14:47:59 |
| `force-reverse` | `false` | `true` |
| Plage de codes du TIFF | 0–237 | 0–223 |
| Taille du TIFF | 148 354 octets | 240 100 octets |

Le workflow `ink-detection-partitioned` annonce `v43` et `v43-cpu`,
la révision d’infrastructure `345960ef4c3ffd915bab09cc23b35d8c567a8651`
et Atlas `28cd60ec3aa7f5722ecd1056f2965b7df4c2cbe0`, avec
`atlas_git_dirty=true`. Les deux exécutions ont passé les indices
`[28, 90[` (62 coupes), une fenêtre 256², un pas de 128 et
`add-scale-bar=false`. Le lot est laissé au défaut du modèle. L’entrée
effective est le même stack à 2,215 µm. Pour B, le niveau 1 de la fiche
décrit une exigence de catalogue. L’exécution pointe vers le stack de
2,215 µm, dont le niveau 1 est à 4,43 µm dans le plan. Une conversion
interne vers la résolution nominale du modèle reste à établir.
[Catalogue Atlas](https://vesuvius-challenge-open-data.s3.amazonaws.com/metadata.json) · [Champs d’exécution conservés](validation/phase5-provenance-windows.json)

La fiche de publication `ink_canonical_2um` associe la recette A à un
checkpoint d’époque 13, étape 113246, distribué sous licence MIT.
Son identifiant LFS SHA-256 est
`36dd0de84b7b7aa6590184192c7415466cd8a1ba7c1e59f42c6373846373c3e0`.
L’empreinte des poids réellement
chargés en juillet, le fichier de poids exact de B, le digest des images
`v43` et les jeux d’entraînement complets des deux exécutions restent
indisponibles dans les artefacts examinés. La fiche A sert de référence
à la famille de modèle. [Fiche du modèle canonique](https://huggingface.co/scrollprize/ink_canonical_2um/blob/e154062e55513a1d4110f40fceeddb90eaa0f022/README.md) · [Checkpoint public](https://huggingface.co/scrollprize/ink_canonical_2um/blob/e154062e55513a1d4110f40fceeddb90eaa0f022/r152_3ddec_v2_l5_epoch13.ckpt)

## Correspondance géométrique

Atlas relie les deux TIFF au rendu `render-tifxyz-pherc0500p2-1babadf6`,
produit par `vc_render_tifxyz`, Villa
`530584554c031c982ba3aa243e1ea39c4bef9818`. Son entrée est
`20250919184428-on-20250526151718-2.215um.tifxyz` (58 × 70 points), publiquement
associé au volume CT `20250526151718`. Le suffixe `-t2` désigne un autre
maillage (30 × 36), publié ultérieurement. Le rendu historique déclare
groupe 0, échelle 1, rotation 0, aucune réflexion UV (`flip=-1`),
pas de crop, `flip-normals=true`, puis 118 coupes sur [Z,V,U] de
forme 118 × 1160 × 1400. Le niveau 0 a un pas de 2,215 µm dans les trois
axes et une translation nulle. Le tag d’orientation TIFF est absent
(orientation standard). Les tags de résolution valent 1/1 sans unité.
[Entrée de rendu et en-têtes](validation/phase5-provenance-windows.json)

- Les 790 200 pixels de code non nul sont identiques sur les deux TIFF
  (IoU 1,000). Les IoU après une réflexion V, une réflexion U, puis une
  rotation 180° sont respectivement 0,6752, 0,6997 et 0,6183. Ce test
  porte sur l’empreinte du rendu, sans utiliser les valeurs d’encre.
- Dans la phase 4, quatre fenêtres CT de 19² pixels retrouvaient la
  coupe 59 du stack avec une corrélation entre 0,966 et 0,981 via le
  maillage historique, contre 0,600 à 0,884 via `-t2`. Les deux
  recadrages de 384² pixels sont inchangés bit pour bit. Leur origine
  [V,U] est [388,508], leur borne haute exclusive [772,892].
  [Mesures CT de la phase 4](validation/phase4-ink-windows.json)
- Le sens des normales du rendu et le sens des coupes données au réseau
  sont connus. Leur lien avec le recto ou le verso anatomique reste à
  confirmer. Le support partagé ne fournit pas de correspondance entre
  traits d’encre et ne permet pas d’affirmer que les deux réseaux ont
  répondu au même signal physique.

## Valeurs, post-traitement et réutilisation

Les descriptions TIFF portent `software=optimized_inference`. Le
mainteneur confirme ce chemin et indique que les deux réseaux ont des
architectures et des entraînements différents. Le code public examiné
applique une sigmoïde à la sortie, redimensionne et pondère les tuiles
chevauchantes (fenêtre de Hann ou gaussienne selon la configuration),
réduit les partitions et sérialise des intensités `uint8` bornées. Le
choix exact de la fenêtre et les réglages internes de `v43` restent à
rattacher aux exécutions. Les deux TIFF donnent des scores quantifiés
sans table de calibration. Le code 0 est conservé dans les calculs de
la fenêtre, tandis que le calcul de rang sur la surface entière
conditionne explicitement sur le support non nul.
[Confirmation du mainteneur](https://github.com/ScrollPrize/villa/issues/1377#issuecomment-5316476283) · [Inférence publique](https://raw.githubusercontent.com/ScrollPrize/villa/baf5e605bb42a3d55a62b7c5c728e0908137225c/ink-detection/optimized_inference/inference.py) · [Export public](https://raw.githubusercontent.com/ScrollPrize/villa/baf5e605bb42a3d55a62b7c5c728e0908137225c/ink-detection/optimized_inference/entrypoint.py)

Les cartes et le rendu proviennent du Vesuvius Challenge Open Data,
sous CC BY-NC 4.0 avec attribution selon les instructions de la source.
Les URI S3 exactes, les ETag, les SHA-256 des TIFF et le SHA-256 du
catalogue servi sont dans le JSON. Aucun fichier annexe de paramètres
n’a été trouvé dans le répertoire public des scores. La convention
d’affichage napari n’ajoute aucune annotation d’encre indépendante.
[Licence et citation Open Data](https://github.com/ScrollPrize/open-data#support-and-citation) · [Artefacts exacts et contrôles](validation/phase5-provenance-windows.json)

## Reproduction

Depuis la racine et avec le catalogue local de la phase 4, la commande
lit deux petits TIFF, les en-têtes du stack et les deux petits maillages.
L’option `--comparison` produit un manifeste napari distinct avec la
provenance vérifiée. Les données originales restent sous `data/`.
Si les recadrages manquent, exécuter d’abord le protocole de phase 4.
[Extraction de phase 4](INK_MODEL_COMPARISON.md)

```powershell
.venv/Scripts/python.exe docs/validation/phase5_provenance.py data/rust2/catalog.json data/phase4-ink docs/validation/phase5-provenance-windows.json --comparison
```
