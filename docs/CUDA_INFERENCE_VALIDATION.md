# Inférence CUDA du checkpoint canonique 2 µm

Le checkpoint public A fonctionne sous Windows natif sur la **NVIDIA
RTX 4080 Laptop**. Avec une même tuile et des poids identiques, inverser
uniquement Z donne un Spearman de **−0,334** entre les deux sorties et
aucun pixel commun dans leurs top 1 % et 5 %. C’est un effet mesuré du
sens des coupes sur cette tuile. Sa contribution aux cartes A et B
publiées reste à mesurer avec les poids exacts de production.
[Protocole et résultats bruts](validation/phase6-cuda-windows.json) · [Analyse des deux ordres](validation/phase6-review-windows.json)

## Checkpoint et entrée

- **Poids.** `r152_3ddec_v2_l5_epoch13.ckpt`, époque 13, étape 113246,
  1 549 556 213 octets, publication MIT. SHA-256
  `36dd0de84b7b7aa6590184192c7415466cd8a1ba7c1e59f42c6373846373c3e0`.
  Le code de l’architecture Villa est épinglé à `baf5e605bb42a3d55a62b7c5c728e0908137225c`.
  Les fichiers exécutés sont vérifiés par empreinte. PyTorch charge
  le checkpoint avec `weights_only=True` et contrôle toutes les clés
  du réseau. [Fiche et poids publics](https://huggingface.co/scrollprize/ink_canonical_2um/tree/e154062e55513a1d4110f40fceeddb90eaa0f022) · [Architecture publique](https://github.com/ScrollPrize/villa/tree/baf5e605bb42a3d55a62b7c5c728e0908137225c/ink-detection/optimized_inference) · [Licence MIT du code](https://github.com/ScrollPrize/villa/blob/baf5e605bb42a3d55a62b7c5c728e0908137225c/LICENSE)
- **CT.** PHerc0500P2, rendu historique L0 de 2,215 µm,
  quatre blocs Zarr publics (7,4 Mio). La tuile [V,U] [512,512] → [768,768]
  est une tuile complète alignée au pas 128 et située dans la fenêtre
  CT auditée. Ses 65 536 pixels ont un signal CT non nul en profondeur.
  On prélève les mêmes 62 coupes dans les deux cas, 28→89 puis 89→28,
  sans modifier V ou U. La coupe 59 correspond exactement au
  recadrage du CT de phase 4, pixel pour pixel.
  [Empreintes et coordonnées](validation/phase6-cuda-windows.json) · [Licence des données](https://github.com/ScrollPrize/open-data#support-and-citation)
- **Prétraitement.** CT `uint8`, validité avant écrêtage, puis
  `min(voxel, 200) / 200` en FP32. Les voxels supérieurs à 200
  représentent 0,014 % de cette tuile. Le tenseur `[B,C,Z,V,U]`
  mesure `[1,1,62,256,256]`. Le réseau conserve sa BatchNorm3D
  apprise en mode évaluation. Logits natifs 64², puis sigmoïde
  et interpolation bilinéaire vers 256². Le code consigne les
  logits et les scores séparément. [Code public du prétraitement](https://github.com/ScrollPrize/villa/blob/baf5e605bb42a3d55a62b7c5c728e0908137225c/ink-detection/optimized_inference/inference.py#L273)

## Mesures Windows

Python 3.11.9, PyTorch 2.8.0+cu126, CUDA 12.6, cuDNN 9.10.2,
pilote NVIDIA 616.64. Lot de 1, FP32 sans TF32, choix d’algorithmes
cuDNN déterministes, un échauffement puis trois passages synchronisés
par ordre. Le plafond de l’allocateur est 9 Gio.

| Ordre | Médiane | Étendue | Pic VRAM PyTorch alloué / réservé | Bornes des logits |
|---|---:|---:|---:|---:|
| 28→89 | 237 ms | 231–238 ms | 1,35 / 1,60 Gio | −1,611 → 1,730 |
| 89→28 | 239 ms | 239–241 ms | 1,35 / 1,60 Gio | −1,695 → −1,169 |

Le chargement a pris 1,99 s. Les trois passages donnent les mêmes
empreintes pour un ordre donné. Un second processus CUDA retrouve
les mêmes SHA-256 pour les logits et les scores des deux ordres.
Les scores interpolés vont de
0,167 à 0,843 dans l’ordre source et de 0,155 à 0,237 en ordre inverse.
Le désaccord par rang persiste au centre 128². L’écart absolu moyen de
0,246 est exprimé sur l’échelle de sortie du même modèle. Les fichiers
`fp32-*-logits.npy` et `fp32-*-scores.npy` sont conservés sous
`data/phase6/`.

## Portée de la comparaison publique

Pour cette expérience, les deux ordres reçoivent rigoureusement les
mêmes voxels. Les résultats isolent un effet de profondeur, avec
un réseau et un contexte UV fixes. Le TIFF publié est issu d’un
assemblage pondéré de tuiles et d’un export quantifié. Le digest
de ses poids et de l’image d’exécution `v43` reste inconnu.
Une comparaison numérique de reproduction du TIFF serait prématurée.

Le dépôt public de modèles a fourni A. La recherche de B sous
`mrg20736_1um_s1z2` et son identifiant Atlas n’a pas donné de
checkpoint public vérifiable. Les requêtes anonymes sur le préfixe du
registre de poids S3 ont obtenu HTTP 403 pour les deux recettes.
La provenance et la licence de B restent à obtenir auprès de la
source. L’alternative exécutée est l’ablation d’ordre Z avec A, sur
le rendu public d’origine. Elle ne montre ni quelle face porte l’encre
ni quelle architecture donne les meilleures détections.

## Reproduction

L’environnement CUDA reste isolé de napari. L’installation initiale
du runtime Windows demande environ 2,9 Go pour la roue PyTorch
CUDA. Le modèle public ajoute 1,55 Go. Les relectures qui suivent
utilisent les fichiers mis en cache. [Versions PyTorch](https://pytorch.org/get-started/previous-versions/)

```powershell
.venv/Scripts/python.exe -m venv data/phase6-cuda
data/phase6-cuda/Scripts/python.exe -m pip install --index-url https://download.pytorch.org/whl/cu126 'torch==2.8.0+cu126' 'torchvision==0.23.0+cu126'
.venv/Scripts/python.exe docs/validation/phase6_cuda.py data/phase6 --prepare docs/validation/phase5-provenance-windows.json
# Le lien du poids exact et son SHA-256 figurent dans la trace CUDA.
# Placer ce fichier sous data/phase6/canonical/.
data/phase6-cuda/Scripts/python.exe docs/validation/phase6_cuda.py data/phase6 --output data/phase6/cuda-reproduction.json
```
