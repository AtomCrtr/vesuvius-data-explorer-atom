# Phase 11 · Indépendance de Frag4 vis-à-vis du checkpoint A

**Le checkpoint A correspond, par trois identifiants indépendants, à une configuration publique du script d'entraînement Villa. Dans cette configuration, Frag4 et tous les fragments `Frag*` sont absents de la liste d'entraînement, et le segment de validation est un segment de PHerc0139.** L'exclusion directe de Frag4 devient probable, mais elle n'est pas démontrée pour le poids exact, et l'ascendance des étiquettes et du pré-entraînement reste inconnue. Toute mesure d'encre de A sur Frag4 resterait **exploratoire**.

## Concordances entre A et le script public

Script : `ink-detection/train_resnet3d_3d_decoder.py`, ajouté le 22 avril 2026 (commit `94602c91`, PR #820), déplacé sans modification dans `deprecated/` le 17 août 2026 (`af8bac80`). Les deux versions sont identiques octet pour octet. [Source au commit de main `c8f3ba45`](https://github.com/ScrollPrize/villa/blob/c8f3ba45304f0a317a49a155929e30d294f201eb/deprecated/ink-detection/train_resnet3d_3d_decoder.py)

| Identifiant | Checkpoint A | Script | Concordance |
| --- | --- | --- | --- |
| Nom d'origine | `r152_3ddec_v2_l5_0_crop_0_fr_i3depoch=13.ckpt` (README Villa, carte du modèle) | `f'r152_3ddec_v2_{fid}_{fold}_fr_{enc}'+'{epoch}'`, `fragments=['l5_0_crop']` | Exacte avec fid `l5_0_crop`, fold 0, enc `i3d` |
| `pred_shape` | [4608, 13824] | forme complétée de `0139_2um/l5_0_crop_inklabels.png` | Cohérente (non vérifiable sans le fichier) |
| Pas | `total_steps` 8 089, `global_step` 113 246 à l'époque 13 | `total_steps=len(train_loader)` | 8 089 × 14 = 113 246, exact |
| Normalisation | `with_norm: true` | `with_norm=True` | Exacte |

## Données d'entraînement de cette configuration

`TRAIN_FRAGMENT_IDS` contient 24 identifiants : segments 2 µm de PHerc0139 (`l2_0_crop`, `w028`–`w030`), PHerc0841 (`w00`, deux `auto_grown`), PHerc0814 (`46527_2um_try2`, `auto_grown_…abf`), PHerc0009B (trois `auto_grown`), Scroll 4 (`l_2`–`l_6`), `Man5outer`, `manb`, `1451`, ainsi que `500p2a`, `658`, `-1` et `20250910185200`. Le segment de validation `l5_0_crop` est exclu des tuiles d'entraînement par le code.

- **Frag4, PHercParis1 et tout `Frag*` sont absents de la liste.** Une branche de prétraitement `frag4` existe pourtant (`layer_range=(22, 46)`, `xyz_scale=2`), ce qui montre que Frag4 a servi dans d'autres expériences du même code.
- **`500p2a` (très probablement PHerc0500P2, avec `reverse_layers=True`) et `-1` (nom d'un segment PHerc0500P2 du Data Browser) figurent dans l'entraînement.** Les mesures des phases 5 à 10 sur PHerc0500P2 portent donc sur un fragment très probablement vu par A, même si le segment `wrap01_0919` lui-même n'est pas listé. Ce point doit figurer dans toute note communautaire.

## Ce qui reste inconnu

| Question | Pourquoi elle compte |
| --- | --- |
| La liste publiée est-elle exactement celle du run qui a produit A ? | Le script peut avoir été édité entre le run et le commit. Les segments les plus récents de la liste datent de février 2026, le commit d'avril : c'est plausible, pas prouvé. |
| D'où viennent les étiquettes des 24 segments ? | Les étiquettes 2 µm proviennent de chaînes de pseudo-étiquetage. Si un modèle antérieur entraîné sur Frag4 a produit des pseudo-étiquettes, Frag4 contamine A indirectement. |
| Pré-entraînement | `r3d152_KM_200ep.pth` est chargé avant l'entraînement ; le dossier d'inférence historique s'appelle `pretraining_all_3d_decoder_v2`. Le contenu de ce pré-entraînement n'est pas documenté. |
| Utilisation de Frag4 pour la sélection de modèle ou d'hyperparamètres | Une sélection sur Frag4 fausserait aussi l'évaluation. |

La réserve Kaggle de 2023 ne dit rien de ces trois points : elle concerne un concours antérieur à A.

## Conclusion et demande à formuler

Frag4 est le meilleur candidat public disponible, avec une exclusion directe **probable**. Pour une mesure de généralisation défendable, il faut une attestation des mainteneurs liée au SHA-256 `36dd0de8…` couvrant la liste exacte du run, l'ascendance des étiquettes et le pré-entraînement. Le brouillon de demande de la phase 10 doit être complété par ces trois questions et par la question de normalisation de la [fiche de compatibilité](PHASE11_CHECKPOINT_COMPATIBILITY.md). Aucun envoi n'a été fait.
