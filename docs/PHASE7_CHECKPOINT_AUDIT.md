# Phase 7 · Identité des checkpoints

**Le checkpoint A public est vérifié et utilisable pour une intervention
sur l’ordre Z. Le checkpoint B de production reste indisponible.** Les
deux cartes publiques PHerc0500P2 sont vérifiées par SHA-256. Atlas
rattache chacune à une recette et à une exécution, mais ne publie pas
le digest des poids chargés. [Audit machine](validation/phase7-checkpoints.json)

| Élément | A | B |
|---|---|---|
| Identifiant Atlas | `20260417190342-new_canon_autoresearch_recipe` | `20260709123958-mrg20736-1um-s1z2` |
| Architecture Atlas | ResNet3D-152, décodeur 3D | ResNet3D-152. Le chargeur public correspondant réduit les cartes de caractéristiques par maximum en profondeur et utilise un décodeur 2D. |
| Poids utilisables | `r152_3ddec_v2_l5_epoch13.ckpt`, publication `e154062e55513a1d4110f40fceeddb90eaa0f022`, époque 13, étape 113246. | Fichier exact et SHA-256 indisponibles. |
| Taille et empreinte vérifiées | 1 549 556 213 octets, SHA-256 `36dd0de84b7b7aa6590184192c7415466cd8a1ba7c1e59f42c6373846373c3e0`. | Sans objet pour la phase 7. |
| Domaine nominal | Environ 2 µm. | 1–1,5 µm, Atlas indique un niveau de rendu requis. |
| Normalisation | `with_norm=true`, BatchNorm3D à 1 canal intégrée aux poids publics. L’entrée du pipeline public applique écrêtage à 200 et division par 200. | Le chargeur public active la normalisation apprise selon les clés des poids. Les réglages propres au checkpoint de production restent inconnus. |
| Ordre de l’exécution Atlas | `force-reverse=false` | `force-reverse=true` |
| Droits | Le poids public et le code Villa épinglé sont sous licence MIT. | Licence du poids exact inconnue. |

La source LFS du fichier public A annonce le même SHA-256 et la même
taille que le fichier local. Le digest du checkpoint publié ne
renseigne pas ce que le conteneur de juillet a chargé depuis le
registre S3. La campagne conserve donc deux identités distinctes
pour le checkpoint A public et pour le TIFF A de production.
[Fiche A épinglée](https://huggingface.co/scrollprize/ink_canonical_2um/tree/e154062e55513a1d4110f40fceeddb90eaa0f022) · [Licence Villa](https://github.com/ScrollPrize/villa/blob/baf5e605bb42a3d55a62b7c5c728e0908137225c/LICENSE) · [Chargeur ResNet3D](https://github.com/ScrollPrize/villa/blob/baf5e605bb42a3d55a62b7c5c728e0908137225c/ink-detection/optimized_inference/model_resnet3d.py)

Quatre recherches publiques Hugging Face par nom de recette, variante,
identifiant Atlas et fragment du nom ont donné HTTP 200 avec un résultat
vide pour B. Les deux requêtes anonymes de préfixe au registre
`scrollprize-models-registry` ont donné HTTP 403. Cette limite porte
sur les sources examinées et leurs droits d’accès. L’admission de B
requiert un fichier rattaché au job, son hash, sa configuration et des
droits de réutilisation documentés. Aucun modèle de substitution
n’a été retenu.
[Requêtes et réponses](validation/phase7-checkpoints.json) · [Résolution publique des poids par Villa](https://github.com/ScrollPrize/villa/blob/baf5e605bb42a3d55a62b7c5c728e0908137225c/ink-detection/optimized_inference/entrypoint.py#L408)

Les deux sorties de production correspondent au même rendu de surface
historique de 2,215 µm, tuiles 256² au pas 128, coupes `[28,90[`,
exécutions `ink-detect-pherc0500p2-d5b71a09` et
`ink-detect-pherc0500p2-95ba6c57`. Le mainteneur rattache les deux
sorties à `optimized_inference`. Les tags `v43` / `v43-cpu` sont
déclarés. Leurs digests et la configuration effectivement utilisée
pour les deux jobs restent inconnus. Le TIFF `uint8` enregistre une
intensité après sigmoïde, assemblage et quantification, avec une
calibration non attestée. Les cartes et le CT sont sous CC BY-NC 4.0
avec attribution. [Audit Atlas et TIFF](INK_PROVENANCE_AUDIT.md) · [Mainteneur Villa](https://github.com/ScrollPrize/villa/issues/1377#issuecomment-5316476283) · [Droits des données](https://github.com/ScrollPrize/open-data#support-and-citation)

```powershell
.venv/Scripts/python.exe docs/validation/phase7_checkpoints.py data/phase6 docs/validation/phase5-provenance-windows.json docs/validation/phase7-checkpoints.json
```
