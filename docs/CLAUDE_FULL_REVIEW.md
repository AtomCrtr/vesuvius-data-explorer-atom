# Revue technique et scientifique de Vesuvius Explorer · phases 1 à 10

Revue de la branche `feat/vesuvius-phase10` (`dbac5b6`), menée en phase 11. Elle sépare ce qui a été **revérifié** pendant cette revue de ce qui est seulement **rapporté** dans la documentation.

**Verdict.** Le code est fiable pour ce qu'il prétend faire : lecture bornée des volumes, géométrie TIFXYZ, noyau Rust, inférence épinglée. Aucun défaut bloquant n'a été trouvé dans le code. Le problème critique est scientifique : le checkpoint A a très probablement été entraîné sur PHerc0500P2, le fragment de toutes les expériences des phases 5 à 10. L'application est prête pour des expériences plus ambitieuses ; ce qui manque, c'est une référence d'encre indépendante et un protocole gelé avant les mesures.

## Ce qui a été revérifié

| Élément | Méthode | Résultat |
| --- | --- | --- |
| Suite de tests | Windows natif, Python 3.11, `.venv` | 355 réussis avant modification, **359** après (1 ignoré, 8 réseau désélectionnés). `ruff check .` propre. [Journal](../data/phase11/windows-tests.log) (local) |
| Noyau Rust | `VESUVIUS_RUST_SAMPLER=1`, tests ciblés ; lecture de `rust/src/lib.rs` | 65 réussis. Interpolation et bornage identiques au chemin Python (`core/chunkcache.py:141-163`), aucun `unsafe`, entrées non finies renvoyées vers Python. |
| Checkpoint A | SHA-256, métadonnées, statistiques de `BatchNorm` relues | Conformes au rapport de phase 6. Nouvelles concordances avec le script Villa, voir [indépendance](PHASE11_TRAINING_INDEPENDENCE.md). |
| Chargement sûr | `docs/validation/phase6_cuda.py:96-125` | Empreintes du code et des poids vérifiées avant `torch.load(..., weights_only=True)` ; cuDNN déterministe, TF32 désactivé. |
| Recalage par repères | `core/optical_registration.py` | SVD rigide avec parité explicite, repères réservés, enveloppe convexe, leave-one-out, critère de qualité. Correct. |
| Conventions de normale | Calcul indépendant | `core/alignment.py:46` donne l'opposé de la normale XYZ de VC3D ; les scripts d'orientation des phases 7–10 utilisent bien la XYZ. Documenté et testé. |
| Accès aux données | Ouverture réelle de Frag4 | Refus de `dl.ash2txt.org` corrigé ; Zarr Frag4 ouvert et lu. |

**Non revérifié** (rapporté seulement) : chronométrages S3/Dask et napari, gains Rust 4,90×, reproduction du TIFF A publié à un niveau près, statistiques spatiales de phase 8. Leurs scripts et JSON existent, mais ils dépendent de répertoires `data/phaseN/` absents du dépôt public ; un tiers ne peut pas les relancer tels quels.

## Points forts

- **Discipline de reproductibilité** rare pour un projet de cette taille : épinglage du code amont par commit et SHA-256, poids vérifiés avant chargement, CUDA déterministe et rejoué dans un second processus, archives de restauration par phase.
- **Géométrie prudente** : conventions de niveaux restreintes aux sources vérifiées (`core/geometry.py:30`), lecture TIFXYZ par plages avec budget d'octets, refus d'écraser un segment (`core/tifxyz.py:333`).
- **Rust à sa juste place** : optionnel, désactivé par défaut, testé en parité, construit et testé en CI sur Linux et Windows.
- **Sécurité des entrées** : liste blanche d'hôtes HTTPS, S3 anonyme, `allow_pickle=False`, `meta.json` plafonné à 1 Mio, `weights_only=True`.
- **Langage scientifique** : les rapports séparent observation et hypothèse et n'annoncent aucune lecture.

## P0 · Critiques

<a id="p0"></a>

| ID | Problème | Preuve | Action |
| --- | --- | --- | --- |
| P0-S1 | **PHerc0500P2 très probablement dans l'entraînement de A.** La configuration publique qui concorde avec A sur trois identifiants liste `500p2a` (avec `reverse_layers=True`) et `-1`. Les comparaisons A/B, l'intervention Z et toute future évaluation d'encre sur PHerc0500P2 portent sur des données vues par A. | `deprecated/ink-detection/train_resnet3d_3d_decoder.py`, `TRAIN_FRAGMENT_IDS` et `get_training_segment_kwargs`, commit `c8f3ba45` | Corriger la note communautaire avant tout partage (fait dans [la note de phase 11](PHASE11_COMMUNITY_NOTE.md)). Ne plus présenter PHerc0500P2 comme candidat d'évaluation pour A. |

Aucun P0 dans le code.

## P1 · Importants

<a id="p1"></a>

| ID | Problème | Fichiers | État |
| --- | --- | --- | --- |
| P1-1 | Signe de `grid_normals` opposé à la convention XYZ de VC3D, non documenté. Risque de signe lors de toute comparaison entre décalages T10 et rapports d'orientation. Changer le signe modifierait les cartes T10 publiées. | `src/vesuvius_data_explorer/core/alignment.py:46` | **Corrigé** : docstring et `tests/test_alignment.py::test_core_normal_is_opposite_to_the_vc3d_xyz_normal`. |
| P1-2 | `dl.ash2txt.org` refusé : impossible d'ouvrir le CT des fragments EduceLab, publiés seulement sur ce serveur. | `core/volume.py:34`, message de `core/tifxyz.py:72` | **Corrigé** avec test `tests/test_data_access.py::test_legacy_data_server_is_accepted`. |
| P1-3 | La logique expérimentale (préparation des tuiles, inférence, fusion, statistiques) vit dans ~40 scripts `docs/validation/` presque sans tests ; leurs entrées sont dans `data/`, absent du dépôt. Six rapports pointent vers `../data/…`, liens morts sur GitHub. | `docs/validation/phase*_*.py`, `docs/VESUVIUS_PHASE*.md` | Ouvert. Extraire la recette d'entrée et l'inférence en module testé (tâche Codex T1). |
| P1-4 | Normalisation : entraînement ÷ 255 (défaut d'`A.Normalize`) contre production ÷ 200, devant une `BatchNorm3d` figée. Non tranché par les statistiques du checkpoint. | Script Villa l. 150-159 ; `optimized_inference/inference.py:102` | Question aux mainteneurs. [Détail](PHASE11_CHECKPOINT_COMPATIBILITY.md) |
| P1-5 | Le critère de recalage (RMS < 2 px CT) ignore la résolution de la référence optique ; il est inatteignable avec l'IR Frag4 (≈ 20 µm/px). | `core/optical_registration.py:92` | Décision : critère fondé sur la résolution de la référence (`max(2 px CT, k × px optique)`). |
| P1-6 | Les déviations de protocole sont documentées a posteriori. Il manque un gel horodaté (fichier de protocole haché et commité avant les mesures). | Phases 9–11 | Ouvert (tâche Codex T3). |

## P2 · Améliorations

| ID | Constat | Fichiers |
| --- | --- | --- |
| P2-1 | Le cache disque ne conserve pas les lectures par plages d'octets : zarr 3.1.6 les garde en mémoire. Pour un Zarr v3 shardé, le gain du cache persistant ne s'applique pas ; les mesures de phase 3 portent sur des volumes v2 par blocs. | `core/cache.py:131-152`, `zarr/experimental/cache_store.py` |
| P2-2 | Clé de cache = URI seule ; un objet réécrit à la même adresse reste servi jusqu'à 30 jours. Acceptable pour des volumes immuables, à documenter. | `core/cache.py:62` |
| P2-3 | Pyramides à formes arrondies vers le haut (Frag4 : 9 231 → 4 616) : facteur historique 1,99978 au lieu de 2, soit ≈ 0,1 voxel au bout de l'axe au niveau 1. Négligeable ; ajouter Frag4 aux sources vérifiées après contrôle. | `core/geometry.py:9-21` |
| P2-4 | Gains de performance mesurés avec N = 3 répétitions, sans intervalle, sur une machine, parfois sur géométries synthétiques. Corrects pour ce qu'ils affirment ; pas généralisables. | `docs/S3_DASK_PROFILING.md`, `docs/RUST_BENCHMARKS.md` |
| P2-5 | Intervalles par blocs de 64² optimistes : l'autocorrélation spatiale dépasse la taille de bloc. Ajouter une analyse de sensibilité à la taille de bloc. | `core/ink_spatial.py:17` |
| P2-6 | Le Data Browser annonce CT et surfaces de PHercParis1Fr39 sur S3 ; le préfixe ne contient qu'une photo. Signalable aux mainteneurs. | — |

## P3 · Facultatif

- `_READ_SINCE_PRUNE` est un compteur global non synchronisé (`core/cache.py:176`) : sans conséquence au-delà d'un élagage plus ou moins tôt.
- `ink_spatial.effect` divise par `selected.sum()` (`core/ink_spatial.py:58`) : division par zéro si la sélection est vide sur un très petit support.
- JSON de profilage de ~1 Mio versionnés (`docs/validation/phase3-profile-*.json`) : déplacer vers des artefacts de release.

## Dette technique

Scripts ponctuels nombreux et couplés à des chemins locaux (`data/phase6/villa`) ; documentation très dense, en français et en anglais, avec des chiffres répétés d'un rapport à l'autre ; logique d'inférence dupliquée entre `phase6_cuda.py`, `phase7_experiment.py`, `phase8_cuda.py` et `phase11_z_frag4.py`. Aucune de ces dettes ne justifie une refonte avant la validation scientifique ; T1 en traite l'essentiel.

## Limites scientifiques

1. En dix phases, **aucune mesure d'encre contre une vérité indépendante** n'a été produite. La phase 11 n'en produit pas non plus, faute de recalage et d'indépendance suffisants.
2. PHerc0500P2 est très probablement dans l'entraînement de A (P0-S1). Les poids B restent inaccessibles.
3. Les effets Z sont mesurés sur un segment de PHerc0500P2 et deux ROI de Frag4 : deux fragments, un seul modèle.
4. La face anatomique de `wrap01_0919` reste inconnue ; celle de Frag4 est connue (surface exposée), ce qui en fait le meilleur banc pour l'ordre Z.
5. Les seuils et fenêtres ont parfois été ajustés après observation de résultats intermédiaires (déclaré en phase 11).

## Réponses aux questions techniques

1. **Le code de Codex est-il fiable ?** Oui pour le cœur du paquet. Le risque se concentre dans les scripts expérimentaux non testés.
2. **Problèmes critiques restants ?** Aucun dans le code ; P0-S1 côté science, puis P1-3 à P1-6.
3. **Gains Rust et S3/Dask bien mesurés ?** Oui pour ce qu'ils affirment (parité vérifiée, mêmes octets utiles), avec de petits effectifs et sans intervalle ; non reproductibles par un tiers sans les données locales.
4. **Transformations géométriques cohérentes ?** Oui. La chaîne PPM → CT de Frag4 a été validée sous 0,25 voxel ; la seule incohérence, le signe de `grid_normals`, est documentée.
5. **Prêt pour des expériences plus ambitieuses ?** Oui côté logiciel. Prochaine priorité : la validation scientifique, pas de nouvelles fonctions.

## Actions prioritaires

1. Corriger la note communautaire (fait) et ne l'envoyer qu'après accord.
2. Demander aux mainteneurs l'attestation d'entraînement de A, la normalisation et l'ordre Z attendu.
3. Geler le protocole d'évaluation Frag4 (tolérance, fenêtre d'intensité) avant d'ouvrir les étiquettes.
4. Codex : T1 (module d'inférence testé), T2 (rééchantillonnage au pas réel de la PPM), T3 (gel de protocole).
