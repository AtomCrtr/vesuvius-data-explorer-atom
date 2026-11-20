# Passation à Claude Opus

## Phase 12 · Première évaluation d'encre de A sur Frag4

Branche `feat/vesuvius-phase12`, créée depuis `main` (`e13fc36`). Le protocole (`5c0602f`) et le script (`f9c965d`) ont été commités avant l'ouverture des étiquettes. [Rapport](PHASE12_INK_EVALUATION.md)

- **H1 et H2 rejetées.** Z_in (air → papyrus) est au niveau du hasard : ROC-AUC 0,49 et 0,40, PR-AUC sous la prévalence.
- **Exploratoire.** Z_out classe l'encre (ROC-AUC 0,86 et 0,89 ; PR-AUC 3,4 et 4,5 × la prévalence), sans jamais dépasser 0,5. Le résultat est stable entre les fenêtres W2 et `>> 8`. L'intensité brute plafonne vers 0,64 (contrôle a posteriori).
- **Métriques au pixel indéfinies.** Aucun trait d'encre n'est plus large que deux fois la tolérance de 301 µm.
- **Correction déclarée.** Un bug de la bande de tolérance a été corrigé après le premier passage ; les rangs sont inchangés.
- **Suite.** Pré-enregistrer H3 (Z_out au-dessus du hasard) sur de nouvelles ROI de Frag4, puis sur Frag1 et Frag3. Les ROI 2 et 5 sont désormais vues. Le complément à villa#2627 est rédigé mais pas envoyé. [Complément](PHASE12_COMMUNITY_FOLLOWUP.md)

## Phase 11 · Revue complète et premier contrôle multimodal sur Frag4

Branche locale `feat/vesuvius-phase11`, créée depuis `feat/vesuvius-phase10` (`dbac5b6`). [Bilan](VESUVIUS_PHASE11.md)

- **Revue.** Code fiable, aucun P0 logiciel. P0 scientifique : la configuration Villa qui concorde avec A sur trois identifiants liste `500p2a` et `-1` dans l'entraînement, donc PHerc0500P2 est très probablement vu par A. Deux P1 corrigés (hôte `dl.ash2txt.org`, signe de `grid_normals` documenté). [Revue](CLAUDE_FULL_REVIEW.md)
- **Géométrie Frag4.** La PPM `extras/PHercParis1Fr39_54keV.ppm` relie l'UV au CT recadré publié sans décalage ; couches = `p + (k − 32)·n`, trilinéaire, résidu < 0,25 voxel. La PPM `…_surface_volume.ppm` est une identité. La normale sort du papyrus. Pas non isométrique (0,94–1,26 voxel/px). [Recalage](PHASE11_FRAG4_REGISTRATION.md)
- **IR.** Résidu ≈ 52 µm médian perpendiculairement à la fissure supérieure, contour ≤ ~200 µm RMS ; seuil de 6,5 µm non atteint et inatteignable (IR natif ≈ 20 µm/px). Étiquettes non téléchargées, métriques d'encre bloquées. [Évaluation](PHASE11_INK_EVALUATION.md)
- **A sur Frag4.** Hors recette (air ≈ 0,48 après `>> 8`, normalisation ÷ 255/÷ 200 ouverte). Inversion Z : Spearman 0,03 et −0,08, top 1 % disjoints ; réponse seulement de l'air vers le papyrus. [Compatibilité](PHASE11_CHECKPOINT_COMPATIBILITY.md) · [Z](PHASE11_Z_GENERALIZATION.md)
- **Décisions du 21 novembre.** Tolérance 301 µm, fenêtre W2 (moments ajustés sur la recette), protocole d'évaluation gelé, note envoyée : [villa#2627](https://github.com/ScrollPrize/villa/issues/2627). Avec W2, l'effet Z est inchangé. [Décisions](PHASE11_DECISIONS.md)
- **Suite.** Ouvrir les étiquettes selon le protocole gelé et évaluer Frag4 en exploratoire ; demander l'attestation d'entraînement. Tâches Codex T1–T5. 359 tests natifs et 65 ciblés Rust réussis. [Feuille de route](ROADMAP_SCIENTIFIC_NEXT_STEPS.md) · [Note communautaire, envoyée](PHASE11_COMMUNITY_NOTE.md)

## Phase 10 · Provenance CT–IR et préparation du pilote indépendant

Branche locale `feat/vesuvius-phase10`, avec un point de restauration vérifié de la phase 9. [Bilan](VESUVIUS_PHASE10.md)

- **Source retrouvée.** Le JPEG public Naples M1050 IR n° 017 est bien dans la collection multispectrale de PHerc0500P2. Le frontal historique diffuse 66 couches, de l’IR aligné et des masques sur 14 990 × 27 160 pixels. Ces dimensions diffèrent du Zarr Atlas. Aucune emprise ni paire de repères de ν2 n’est documentée. La calibration du champ reste ouverte. [Vérification](PHASE10_SOURCE_INVESTIGATION.md)
- **Reprise conditionnelle.** Obtenir l’emprise et la face du champ `500P2_230925_N2`, les points IR→CT ou la transformation et sa révision, ainsi que l’étalonnage original. Les 4,42 mm de phase 9 comparent des nœuds de deux maillages précis et laissent ouverte la position de ν2. Deux brouillons en anglais attendent accord. [Éléments manquants](PHASE10_REGISTRATION_EVIDENCE.md) · [Demandes](PHASE10_AUTHOR_CONTACT.md)
- **Autre jeu.** PHercParis1Fr39 est **Frag4**. La pile 54 keV, l’IR, les masques et artefacts d’alignement sont publics. La réserve Kaggle n’atteste pas l’exclusion du checkpoint A. Préparer un contrôle CT/IR borné puis demander le manifeste d’entraînement avant les métriques. [Classement](PHASE10_ALTERNATIVE_DATASETS.md)
- **Relecture et contribution.** R02 et R04 ont un dossier neutre enrichi de cubes CT natifs et d’une fiche d’observation. La note de méthode en anglais détaille ce que l’intervention à A fixe apporte à Villa #1377. Rien n’a été publié. 355 tests natifs et 80 ciblés avec Rust ont réussi. [Relecture et journaux](VESUVIUS_PHASE10.md) · [Note de méthode](PHASE10_COMMUNITY_REPORT.md)

## Phase 9 · Recalage CT–optique de PHerc0500P2

Branche locale `feat/vesuvius-phase9`, avec 137 fichiers dans le point de restauration de phase 8. [Bilan et reproduction](VESUVIUS_PHASE9.md)

- **Optique.** Seul ν2 a été téléchargé. Les axes numériques donnent 0,68793625 µm/pixel, contre 0,34 µm/pixel dans l’article. La calibration instrumentale reste à obtenir. Les quatre fichiers concordent avec les SHA-256 LFS. Le TIFF RGB présente un type TIFF incohérent. Le décodeur de validation lit ses bandes uint8 après contrôle, en conservant l’original. [Audit](PHASE9_PROFILOMETER_AUDIT.md)
- **Géométrie.** Le frontal `20250628074500-500P2_front` et le segment `wrap01_0919` sont séparés d’au moins 4,42 mm entre nœuds sondés sur deux révisions frontales. La recherche grossière sur le composite CT publié n’isole pas un emplacement de ν2. La face anatomique et l’orientation du champ dans le CT restent indéterminées. [Localisation](PHASE9_CT_OPTICAL_REGISTRATION.md)
- **Évaluation.** Le pipeline par repères structuraux et la mesure d’erreur sont prêts. Le pilote réel reste sans transformation ni métrique d’encre. Le préprint documente l’entraînement d’une autre famille sur PHerc0500P2. Les provenances du poids A exact et de ses dérivés restent inconnues. [Géométrie](PHASE9_GEOMETRIC_UNCERTAINTY.md) · [Indépendance](PHASE9_DATA_INDEPENDENCE.md)
- **Relecture.** Le panneau napari charge le CT et l’optique dans des repères distincts, avec annotation et prédictions masquées à l’ouverture. Les cubes indépendants de R02 et R04 sont exportés. 355 tests natifs, 80 ciblés avec Rust et 8 tests réseau ont réussi. [Session et dossier CT](VESUVIUS_PHASE9.md#reproduction-windows)

Demander la photo de situation de `500P2_230925_N2` en lien avec Naples M1050 IR n° 017, les points IR→CT du frontal, la calibration du profilomètre et le manifeste d’entraînement lié au SHA-256 d’A. Ces pièces serviront à vérifier où se trouve le champ et si ses données dérivées recoupent l’entraînement.

## Phase 8 · Support spatial, orientation et validation indépendante

Branche locale `feat/vesuvius-phase8`. Le ZIP `data/phase8/phase7-before-phase8.zip` et son manifeste préservent l’état de travail de la phase 7 et les artefacts repris. [Bilan et restauration](VESUVIUS_PHASE8.md)

- **Sensibilité spatiale.** La grille couvre 110 cellules, dont 61 satisfont le critère de support. Sur 790 200 pixels valides, Spearman A+/A− vaut 0,021 et l’écart absolu moyen 0,247, intervalle par blocs 64² [0,209 ; 0,283]. Au-delà de 16 pixels du bord, la moyenne vaut 0,255. L’inclusion mécanique du fond à zéro ferait monter Spearman à 0,870. La distance au bord et le taux de support sont modérément associés aux écarts. [Mesures](PHASE8_SPATIAL_ROBUSTNESS.md)
- **Orientation.** Six nouveaux témoins CT confirment `−N` pour la profondeur croissante. Le masque public de recto `0500p2_5217` cite le même scan et ne contient pas d’étiquette dans les six voisinages sondés. La face reste indéterminée. [Contrôle](PHASE8_PHYSICAL_ORIENTATION.md)
- **Référence d’encre.** EduceLab donne deux contrôles géométriques et six fenêtres exploratoires. Quatre champs optiques annotés couvrent des territoires de PHerc0500P2. Il faut lever la divergence de pas publiée, localiser les champs sur le segment, déterminer la face et obtenir des exclusions d’entraînement par manuscrit. La demande au mainteneur Villa couvre également les poids exacts de B et les empreintes des jobs. Elle reste au stade de brouillon local. [Provenance et expérience prioritaire](PHASE8_INK_VALIDATION.md)
- **Examen.** Commencer la relecture humaine avec les cubes CT de R02 et R04, puis examiner R03 et le témoin R01. La vue napari affiche la sensibilité sur le CT, les mesures par ROI et la provenance. La session du segment entier référence les 61 cellules mesurées. [Relecture et sessions](PHASE8_CANDIDATE_REVIEW.md)
- **Reproductibilité.** 54 nouvelles tuiles non vides calculées dans les deux orientations, 32 reprises vérifiées et 4 tuiles vides. Huit nouvelles tuiles reproduites à l’identique dans un second processus CUDA. Les suites ont validé 347 tests natifs, 8 réseau et 73 avec Rust. [Procédure et journaux](VESUVIUS_PHASE8.md#reproduction)

La prochaine expérience prioritaire est le recalage géométrique d’un champ optique sur le même fragment, avec vérification de la face et de l’erreur sur des repères tenus à l’écart. L’expérience factorielle avec B peut reprendre dès l’obtention du poids et de son empreinte.

## Phase 7 · Contraste Z assemblé et contrôle physique

Branche locale `feat/vesuvius-phase7`. Référence phase 6
préservée dans `data/phase7/phase6-before-phase7.zip`.
[Bilan et restauration](VESUVIUS_PHASE7.md)

- **Poids.** A public correspond au SHA-256 Hugging Face et
  tourne en FP32. Les recherches publiques de B restent vides
  et le registre S3 renvoie HTTP 403 en accès anonyme. Les
  digests des jobs d’origine restent inconnus. B+ et B− ne sont
  pas mesurées. [Audit](PHASE7_CHECKPOINT_AUDIT.md)
- **Intervention.** Les mêmes 32 tuiles sont assemblées pour
  A+ et A−. Sur le recadrage CT, Spearman −0,444 et aucun
  recouvrement jusqu’au top 10 %. A+ retrouve le TIFF A publié
  à un code près. Sur la zone distante le Spearman A+/A−
  remonte à 0,809. L’effet Z dépend du secteur et ne quantifie
  pas la contribution de Z à la différence A/B de production.
  [Mesures](PHASE7_MODEL_COMPARISON.md)
- **Orientation.** Le CT brut confirme le signe `−N` pour
  l’augmentation de Z aux quatre témoins, Pearson 0,991–0,997.
  Le recto/verso anatomique reste inconnu. Les deux processus
  CUDA indépendants reproduisent tous les tableaux.
  [Protocole](PHASE7_Z_ORDER_EXPERIMENT.md)
- **Relecture.** La vue napari 2 × 2 affiche les conditions
  présentes et l’indisponibilité de B±. Le nouveau ZIP garde
  les quatre régions annotées, le CT et quatre cartes.
  [Dossier de relecture](PHASE7_CANDIDATE_REVIEW.md)
- **Tests.** 341 tests Windows natifs, 8 réseau et 73 ciblés
  avec Rust activé. [Bilan](VESUVIUS_PHASE7.md#reproductibilité-et-compatibilité)

Le prochain contrôle est l’expérience croisée avec le poids B
attesté, à résolution, support et assemblage fixes. L’encre
et la face exigent toujours une preuve indépendante.

## Phase 6 · Désaccord, CUDA et relecture

Branche locale `feat/vesuvius-phase6`, base
`eba4082134df544dc56b5f9d6622d9fd0161f36c`. La phase 5 a un
ZIP de restauration vérifié sous `data/phase6-restore/`.
[État et restauration](VESUVIUS_PHASE6.md)

- Sur PHerc0500P2, la distance minimale entre top 1 % est de
  208 pixels en norme de Chebyshev. Les 14 641 translations
  de ±60 px par axe gardent l’intersection vide. Spearman
  vaut 0,636 sur le support commun et 0,952 avec les zéros
  partagés. [Désaccord et géométrie](PHASE6_MODEL_DISAGREEMENT.md)
- CUDA FP32 exécuté en Windows natif avec le poids canonique
  public vérifié. Médianes de 237 et 239 ms par tuile, pic
  réservé de 1,60 Gio, sorties reprises bit à bit dans un
  second processus. Le seul changement d’ordre Z donne un
  top 1 % et 5 % disjoint avec le même checkpoint.
  [Conditions et traces CUDA](CUDA_INFERENCE_VALIDATION.md)
- Les huit fenêtres EduceLab ont des références IR cohérentes
  avec les sources. Aucune séparation des rouleaux d’entraînement
  n’a été attestée. Le ZIP local d’examen propose quatre régions
  sur la grille validée. Il conserve les paramètres d’affichage,
  les TIFF et des statuts renseignés indépendamment.
  [Audit EduceLab](EDUCELAB_INDEPENDENCE_AUDIT.md) · [Dossier candidat](CANDIDATE_REVIEW_PROTOCOL.md)
- Windows natif, 334 tests principaux, 8 réseau et 73 ciblés
  avec Rust activé. [Vérifications](VESUVIUS_PHASE6.md#vérification)

Priorité à l’obtention du poids B, de sa licence et des digests
des deux exécutions. Une fois ces éléments acquis, commencer par
une campagne à deux ordres Z à géométrie identique, avant de
comparer des stratégies d’ensemble.

## Phase 5 · Accord entre modèles et références d’encre

La phase 5 est dans l’arbre de travail de
`feat/rust-explorer-first-kernel`. L’audit Atlas rattache les
cartes A et B de PHerc0500P2 au rendu historique de 2,215 µm,
avec `force-reverse=false` pour A et `true` pour B. Le Jaccard
descriptif de la fenêtre est 0,477 à 50 %, et le top 1 % des
scores sur le support non nul est disjoint. La face anatomique,
le poids exact de B, le digest des images de production et
l’absence de fuite d’entraînement restent à établir.
[Atlas et géométrie](INK_PROVENANCE_AUDIT.md)

- **Application.** Accord par seuil et par rang, distributions,
  zones proches des seuils et pixels manquants dans napari. La
  galerie conserve la région, le modèle, l’observation,
  l’hypothèse et la référence de relecture externe dans les
  exports. Les différences probabilistes exigent une calibration et
  un recalage documentés. [Utilisation](MODEL_CONSENSUS_ANALYSIS.md)
- **Références indépendantes.** Huit fenêtres CT/IR/annotations
  EduceLab locales, dont deux contrôles de bord à relire. La
  figure 3 de Parsons et al. documente la référence papyrologique.
  Ces fenêtres sont pour le contrôle méthodologique, en attente
  d’une preuve d’indépendance des poids. [Données et fenêtres](INK_EVALUATION_DATASET.md)
- **Mesures et suite.** Windows natif, 328 tests réussis et huit
  contrôles réseau réussis sous Python 3.12. Sur
  RTX 4080 Laptop, les calculs CPU prennent 14,3 ms en médiane
  et les bascules OpenGL après la première couche 43 à 56 ms.
  Priorité scientifique au rattachement de la face et des poids
  et à un test par rouleau indépendant. [Bilan et protocole CUDA](VESUVIUS_PHASE5.md)

## Phase 4 · État du lot

Vesuvius Explorer lit et explore les volumes CT publics avec
napari. Python reste le moteur par défaut, Rust/PyO3 est une
accélération optionnelle, et PyTorch/CUDA reste réservé aux
pipelines d’inférence. L’arbre de travail
`feat/rust-explorer-first-kernel` contient les phases 3 et 4.
Le corps de Pull Request est sous `docs/PHASE4_PR.md`.
[Bilan](RUST_PHASE4.md) · [Revue GitHub](PHASE4_PR.md)

- **Géométrie.** Les 24 comparaisons L0–L3 sur trois acquisitions
  et quatre URI publiques retrouvent exactement la moyenne 2³,
  arrondie au pair. En coordonnées de centres L0, la carte est
  `q = (p + 0.5) / 2^L - 0.5`. Le décalage NGFF sans translation
  est 0,4375 voxel à L3. Les formes arrondies faussaient aussi
  le facteur historique, jusqu’à 0,4486 voxel Z dans un rendu
  réel de la phase 4. Les sorties identifient le facteur et la
  convention. Les cas dont la source ou les métadonnées
  divergent conservent le calcul historique. Les projections
  sur deux TIFXYZ publics passent contre un oracle indépendant.
  [Validation et traces](GEOMETRY_VALIDATION.md)
- **Interface.** Les 384–420 ms du rappel d’ajout à froid incluaient
  203–209 ms dans la construction de l’objet `Image` sur Qt.
  Le worker construit maintenant l’objet détaché. Sur trois
  répétitions, le pire intervalle Qt à froid passe de 435 à
  207 ms. L’insertion synchrone reste dominante dans les
  pauses résiduelles. Le chargement est visible et les
  révisions de chemin et de paramètres éliminent les résultats
  obsolètes. [Profil natif](NAPARI_PERFORMANCE_PHASE4.md)
- **Cartes réelles.** PHerc0500P2 `20250919184428`, deux TIFF
  Atlas 8 bits des modèles `20260417190342` et `20260709123958`
  dans la même grille prise sur la pile publique. Quatre
  témoins CT montrent un lien avec le TIFXYZ historique
  (`r ≥ 0,966`) plus fort qu’avec t2. La révision exacte et
  la face de chacun des deux calculs d’encre restent inconnues.
  Le panneau a affiché différence, consensus et désaccord
  et exporté une ROI avec provenance. Jaccard positif 0,477
  au seuil de 50 % sur la fenêtre fixée. Ce chiffre mesure
  l’accord des scores, sans vérité d’encre indépendante.
  [Catalogue, résultats et campagne RTX](INK_MODEL_COMPARISON.md)
- **Tests.** Suite Windows native avec moteur Python par défaut
  et tests de parité Rust. 317 réussites en Python 3.11.
  Sous Python 3.12, 82 tests ciblés et les huit tests
  réseau passent, dont le contrôle public `vc-delta3d`.
  [Commandes et environnement](RUST_PHASE4.md)

## Phase 4 · Reprise recommandée

1. Vérifier les métadonnées des rendus, la face et la révision
   de chaque TIFF avant la comparaison à une annotation
   indépendante. Un résultat de consensus reste un candidat.
   La seule égalité de dimensions ne suffit pas.
2. Qualifier Reader V3 et le second modèle public sur la même
   pile native ~9 µm. Vérifier les exclusions de tous les
   ancêtres des checkpoints, puis geler le partage par rouleau.
   Le protocole propose PHerc0841 en validation et PHerc1447
   en évaluation, sous réserve de cet audit. Lancer le pilote
   batch 1 sur la RTX 4080 Laptop, puis mesurer exactitude,
   faux positifs, mémoire et latence sur les fenêtres gelées.
3. Vérifier les niveaux supérieurs à L3 et les pyramides
   d’autres producteurs avant de changer les règles par
   défaut. Pour les sorties alignées déjà publiées, garder
   les empreintes et relire les cas proches des seuils T10.
4. Instrumenter les rappels restants lors de l’insertion
   du calque, à chaud en particulier. Conserver les
   manipulations Qt/Vispy sur le thread graphique.

## Historique

Les mesures et décisions des phases 2 et 3 suivent.

## Phase 3 · Résultats démontrés

- Sur `feat/rust-explorer-first-kernel`, réduire les requêtes
  avant d’envisager un lecteur Rust. Chaque niveau est résolu une
  fois, les niveaux indépendants sont lus en parallèle et s3fs
  ouvre les petits objets en un GET. Sur trois répétitions
  PHerc0800, médiane des métadonnées de 4,13 à 1,54 s à froid et
  de 3,24 à 0,41 s à chaud. La première trame passe de 15,16 à
  5,49 s à froid et de 4,63 à 1,11 s à chaud, avec la même
  empreinte des coupes et le même nombre d’octets CT utiles.
  [Protocole et mesures brutes](S3_DASK_PROFILING.md)
- Zarr v3 shardé publié de PHercParis4 `20260310170716` et copie
  v2 identiques sur les ROI des niveaux 0, 1 et 3. CT EduceLab
  `uint16` de `20230205180739` conservé exactement après
  réencodage local v3 shardé. Cinq rendus de cellules de
  surfaces publiées identiques entre Python et Rust. La roue
  est facultative et l’extra codec nécessite Python 3.12.
  [Validation et contrôles](ZARR_V3_UINT16_VALIDATION.md)
- Le panneau compare deux cartes sur la même grille. Il
  propose opacité, désaccord au seuil, ROI, capture PNG avec
  coordonnées et session JSON avec contrôle des sources. Les
  annotations représentent des caractères candidats en attente
  de validation indépendante. [Guide](COMPARAISON_PREDICTIONS.md)
- La suite Qt Windows avec Rust actif compte 312 réussites.
  Le test du volume public `vc-delta3d` passe séparément
  en Python 3.12. [Bilan](RUST_PHASE3.md)

## Phase 3 · Limites et suite

1. Vérifier sur des repères indépendants la convention de centres
   et de translations NGFF des volumes publics avant de changer
   l’échantillonnage T10. Le plus grand écart relevé entre le
   calcul historique et l’échelle seule est de 0,4375 voxel de
   niveau à L3. Étendre la campagne à une publication Zarr
   distante nativement `uint16`.
2. Dans napari, le p95 de la minuterie Qt reste proche de 17 ms
   avec des pauses ponctuelles jusqu’à 444 ms. Comparer une vue
   progressive L5 → L4 avec la même position, puis profiler
   individuellement l’ajout de calque et le rendu. Les 36 GET
   de réouverture restants sondent des clés absentes. Mesurer
   l’effet d’un TTL négatif court et son invalidation sur un
   store qui publie un nouveau bloc. La VRAM WDDM de 32,44 Mio
   est un relevé ponctuel après la vue à chaud.
3. Évaluer le panneau sur deux cartes d’encre réelles issues
   d’une même pile UV orientée. Archiver les paramètres de
   génération et faire relire les désaccords et candidats
   selon un protocole indépendant.

Le profil de panne injecte l’erreur avant l’appel S3. Un essai
de coupure TCP en cours de transfert sera nécessaire pour
quantifier le comportement du SDK pendant ses tentatives.
[Bilan et reproductibilité](RUST_PHASE3.md)

## Décision après la phase 2

Conserver Rust en option sur les blocs CT entiers. Sur huit recadrages réels de PHerc0814, PHerc0500P2 et PHerc0139, les rendus et les coordonnées recalées coïncident. L’écart maximal est de 2,84 × 10⁻¹⁴ unité CT sur un profil. La carte gagne jusqu’à 4,90× et le chemin de rapport complet jusqu’à 2,33×. Sur le plus grand essai de rapport, le RSS passe de 250 à 158 Mio. Ces résultats couvrent Zarr v2 `uint8` et des niveaux de lecture 0 à 3. [Rapport et reproductibilité](RUST_PHASE2.md)

Les essais S3 attribuent l’essentiel du coût à froid au store. Le cache disque ramène 28 lectures réseau à sept au premier passage et à zéro pour les données lors d’une nouvelle ouverture. La médiane de lecture à chaud est de 2,34 ms. Ne pas prioriser un port du lecteur Rust. Au prochain profil, identifier les neuf réponses de métadonnées à zéro octet encore émises à la réouverture et évaluer un TTL court pour les seules clés optionnelles, avec contrôle des métadonnées mises à jour. Pour le chemin de dérive napari, comparer les accès Dask actuels à des lectures Zarr groupées hors du thread graphique et mesurer le délai jusqu’à la trame. [Trace S3](validation/zarr-navigation-windows.json) · [Trace napari](validation/napari-real-windows.json)

Dans napari, les gains sur le worker de dérive se traduisent par une baisse de 3,5 à 7,9 % de la médiane jusqu’à la trame. La suite complète sous Qt `windows` compte 304 réussites. Un `napari.Viewer` seul reproduit l’échec de `GL_MAX_TEXTURE_SIZE` sous `offscreen`. Garder le test Windows natif et la CI Linux configurée avec Xvfb. Le panneau **Comparer les prédictions** lit des cartes déjà produites, avec origine UV, pas physique, provenance et seuil d’affichage. Conserver les runs Reader/PyTorch/CUDA en Python et exporter les plans sur la même grille avant de les comparer. [Manifeste de comparaison](COMPARAISON_PREDICTIONS.md)

## État du premier lot

- Branche locale `feat/rust-explorer-first-kernel`, base `426e712`. L’extension facultative et les mesures se relisent indépendamment des travaux locaux d’évaluation d’encre.
- Le chemin de projection `core/chunkcache.py` utilise le noyau `rust/src/lib.rs` sur activation. La CLI `vesuvius-qc carte` et l’interface napari **Surfaces** partagent le point d’entrée. La version Python est le choix par défaut.
- Windows GNU x64, Release, grand rendu Zarr local médian 307,30 ms en Python, 175,07 ms avec le témoin SciPy optimisé, 128,34 ms en Rust. Sur le bloc PHerc0800 réencodé localement, 51,87 / 33,22 / 27,23 ms. Les géométries de ces mesures sont synthétiques.
- Les tests vérifient les sorties Python/Rust, y compris une carte synthétique multithread, et le script de benchmark vérifie la parité des tableaux. Sur Windows, l’essai napari a ouvert un Zarr local, superposé un tifxyz et affiché la carte de dérive avec Rust. La suite graphique complète reste à reproduire. Une matrice CI Linux/Windows valide la construction et l’import de la roue sur les prochains runs. [Profil et mesures](RUST_BENCHMARKS.md)

## Suite à orchestrer

1. Étendre le corpus à un vrai `uint16` et à un Zarr v3 shardé `vc-delta3d`, puis vérifier les mêmes champs et les décisions au seuil. Pour les très grands segments, relever les relectures et évictions causées par les lots plus grands que le cache et figer un budget avant l’essai.
2. Tester les métadonnées et les alternatives Dask/Zarr sur une trajectoire avec plusieurs résolutions et changements de direction. Mesurer les octets réseau et les temps jusqu’à la trame avant d’évaluer un préchargement borné.
3. Faire un essai VC3D/HerculeX sur la même coupe et examiner face, coutures et trous. Pour l’encre, produire une pile orientée une fois, exécuter Reader V3 et un modèle indépendant sur les mêmes pixels avec batch et VRAM enregistrés, puis préserver cartes brutes et contrôles. Alimenter le panneau UV avec ce lot, puis évaluer une présentation côte à côte et les annotations exportables.
4. Vérifier une roue Windows MSVC et une roue Linux/WSL2. Passer le même corpus et la même version NumPy. Geler les critères de gain du parcours complet avant de changer le réglage par défaut.

Les exigences d’axes, de provenance, de compatibilité des codecs et de licence sont documentées avec la feuille de route. [Audit](RUST_AUDIT.md) · [Architecture](RUST_ARCHITECTURE.md) · [Interface](VESUVIUS_EXPLORER.md)
