# Feuille de route scientifique après la phase 11

**Priorité : valider, pas développer.** L'infrastructure suffit. Ce qui manque est une mesure d'encre contre une référence indépendante, avec un protocole gelé avant de regarder les résultats.

## Décisions

Les trois décisions ci-dessous ont été appliquées le 21 novembre 2026 (tolérance 301 µm, fenêtre W2, envoi). [Décisions](PHASE11_DECISIONS.md)

### Options examinées

| Décision | Options | Recommandation |
| --- | --- | --- |
| Critère de recalage pour une référence optique grossière | Garder 2 px CT (inatteignable) ; passer à `max(2 px CT, 2 px optiques)` ; travailler avec une tolérance spatiale explicite | Tolérance explicite de 3σ ≈ 200 µm sur Frag4, avec analyse de sensibilité au décalage |
| Envoi des demandes aux mainteneurs | Envoyer la note et les trois questions ; attendre | Envoyer, après relecture, la note corrigée et les questions d'attestation |
| Fenêtre d'intensité de Frag4 | `>> 8` brut (actuel) ; fenêtre air → 0 fixée sur le CT | Fenêtre fixée sur le CT seul, gelée avant les étiquettes |

## Phase 13 proposée : confirmer ou infirmer le classement de Z_out

La phase 12 est faite ([rapport](PHASE12_INK_EVALUATION.md)). H1 et H2 sont rejetées, et Z_out classe l'encre sur les ROI 2 et 5 sans la détecter. Les ROI 2 et 5 sont désormais vues : elles ne servent plus à confirmer.

1. Geler **H3 : ROC-AUC(Z_out) > 0,5 + demi-largeur à 95 %** et **H4 : PR-AUC(Z_out) > PR-AUC(Z_in)**, ainsi que de nouvelles ROI de Frag4 tirées par la règle géométrique (patchs non encore utilisés), avant de calculer quoi que ce soit.
2. Répéter sur Frag1 et Frag3 avec la même recette.
3. Ajouter un témoin non appris (texture locale ou filtre sur plusieurs plans) pour situer l'apport de A par rapport à l'intensité.
4. Envoyer le complément à villa#2627 après accord ([brouillon](PHASE12_COMMUNITY_FOLLOWUP.md)).

## Phase 12 (faite) : première évaluation Frag4, exploratoire et pré-enregistrée

1. **Geler** (fait : [phase12-protocol.json](validation/phase12-protocol.json)) dans un fichier haché et commité avant toute mesure : ROI (règle géométrique existante), fenêtre d'intensité, tolérance spatiale, seuils, métriques, ordre(s) Z évalués, critère de succès.
2. **Ouvrir** ensuite seulement `PHercParis1Fr39_54keV_inklabels.png` et calculer VP/FP/FN, Dice, Jaccard, PR-AUC à tolérance, pour `Z_in` et `Z_out`, avec intervalles par blocs et sensibilité au décalage (0, ±25, ±50, ±100 µm).
3. **Intituler** le résultat « exploratoire, exclusion directe probable » tant que l'attestation manque.

C'est l'expérience la plus prometteuse : la face écrite de Frag4 est connue, l'encre y est visible en IR, la chaîne géométrique est validée, et l'effet Z y est fort. Elle dira si l'ordre qui « répond » correspond à l'encre.

## En parallèle

- Demander l'attestation d'entraînement de A (liste exacte, ascendance des étiquettes, pré-entraînement), la normalisation ÷ 255/÷ 200 et l'ordre attendu pour une surface exposée.
- Abandonner PHerc0500P2 comme banc d'évaluation de A (P0-S1). Garder la demande ν2 seulement si elle sert un autre modèle.
- Étendre l'expérience Z aux autres fragments EduceLab (Frag1, Frag3) avec la même recette, pour sortir du cas unique.

## Tâches pour Codex

| ID | Tâche | Critère d'acceptation |
| --- | --- | --- |
| T1 | Extraire la recette d'entrée et l'inférence (préparation des tuiles, ordre Z, normalisation, fusion Hann) des scripts `phase6/7/8/11` vers un module `vesuvius_data_explorer.inference`, sans dépendance à torch à l'import. | Tests unitaires sans GPU (tuile synthétique, fusion, ordre) ; les quatre scripts l'utilisent ; sorties phase 11 identiques au bit près. |
| T2 | Rééchantillonnage Frag4 au pas réel de la PPM (lecture de la PPM par plages, métrique locale), au lieu du pas nominal 3,24 µm. | Carte du facteur d'échelle local ; test sur une PPM synthétique non isométrique. |
| T3 | Commande `vesuvius-qc protocole geler <fichier>` : écrit le protocole JSON, son SHA-256 et l'horodatage ; les scripts d'évaluation refusent de tourner si le protocole n'est pas gelé ou a changé. | Test de refus et d'acceptation. |
| T4 | Ajouter `Frag4/54keV_3.24um_.zarr` à `core/geometry.py:_VERIFIED` après comparaison des niveaux adjacents (moyenne 2³), comme en phase 4. | Script de vérification et test. |
| T5 | Transformer les liens `../data/…` des rapports en mentions d'artefacts locaux, ou publier les manifestes correspondants. | Aucun lien mort vers `data/` dans `docs/`. |
