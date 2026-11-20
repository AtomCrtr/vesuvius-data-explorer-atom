# Phase 7 · Expérience factorielle et vérification des orientations

## Résultat scientifique

Sur PHerc0500P2, une intervention sur l’ordre Z, à checkpoint
public A, géométrie et assemblage identiques, change fortement
les prédictions. La fenêtre CT donne un **Spearman A+/A− de
−0,444** et aucun pixel commun jusqu’au top 10 %. La région
distante donne un **Spearman de 0,809** et un accord de rang
partiel. L’effet est donc réel pour A et varie selon le secteur.
L’ordre Z est une cause plausible du désaccord de production.
Pour en quantifier la contribution, il manque le poids exact de B,
son prétraitement et le rattachement explicite des poids aux jobs.
[Expérience](PHASE7_Z_ORDER_EXPERIMENT.md) · [Comparaisons](PHASE7_MODEL_COMPARISON.md) · [Audit des poids](PHASE7_CHECKPOINT_AUDIT.md)

A+ retrouve le TIFF A publié à un code près sur les deux régions.
Ce niveau de concordance motive une reproduction de la chaîne
B dès que les poids seront disponibles. Le CT brut confirme
que l’indice de profondeur croît le long de `−dP/dU × dP/dV`
sur les quatre témoins du maillage historique. Cette direction
est géométrique. La face anatomique reste inconnue.

Les quatre régions du dossier de phase 6 ont été relues et
documentées avec leurs sorties originales et contrôlées.
La contribution scientifique disponible porte sur une
sensibilité à l’ordre Z et un protocole de contrôle. Le gain
de détection d’encre reste indémontré, faute de vérité terrain
appropriée et indépendante. Les données de relecture permettent
à un spécialiste d’examiner les traces sans recevoir une
transcription proposée par le modèle.
[Dossier de relecture](PHASE7_CANDIDATE_REVIEW.md)

## Suite expérimentale

Demander le poids B, son SHA-256, sa licence, les digests A et B
de production et la configuration d’inférence. Valider l’entrée
commune à résolution égale ou documenter les traitements propres
à chaque architecture. Exécuter les deux orientations de B sur
le même plan gelé. Les six contrastes et l’interaction par rang
deviennent interprétables sur le même support lorsque les quatre
cellules sont mesurées. Une nouvelle évaluation supervisée
requiert un rouleau réservé à l’évaluation, des labels alignés et
une face attestée. Aucun réentraînement n’a été lancé.

## Reproductibilité et compatibilité

`feat/vesuvius-phase7` part du même commit de référence que
`feat/vesuvius-phase6`. L’arbre de reprise contenait 76 fichiers
modifiés ou non suivis et l’index était vide. Le dossier local
`data/phase7/phase6-before-phase7.zip` préserve cet état et
sept entrées locales de la phase 6. SHA-256
`5ff56ab091fa6a0cb603e691fd42ca3b8bf4ac142491af024e4b3350a3402382`.
Le ZIP vérifié contient la base Git, le patch et l’arbre de
récupération. Restaurer les chemins de `tree/` sur la base de
`restore.json` dans un dossier de travail distinct.

Windows natif a donné **341 tests réussis** et un test ignoré
pour le codec optionnel. Les **8 tests réseau** réussissent
séparément sous Python 3.12 avec le codec. Les **73 contrôles
ciblés** Rust, volumes et géométrie réussissent avec Rust activé.
Les tests couvrent
notamment les configurations napari à deux et quatre conditions,
la conversion des coupes, la normale, les masques, l’intégrité
du checkpoint et les cas absents. Les tests d’export vérifient
les archives rouvrables et reproductibles. Les calculs de la
vue 2 × 2 tournent dans un worker et consomment les TIFF en
cache. Les chemins S3/Dask et Rust restent utilisés par les
ensembles de tests existants. Python reste le moteur par défaut.

Les logits 64², les scores par tuile et les rasters assemblés
sont conservés sous `data/phase7`. L’expérience principale
rejouée dans deux processus CUDA indépendants donne les mêmes
tableaux, à environnement fixé.
[Trace CUDA](validation/phase7-cuda-windows.json) · [Plan de tuiles](validation/phase7-input-plan.json) · [Passation Claude](CLAUDE_HANDOFF.md)
