# Vesuvius Explorer · Phase 11

**Premier résultat défendable sur Frag4 : la chaîne CT natif → maillage → volume de surface est validée sous le quart de voxel, et la sensibilité du checkpoint A à l'ordre Z se retrouve sur un second fragment.** Le recalage de l'IR sur le CT, en revanche, n'atteint pas le seuil fixé (≈ 50 µm médian contre 6,5 µm exigés) ; aucune métrique d'encre n'a été calculée et les étiquettes n'ont pas été ouvertes. La revue du code ne trouve aucun défaut bloquant, mais révèle que A a très probablement été entraîné sur PHerc0500P2.

## Réponses

| Question | Réponse | Détail |
| --- | --- | --- |
| Le code de Codex est-il fiable ? | Oui pour le paquet ; risque concentré dans ~40 scripts expérimentaux peu testés. | [Revue](CLAUDE_FULL_REVIEW.md) |
| Problèmes critiques ? | P0 scientifique : PHerc0500P2 très probablement dans l'entraînement de A. Aucun P0 dans le code. | [P0](CLAUDE_FULL_REVIEW.md#p0) |
| Gains Rust et S3/Dask bien mesurés ? | Oui pour ce qu'ils affirment, N = 3, sans intervalle, non reproductibles sans les données locales. | [Revue](CLAUDE_FULL_REVIEW.md) |
| Géométrie cohérente ? | Oui ; le signe de `grid_normals` est maintenant documenté et testé. | [P1-1](CLAUDE_FULL_REVIEW.md#p1) |
| Recalage CT–IR vérifiable sur Frag4 ? | Partiellement : CT → surface validé (< 0,25 voxel) ; surface → IR mesuré sur une fissure et le contour seulement. | [Recalage](PHASE11_FRAG4_REGISTRATION.md) |
| Quelle erreur ? | CT → surface : < 0,8 µm. Surface → IR : 52 µm médian [32 ; 65] perpendiculairement à la fissure supérieure, biais 13 µm ; contour ≤ ~200 µm RMS. | [Recalage](PHASE11_FRAG4_REGISTRATION.md) |
| Checkpoint A compatible ? | Exécutable après rééchantillonnage, mais hors recette : air ≈ 0,48 au lieu de 0, pas réel 3,05–4,09 µm, normalisation ÷ 255/÷ 200 non résolue. | [Compatibilité](PHASE11_CHECKPOINT_COMPATIBILITY.md) |
| Évaluation indépendante possible ? | Pas encore : Frag4 absent de la liste publique d'entraînement concordante avec A, mais ascendance des étiquettes et pré-entraînement inconnus. | [Indépendance](PHASE11_TRAINING_INDEPENDENCE.md) · [Évaluation bloquée](PHASE11_INK_EVALUATION.md) |
| Sensibilité Z retrouvée ? | Oui : Spearman 0,03 et −0,08, top 1 % disjoints dans les deux ROI ; réponse structurée seulement de l'air vers le papyrus. | [Z](PHASE11_Z_GENERALIZATION.md) |
| Premier résultat défendable ? | La chaîne géométrique validée de Frag4, ses pièges documentés (PPM identité, pas non isométrique, S3 vide) et la reproduction de l'effet Z sur un second fragment à face connue. | — |
| Que partager ? | La note de méthode corrigée, après accord. | [Note](PHASE11_COMMUNITY_NOTE.md) |
| Prochaine expérience ? | Évaluation Frag4 à tolérance spatiale et fenêtre d'intensité gelées, en parallèle de la demande d'attestation. | [Feuille de route](ROADMAP_SCIENTIFIC_NEXT_STEPS.md) |
| Logiciel, modèles ou validation ? | Validation scientifique d'abord. | [Feuille de route](ROADMAP_SCIENTIFIC_NEXT_STEPS.md) |

## Décisions du 21 novembre

Tolérance de recalage de **301 µm** (biais + 3σ robuste des résidus de fissures), fenêtre d'intensité **W2** fixée sur le CT seul (W1, air → 0, écartée : elle écrêtait 33 % du papyrus), protocole d'évaluation gelé avant les étiquettes, et note envoyée aux mainteneurs. Avec W2, l'expérience Z garde le même schéma (Spearman 0,027 et −0,006, top 1 % disjoints). [Décisions](PHASE11_DECISIONS.md) · [Protocole gelé](validation/phase12-protocol.json)

## Modifications du code

- `core/volume.py` : `dl.ash2txt.org` ajouté aux hôtes HTTPS autorisés (seul serveur du CT des fragments EduceLab) ; message de `core/tifxyz.py` dérivé de la liste.
- `core/alignment.py` : convention de signe de `grid_normals` documentée.
- `core/optical_registration.py` : `registration_tolerance`, tolérance spatiale pour une référence optique grossière.
- Tests : `test_registration_tolerance_follows_robust_spread_and_reference_resolution`, `test_legacy_data_server_is_accepted`, `test_core_normal_is_opposite_to_the_vc3d_xyz_normal`, `tests/test_phase11.py` (deux tests de conventions des scripts).
- Scripts : `docs/validation/phase11_inventory.py`, `phase11_geometry.py`, `phase11_ir_registration.py`, `phase11_cracks.py`, `phase11_z_frag4.py`.

## Vérification

Windows natif, Python 3.11 : **359 tests réussis**, 1 ignoré, 8 réseau désélectionnés ; `ruff check .` propre. Avec `VESUVIUS_RUST_SAMPLER=1`, 65 tests ciblés réussis. Journaux locaux sous `data/phase11/`. Inférence : torch 2.8.0+cu126, RTX 4080 Laptop, FP32 déterministe, répétition au bit près.

Pendant la session, un autre processus a commité `04c63d8` (« Corriger le test napari dans la CI sans Qt », `qtbot` rendu facultatif dans `tests/test_optical_registration.py`) et y a placé `feat/vesuvius-phase10` et son suivi distant. La branche de phase 11 part de ce commit ; il ne provient pas de cette phase.

## Reproduction

```powershell
$py = '.venv/Scripts/python.exe'; $gpu = 'data/phase6-cuda/Scripts/python.exe'
& $py -I docs/validation/phase11_inventory.py docs/validation/phase11-frag4-inventory.json
# Téléchargements 2D : voir PHASE11_FRAG4_DATA_AUDIT.md (URL et SHA-256), dans data/phase11/raw/
& $py docs/validation/phase11_geometry.py data/phase11 docs/validation/phase11-geometry-ppm.json
& $py docs/validation/phase11_ir_registration.py data/phase11 docs/validation/phase11-ir-registration.json
& $py docs/validation/phase11_cracks.py data/phase11 docs/validation/phase11-cracks.json
& $py docs/validation/phase11_z_frag4.py data/phase11 --prepare
& $gpu docs/validation/phase11_z_frag4.py data/phase11
& $py docs/validation/phase11_z_frag4.py data/phase11 --report docs/validation/phase11-z-frag4.json
```

L'archive locale `data/phase11/phase11-reproduction.zip` réunit scripts, JSON et manifeste d'empreintes, sans aucune donnée Frag4, conformément à la licence EduceLab. [Manifeste](validation/phase11-manifest.json)
