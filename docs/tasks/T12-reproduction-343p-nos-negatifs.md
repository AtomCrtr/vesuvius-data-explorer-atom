# T12 · Phase 18 : les deux ordres sur PHerc0343P, avec nos propres négatifs · prompt Codex

- **Origine :** décision du PO du 25 novembre 2026. On n'attend pas la sélection de pixels d'EconLearn : on mesure l'écart entre les deux ordres dans notre chaîne, avec des négatifs définis avant de consulter les étiquettes. La comparaison avec ses ROC-AUC (0,599 et 0,936) restera indicative.
- **Statut :** à lancer.
- **Branche :** `feat/vesuvius-phase18`, créée depuis `main` (`400e6d6`).
- **Lien avec `phase17b-protocol.json` :** ce projet reste réservé à la comparaison appariée sur la sélection d'EconLearn, s'il la partage. La phase 18 ne le modifie pas. Ses cartes de scores, une fois hachées, pourront être réévaluées plus tard sur son support sans relancer l'inférence.

---

## Prompt à donner à Codex (copier tel quel à partir d'ici)

Tu travailles dans le dépôt `vesuvius-data-explorer-atom`. Les documents sont en français, le code et ses commentaires en anglais, comme dans le reste du dépôt. Le PO travaille sous Windows : `.venv/Scripts/python.exe` pour l'environnement principal, `data/phase6-cuda/Scripts/python.exe` pour l'inférence CUDA (RTX 4080). Crée la branche `feat/vesuvius-phase18` depuis `main`. N'écris rien sur GitHub et ne poste aucun commentaire.

### 1. Ce qu'il faut lire d'abord

1. `docs/CLAUDE_HANDOFF.md`, phases 11 à 17.
2. `docs/PHASE17_ORIENTATION_2UM.md` et `docs/validation/phase17-orientation.json`. Sur PHerc0343P, l'air est du côté des couches basses (r = 5,83), donc lire les couches de 63 vers 02 correspond à **`Z_out`** (papyrus → air), et de 02 vers 63 à **`Z_in`**.
3. `docs/PHASE11_CHECKPOINT_COMPATIBILITY.md` : la recette de A (poids `r152_3ddec_v2_l5_epoch13.ckpt`, SHA-256 `36dd0de8…` ; 62 plans ; uint8 écrêté à 200 puis ÷ 200 ; tuiles de 256 au pas de 128 ; fusion Hann ; FP32 déterministe).
4. `docs/validation/phase11_z_frag4.py` (inférence auditée), `docs/validation/phase12_ink_eval.py` (`sample_labels`, `ranking`, `binned`, bande de tolérance), `docs/validation/phase13_eval.py` (préparation sans étiquettes, témoins B1/B2, bootstrap apparié, `MIN_CLASS`, protocole à empreinte), `docs/validation/phase15_audit.py` (bootstrap par ROI et par composante).
5. `docs/validation/phase17b-protocol.json` : licences déjà consultées. Fragment sous **CC BY-NC 4.0**, `343P_ir.png` et `343P_inklabels.png` produits par l'équipe du Vesuvius Challenge.
6. `docs/validation/phase17-inventory.json` : URL, tailles et en-têtes de toutes les couches, du masque, de l'IR et des étiquettes de PHerc0343P.

### 2. La question

**Dans notre chaîne, sur PHerc0343P, l'ordre `Z_out` classe-t-il l'encre tracée mieux que `Z_in`, et mieux que le hasard et que des témoins non appris, avec des négatifs définis avant toute lecture des étiquettes ?**

Ce n'est pas une analyse aveugle : les scores d'EconLearn sont connus. Le rapport le dit dès la première ligne.

### 3. Vérification préalable : PHerc0343P est-il dans l'entraînement de A ?

Dans le script Villa épinglé (`deprecated/ink-detection/train_resnet3d_3d_decoder.py` au commit `c8f3ba45304f0a317a49a155929e30d294f201eb`), cherche tout identifiant qui pourrait désigner PHerc0343P (`343`, `0343`, `343p`…) dans `TRAIN_FRAGMENT_IDS` et dans les chemins de données, y compris dans `train_resnet3d_lib`. Écris le résultat dans le protocole, avec les lignes citées. S'il y figure, la phase 18 devient une mesure dans la distribution d'entraînement : poursuis, mais écris-le en tête du rapport.

### 4. Protocole figé avant toute inférence et avant les étiquettes

Commit 1, **avant** de télécharger la moindre couche nouvelle, l'IR ou les étiquettes : `docs/validation/phase18-protocol.json` et `docs/validation/phase18_eval.py`, avec l'empreinte du protocole contrôlée comme en phases 14 et 17 (fins de ligne normalisées, refus d'un protocole modifié). Le protocole fixe tout ce qui suit.

**Entrées (dans la recette, sans rééchantillonnage).**
- Couches 02 à 63 de `PHerc0343P/paths/2um_front_surface/layers/`, soit 62 plans à 2 µm, ce qui correspond à la fenêtre d'EconLearn.
- `Z_out` = plans 63 → 02 ; `Z_in` = plans 02 → 63. Ce sont les mêmes tableaux, seul l'axe de profondeur est inversé.
- Normalisation de la recette : uint8, écrêtage à 200, ÷ 200. Pas de fenêtre W2 en analyse principale, puisque les PNG sont déjà en 8 bits comme à l'entraînement.
- Secondaire, sans décision : la fenêtre 01–62 de Villa, dans les deux ordres.

**Support et ROI (définis sur le masque seul).**
- Pavage de tout le masque publié (érodé de 16 px, comme en phase 11) en ROI carrées non chevauchantes, d'une taille fixée dans le protocole (par exemple 2048 px, soit environ 4 mm). Garde toutes les ROI dont au moins 50 % de la surface est dans le masque. Il n'y a **aucune sélection** : on évalue tout le fragment.
- Pixels valides : dans le masque érodé, couverts par les tuiles, avec un poids de fusion d'au moins 25 % du maximum (règle de la phase 11).

**Classes (règles écrites avant de voir les étiquettes).**
- Positifs : les pixels de `343P_inklabels.png` marqués encre, sur le même canevas que les couches. Vérifie l'égalité des dimensions dans l'inventaire et arrête-toi si elles diffèrent : ne recale rien sans en parler au PO.
- **Négatifs principaux** : les pixels valides situés à plus de T µm de tout positif. Fixe **T = 301 µm**, la tolérance des phases 12 à 16. L'anneau entre 0 et T est exclu des deux classes. Reprends exactement la logique de `phase12_ink_eval`.
- Sensibilité, sans décision : T = 100 µm et T = 0.
- **Négatifs « propres sur la photo », secondaire sans décision**, pour s'approcher du critère d'EconLearn : parmi les négatifs principaux, ne garder que ceux dont la luminance IR est au-dessus du 25e percentile de l'IR dans le masque. L'encre est sombre en IR. Ce seuil est fixé ici et ne sera pas ajusté.
- Inclusion d'une ROI dans les métriques regroupées : au moins `MIN_CLASS` = 1000 pixels dans chaque classe (règle de la phase 13). Une ROI sans encre étiquetée est donc exclue par règle, et le nombre de ROI exclues est publié.

**Scores comparés.** `Z_out`, `Z_in`, et les témoins non appris B1 (intensité de surface) et B2 (texture locale), définis comme en phase 13.

**Hypothèses (ROI regroupées).**
- **H1** : ROC-AUC(`Z_out`) − ROC-AUC(`Z_in`) > 0, borne basse de l'intervalle à 95 % au-dessus de 0.
- **H2** : ROC-AUC(`Z_out`) > 0,5, borne basse au-dessus de 0,5.
- **H3** : ROC-AUC(`Z_out`) − meilleur témoin > 0, borne basse au-dessus de 0.
- Rapporte aussi les PR-AUC et la prévalence.

**Incertitude.** L'analyse principale est un **bootstrap apparié par composante connexe d'encre**, comme recommandé en phase 15 : chaque tirage rééchantillonne les composantes, avec leurs négatifs voisins rattachés par une règle écrite dans le protocole. Les mêmes tirages servent pour tous les scores. Fixe le nombre de tirages et la graine. En secondaire, ajoute le bootstrap par ROI et le bootstrap par blocs de 64² des phases 13 et 14, en précisant qu'il est optimiste.

**Comparaison avec EconLearn, indicative et sans décision.** Donne l'écart entre nos ROC-AUC et ses chiffres (0,936 en `Z_out`, 0,599 en `Z_in`). Écris que les supports diffèrent (nos négatifs, notre tolérance, notre masque) et qu'un écart ne prouve pas une erreur de part ou d'autre.

### 5. Inférence avant les étiquettes

Commit 2, toujours **sans** IR ni étiquettes :
- Télécharge les couches 02 à 63 et 01 (pour la fenêtre secondaire) dans `data/phase18/`, hors Git, et note le SHA-256 de chaque fichier. Les 26 couches déjà téléchargées en phase 17 peuvent être réutilisées si leurs empreintes concordent.
- Lance A dans les deux ordres, et dans les deux fenêtres, avec le code d'inférence de la phase 11 inchangé. Vérifie le SHA-256 des poids avant chargement (`weights_only=True`). Répète une ROI pour confirmer le déterminisme au bit près.
- Calcule B1 et B2.
- Commite `docs/validation/phase18-scores.json` : SHA-256 de chaque carte de scores et des entrées, statistiques sans étiquettes (moyenne, P99, part > 0,5 par ordre), temps de calcul. **Les cartes restent hors Git.** Le message de commit précise : « cartes de scores hachées avant ouverture des étiquettes ».

### 6. Évaluation

Commit 3 :
- Télécharge `343P_inklabels.png` et `343P_ir.png`, et note leur SHA-256.
- Lance `phase18_eval.py --report docs/validation/phase18-eval.json` sur les cartes dont l'empreinte correspond à `phase18-scores.json`. Le script refuse une carte dont l'empreinte diffère.
- Ne change aucune règle après ouverture. Si une règle se révèle inapplicable (canevas différent, étiquettes vides sur la plupart des ROI…), documente l'échec et propose une phase suivante, sans corriger en silence.

### 7. Optionnel, après le reste : PHerc0500P2 (étape C, descriptive)

Seulement si le temps de calcul mesuré sur PHerc0343P le permet (le PO tranche si l'estimation dépasse 6 h de GPU). On applique le même protocole à PHerc0500P2, fragment de l'entraînement : c'est une mesure dans la distribution, sans hypothèse confirmatoire. Elle donnerait le chiffre « ordre stocké » qui manque à EconLearn, et elle indique si l'ordre d'entraînement supposé (63 → 02 ≈ 62 → 01, soit `Z_out`) est celui qui donne les meilleurs scores, ce qui serait cohérent avec la correspondance plausible de `500p2a`, sans la prouver. Écris cette étape dans le même protocole, avant tout calcul.

### 8. Livrables

1. Les commits 1 à 3 ci-dessus, dans cet ordre, puis le commit 4 avec le rapport `docs/PHASE18_REPRODUCTION_343P.md`, dans le style des phases 13 à 17 :
   - réponse en gras en une ou deux phrases ;
   - mention « non aveugle » ;
   - chronologie des commits ;
   - tableau H1 à H3 ;
   - sensibilités (T, fenêtre, négatifs IR, bootstraps secondaires) ;
   - comparaison indicative avec EconLearn ;
   - limites ;
   - suite.
2. Les tests dans `tests/test_phase18.py`, sans réseau :
   - l'inversion de l'axe Z ne change que l'ordre des plans ;
   - la règle des négatifs avec l'anneau T sur une image synthétique ;
   - le seuil IR des négatifs secondaires ;
   - le bootstrap par composante (mêmes tirages pour tous les scores) ;
   - le refus d'un protocole modifié et d'une carte de scores dont l'empreinte diffère.
3. Une section « Phase 18 » en tête de `docs/CLAUDE_HANDOFF.md`, et `docs/PHASE18_PR.md`.
4. Un projet de court complément en anglais pour villa#2627, dans `docs/PHASE18_COMMUNITY_FOLLOWUP.md`, marqué « brouillon, non envoyé ». Il donne nos chiffres, nos négatifs et le caractère non aveugle, et rappelle que la comparaison appariée reste possible s'il partage sa sélection.

### 9. Règles à ne pas enfreindre

- Ni étiquettes ni IR avant le commit 2 (cartes de scores hachées).
- Aucun seuil (T, percentile IR, `MIN_CLASS`, taille des ROI, érosion, poids de fusion) ne bouge après ouverture.
- Ne modifie aucun protocole figé antérieur, ni `phase17b-protocol.json`.
- Licence CC BY-NC 4.0 : pas d'image, pas de découpe d'étiquette ni d'IR, pas de transcription, dans le dépôt comme dans les brouillons. On publie uniquement des statistiques agrégées, avec attribution à l'équipe du Vesuvius Challenge.
- Pas de données lourdes dans Git.
- Lance `pytest` en entier avant le dernier commit. Donne le décompte (réussis, ignorés, désélectionnés) et compare-le aux 314 / 13 / 8 de la phase 17.
- Rédaction : phrases courtes, accents corrects, aucune conclusion au-delà des chiffres. Un résultat contraire à EconLearn ou à nos phases précédentes se rapporte tel quel.

### 10. Ce que tu rends au PO

Un résumé de six lignes au plus :

1. la présence ou l'absence de PHerc0343P dans l'entraînement ;
2. les ROC-AUC de `Z_out` et `Z_in` avec leurs intervalles, et le verdict pour H1, H2 et H3 ;
3. la sensibilité la plus défavorable ;
4. l'écart indicatif avec EconLearn ;
5. les commits ;
6. ce qui attend son accord (étape C, envoi du complément).
