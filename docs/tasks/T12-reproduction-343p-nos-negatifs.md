# T12 · Phase 18 : les deux ordres sur PHerc0343P, sur notre support et sur celui d'EconLearn · prompt Codex

- **Origine :** décision du PO du 25 novembre 2026 de ne pas attendre EconLearn. Le même matin, EconLearn a publié sur [villa#2627](https://github.com/ScrollPrize/villa/issues/2627) ses règles de sélection, ses effectifs et ses réglages d'inférence. La phase 18 évalue donc les deux ordres **sur deux supports** : le nôtre, dans la continuité des phases 12 à 16, et le sien, reconstruit à partir de ses règles.
- **Statut :** commit 1 fait le 25 novembre 2026 (protocole figé, script, tests, sans aucun téléchargement de phase 18). Codex reprend à l'étape 2, voir « Reprise » ci-dessous. Le protocole figé fait foi là où il précise ou corrige ce prompt.
- **Branche :** `feat/vesuvius-phase18`, créée depuis `main`.
- **Lien avec `phase17b-protocol.json` :** ce projet non figé est remplacé par le support E de la phase 18. Ne modifie pas le fichier : le rapport de phase 18 dit qu'il est remplacé.

## Ce que la réponse d'EconLearn change

1. **Son écart 0,599 → 0,936 mélange deux effets.** Le passage en ordre stocké utilisait des tuiles sans chevauchement (pas de 256), le passage inversé le pas de 128 avec fusion Hann. L'effet de l'ordre n'est donc pas isolé dans ses chiffres. Notre phase 18 compare les deux ordres avec un pavage identique, et mesure à part l'effet du pavage.
2. **Son support est reconstructible.** Couches, IR, lettres tracées et masque partagent le même canevas. La vérité est construite sur une grille de 0,2564 × le canevas, soit 8,64 µm par pixel. Ses effectifs publiés permettent de vérifier la reconstruction avant tout calcul de ROC-AUC.
3. **Son incertitude ne porte pas sur l'écart entre ordres.** Ses 2 000 placements aléatoires des lettres (meilleure ROC-AUC aléatoire 0,722) testent l'écart au hasard d'un seul passage. Notre bootstrap apparié par composante donne un intervalle sur la différence `Z_out` − `Z_in`.
4. **Pour 500p2a, rien de nouveau sur le rendu.** Il a lu le paquet public tel qu'il est servi aujourd'hui (couches 02–63) et propose de publier le SHA-256 de chaque couche. On compare ses empreintes aux nôtres. Le lien avec le rendu d'entraînement reste une question pour les mainteneurs.

## Reprise à l'étape 2 (le commit 1 est fait)

Le commit 1 contient `docs/validation/phase18-protocol.json` (SHA-256 `1c115794…be26`), `docs/validation/phase18_eval.py` et `tests/test_phase18.py` (13 tests ; suite complète : 327 réussis, 13 ignorés, 8 désélectionnés). Les étapes `--hash`, `--supports` et `--report` ont tourné de bout en bout sur un fragment synthétique. La recherche y a retrouvé l'interprétation génératrice (écart 0 %). L'inférence CUDA n'a pas pu être exécutée hors de la machine du PO.

Ce que le protocole fixe en plus du prompt :

- PHerc0343P n'apparaît pas dans `TRAIN_FRAGMENT_IDS` du script Villa épinglé. Plusieurs identifiants sont opaques, donc l'indépendance est probable, pas attestée ;
- le canevas est complété par des zéros jusqu'à un multiple de 256 px, pour que les deux pas le pavent exactement. Une tuile est calculée si elle contient au moins un pixel du masque ;
- six cartes (`Z_out`/`Z_in` × pas de 128/256, plus la fenêtre 01–62 au pas de 128), et B1/B2 comme en phase 13 ;
- 216 interprétations du support E, avec la métrique des érosions en plus ;
- bootstrap : 1999 tirages, graine 218 (composantes), 219 (ROI), 220 (blocs). Placement : 2000 décalages cycliques, graine 1802, décalage d'au moins 64 px de grille.

Commandes, depuis la racine, sur la machine du PO :

```
.venv/Scripts/python.exe docs/validation/phase18_eval.py --prepare
data/phase6-cuda/Scripts/python.exe docs/validation/phase18_eval.py --run
.venv/Scripts/python.exe docs/validation/phase18_eval.py --baselines
.venv/Scripts/python.exe docs/validation/phase18_eval.py --hash        # puis commit 2
.venv/Scripts/python.exe docs/validation/phase18_eval.py --supports    # puis commit 3
.venv/Scripts/python.exe docs/validation/phase18_eval.py --report docs/validation/phase18-eval.json   # commit 4
```

Ressources à prévoir :

- **Disque :** environ 1,8 Go de couches PNG et 7,4 Go pour la pile `layers01_63.npy`, plus environ 3,5 Go de cartes, le tout dans `data/phase18/`, hors Git.
- **Mémoire :** `--supports` et `--report` dépassent 10 Go de RAM au pic (transformées de distance sur les 407 Mpx de PHerc0500P2).
- **GPU :** temps inconnu. `run.json` note les secondes par carte ; si l'étape C est envisagée, extrapole à partir de ces temps.

Si EconLearn publie ses SHA-256 de couches, enregistre-les dans un JSON `{nom de fichier: sha}` et passe-le avec `--econlearn-sha` à l'étape `--hash`.

---

## Prompt à donner à Codex (copier tel quel à partir d'ici)

Tu travailles dans le dépôt `vesuvius-data-explorer-atom`. Les documents sont en français, le code et ses commentaires en anglais, comme dans le reste du dépôt. Le PO travaille sous Windows : `.venv/Scripts/python.exe` pour l'environnement principal, `data/phase6-cuda/Scripts/python.exe` pour l'inférence CUDA (RTX 4080). Crée la branche `feat/vesuvius-phase18` depuis `main`. N'écris rien sur GitHub et ne poste aucun commentaire.

### 1. Ce qu'il faut lire d'abord

1. `docs/CLAUDE_HANDOFF.md`, phases 11 à 17.
2. `docs/PHASE17_ORIENTATION_2UM.md` et `docs/validation/phase17-orientation.json`. Sur PHerc0343P, l'air est côté couches basses (r = 5,83). Lire les couches de 63 vers 02 correspond donc à **`Z_out`** (papyrus → air), et de 02 vers 63 à **`Z_in`**.
3. `docs/PHASE11_CHECKPOINT_COMPATIBILITY.md` : recette de A (poids `r152_3ddec_v2_l5_epoch13.ckpt`, SHA-256 `36dd0de8…` ; 62 plans ; uint8 écrêté à 200 puis ÷ 200 ; tuiles de 256 au pas de 128 ; fusion Hann ; FP32 déterministe).
4. `docs/validation/phase11_z_frag4.py` (inférence auditée), `docs/validation/phase12_ink_eval.py` (`sample_labels`, `ranking`, `binned`, bande de tolérance), `docs/validation/phase13_eval.py` (témoins B1 et B2, bootstrap apparié, `MIN_CLASS`, protocole à empreinte), `docs/validation/phase15_audit.py` (bootstrap par ROI et par composante).
5. `docs/validation/phase17b-protocol.json` : licences déjà consultées. Fragment sous **CC BY-NC 4.0** ; `343P_ir.png` et `343P_inklabels.png` sont de l'équipe du Vesuvius Challenge.
6. `docs/validation/phase17-inventory.json` : URL, tailles et en-têtes des couches, du masque, de l'IR et des étiquettes de PHerc0343P.
7. Le commentaire d'EconLearn du 25 novembre sur villa#2627, qui donne sa méthode. Elle est recopiée en section 4.3.

### 2. La question

**Dans notre chaîne, avec un pavage identique pour les deux ordres, `Z_out` classe-t-il l'encre tracée de PHerc0343P mieux que `Z_in`, mieux que le hasard et mieux que des témoins non appris, sur notre support comme sur celui d'EconLearn ? Et quelle part de son écart vient du pavage ?**

Ce n'est pas une analyse aveugle : les scores d'EconLearn et sa méthode sont connus. Le rapport le dit dès la première ligne.

### 3. Vérification préalable : PHerc0343P est-il dans l'entraînement de A ?

Dans le script Villa épinglé (`deprecated/ink-detection/train_resnet3d_3d_decoder.py` au commit `c8f3ba45304f0a317a49a155929e30d294f201eb`, et `train_resnet3d_lib`), cherche tout identifiant de PHerc0343P (`343`, `0343`, `343p`…) dans `TRAIN_FRAGMENT_IDS` et dans les chemins. Écris le résultat dans le protocole avec les lignes citées. S'il y figure, poursuis, mais écris en tête du rapport qu'il s'agit d'une mesure dans la distribution d'entraînement.

### 4. Protocole figé avant toute inférence et avant les étiquettes

Commit 1, **avant** de télécharger la moindre couche nouvelle, l'IR ou les étiquettes : `docs/validation/phase18-protocol.json` et `docs/validation/phase18_eval.py`, avec l'empreinte du protocole contrôlée comme en phases 14 et 17. Le protocole fixe tout ce qui suit.

#### 4.1 Entrées et inférence

- Couches 02 à 63 de `PHerc0343P/paths/2um_front_surface/layers/` : 62 plans, sans rééchantillonnage, comme EconLearn.
- **Taille du pixel du canevas : 2,215 µm, et non 2 µm.** Le nom `2um` est arrondi. Le facteur 0,2564 d'EconLearn vers sa grille de 8,64 µm donne 2,215 µm, la résolution de la recette de A. Toute conversion de µm en pixels utilise 2,215 µm, par exemple 301 µm ≈ 136 px. Si les métadonnées du paquet donnent une autre valeur, arrête-toi et documente l'écart.
- `Z_out` = plans 63 → 02 ; `Z_in` = plans 02 → 63. Mêmes tableaux, seul l'axe de profondeur est inversé.
- Normalisation de la recette, qui est aussi celle d'EconLearn : écrêtage à 200, puis ÷ 200. Pas de fenêtre W2.
- **Pavage principal, identique pour les deux ordres :** tuiles de 256, pas de 128, fusion Hann.
- **Plan factoriel pour isoler le pavage, sans décision :** les deux ordres sont aussi calculés au pas de 256 sans chevauchement, ce qui reproduit la condition du 0,599 d'EconLearn. On obtient 4 cartes (ordre × pas).
- Secondaire, sans décision : la fenêtre 01–62 de Villa, dans les deux ordres, au pas de 128.

#### 4.2 Support N (le nôtre, continuité des phases 12 à 16)

- Pavage de tout le masque publié (érodé de 16 px, comme en phase 11) en ROI carrées non chevauchantes de taille fixée (par exemple 2048 px). On garde toute ROI dont au moins 50 % de la surface est dans le masque. Aucune sélection : on évalue tout le fragment.
- Pixels valides : dans le masque érodé, couverts par les tuiles, avec un poids de fusion d'au moins 25 % du maximum.
- Positifs : les pixels encre de `343P_inklabels.png`, sur le même canevas. Vérifie l'égalité des dimensions. Si elles diffèrent, arrête-toi.
- Négatifs : les pixels valides à plus de **T = 301 µm** de tout positif. L'anneau entre 0 et T est exclu. Reprends exactement la logique de `phase12_ink_eval`. Sensibilité sans décision : T = 100 µm et T = 0.
- Une ROI entre dans les métriques regroupées si chaque classe y compte au moins `MIN_CLASS` = 1000 pixels. Le rapport publie le nombre de ROI exclues.

#### 4.3 Support E (celui d'EconLearn, reconstruit à partir de ses règles)

D'après son commentaire :

- la vérité est construite sur une grille de **0,2564 × le canevas (8,64 µm par pixel)** ;
- encre = lettres tracées **érodées de 2 px** ;
- négatifs « propres sur la photo » = pixels **à au moins 12 px de toute lettre tracée** où **l'IR est plus clair que sa médiane sur le fragment** ;
- région = masque du fragment **érodé de 10 px**, là où les tuiles ont produit une valeur ; les pixels ni encre ni propres ne sont pas scorés ;
- ROC-AUC calculée après **quantification de la carte en 256 niveaux entre ses percentiles 0,1 et 99,9** ;
- effectifs publiés pour PHerc0343P : **247 538 pixels d'encre, 2 021 316 propres, 4 292 390 valides** (et pour PHerc0500P2 : 1 004 495 encre, 8 052 681 propres).

Il ne précise ni la méthode de réduction vers la grille de 8,64 µm, ni sur quelle grille s'appliquent l'érosion de 10 px et la médiane de l'IR. **On ne l'attend pas : ses effectifs suffisent à trancher.** Fige, avant toute lecture, un **ensemble fini d'interprétations**, puis choisis celle qui reproduit ses effectifs :

- **Taille de la grille :** `round` ou `floor` de 0,2564 × (largeur, hauteur) du canevas. Pour PHerc0343P (8416 × 13 924), on obtient environ 2158 × 3570.
- **Réduction des étiquettes et du masque :** plus proche voisin, ou moyenne de zone suivie d'un seuil à 0,5, ou « au moins un pixel ».
- **Réduction de l'IR :** moyenne de zone ou plus proche voisin.
- **Grille des opérations morphologiques** (érosion de 2 px de l'encre, distance de 12 px, érosion de 10 px du masque) : grille de 8,64 µm, ou canevas avec les rayons multipliés par 1/0,2564, puis réduction.
- **Population de la médiane IR :** région érodée, masque entier, ou région hors encre.
- **Métrique des érosions et distances :** euclidienne, taxicab (érosion itérée en croix) ou échiquier (carré 3 × 3). Ajoutée au moment du gel : « shrunk by 2 px » ne dit pas laquelle.
- Cela fait 2 × 3 × 2 × 2 × 3 × 3 = 216 combinaisons. Elles sont toutes énumérées dans le protocole, dans un ordre fixé.
- **Critère de choix :** l'écart relatif maximal sur les **cinq effectifs publiés** (PHerc0343P : encre, propres, valides ; PHerc0500P2 : encre, propres). Retiens la combinaison qui minimise cet écart. Le support E est déclaré **reconstruit** si cet écart est ≤ 2 %, et **approché** sinon (résultats alors seulement descriptifs). En cas d'égalité, prends la première combinaison dans l'ordre fixé.
- Pour PHerc0500P2, ce calcul n'utilise que `500P2_inklabels.png`, `500P2_ir.png` et `500P2_mask.png`, soit environ 58 Mo, sans aucune couche ni inférence.
- Publie dans `phase18-supports.json` les effectifs des 216 combinaisons, pas seulement ceux de la combinaison retenue.
- Les effectifs se calculent **avant** toute ROC-AUC sur les cartes. Ils ne dépendent que des étiquettes, de l'IR et du masque, et pas des scores. La recherche ne peut donc pas favoriser un ordre.
- Si EconLearn répond entre-temps sur ses choix, note sa réponse dans le protocole et vérifie qu'elle correspond à la combinaison retenue. Le critère de choix reste celui des effectifs.

#### 4.4 Scores, hypothèses, incertitude

- Scores comparés : `Z_out` et `Z_in` (pas de 128), B1 (intensité de surface) et B2 (texture locale), comme en phase 13.
- Hypothèses, **sur chacun des deux supports N et E**, avec un verdict par support :
  - **H1** : ROC-AUC(`Z_out`) − ROC-AUC(`Z_in`) > 0, borne basse de l'intervalle à 95 % au-dessus de 0 ;
  - **H2** : ROC-AUC(`Z_out`) > 0,5, borne basse au-dessus de 0,5 ;
  - **H3** : ROC-AUC(`Z_out`) − meilleur témoin > 0, borne basse au-dessus de 0.
- Sur N, la ROC-AUC se calcule sur les scores bruts. Sur E, elle se calcule avec sa quantification, et la version sur scores bruts est donnée en sensibilité.
- **Effet du choix des négatifs, sans décision :** support E **sans le filtre IR** (tous les pixels à au moins 12 px des lettres). Ses négatifs « plus clairs que la médiane IR » écartent le papyrus sombre ou abîmé, qui est justement le plus difficile. Rapporte, pour E, E sans filtre IR et N, la ROC-AUC de chaque ordre et leur différence.
- **Incertitude principale :** bootstrap apparié par composante connexe d'encre (phase 15). Les négatifs sont rattachés à la composante la plus proche, selon une règle écrite dans le protocole. Mêmes tirages pour tous les scores ; nombre de tirages et graine fixés. En secondaire : bootstrap par ROI, et bootstrap par blocs de 64², signalé comme optimiste.
- **Effet du pavage, descriptif :** sur le support E, les 4 ROC-AUC du plan ordre × pas, l'écart dû à l'ordre à pas égal, et l'écart dû au pas à ordre égal.
- **Test de placement d'EconLearn, secondaire :** 2 000 placements aléatoires des lettres sur le fragment, graine fixée, pour `Z_out` et `Z_in`. Il sert à comparer avec sa meilleure ROC-AUC aléatoire, 0,722.
- **Comparaison avec ses chiffres, indicative :** écart entre notre ROC-AUC sur E et ses 0,936 (`Z_out`, pas de 128), et entre notre `Z_in` au pas de 256 et son 0,599.

### 5. Inférence avant les étiquettes

Commit 2, toujours **sans** IR ni étiquettes :

- Télécharge les couches 01 à 63 dans `data/phase18/`, hors Git, avec le SHA-256 de chaque fichier. Les couches de la phase 17 sont réutilisables si leurs empreintes concordent.
- Lance A pour toutes les cartes de la section 4.1 avec le code d'inférence de la phase 11, inchangé à part le pas. Vérifie le SHA-256 des poids (`weights_only=True`). Répète une ROI pour confirmer le déterminisme au bit près.
- Calcule B1 et B2.
- Commite `docs/validation/phase18-scores.json` : SHA-256 de chaque carte et de chaque entrée, statistiques sans étiquettes (moyenne, P99, part > 0,5), temps de calcul. Les cartes restent hors Git. Message : « cartes de scores hachées avant ouverture des étiquettes ».
- Si EconLearn a publié ses SHA-256 de couches, compare-les aux nôtres dans ce même JSON (concordance fichier par fichier).

### 6. Évaluation

- **Commit 3 :** télécharge `343P_inklabels.png` et `343P_ir.png`, ainsi que `500P2_inklabels.png`, `500P2_ir.png` et `500P2_mask.png` pour la recherche sur les effectifs, et note leur SHA-256. Construis les supports N et E. Commite `docs/validation/phase18-supports.json` avec les effectifs, le résultat du critère de reconstruction de E et l'interprétation retenue. **Aucune ROC-AUC dans ce commit.**
- **Commit 4 :** `phase18_eval.py --report docs/validation/phase18-eval.json`, sur les cartes dont l'empreinte correspond à `phase18-scores.json`. Le script refuse toute carte différente.
- Aucune règle ne change après ouverture. Si une règle se révèle inapplicable, documente l'échec, sans correction silencieuse.

### 7. Optionnel : PHerc0500P2 (étape C, descriptive)

Seulement si le temps mesuré sur PHerc0343P le permet. Au-delà de 6 h de GPU estimées, le PO décide. Ce fragment fait partie de l'entraînement : la mesure est dans la distribution, sans hypothèse confirmatoire. On applique les supports N et E, et ses effectifs (1 004 495 / 8 052 681) servent de contrôle de reconstruction. Cette étape donnerait le chiffre « ordre stocké » au pas de 128, qui manque à EconLearn. Elle dirait aussi si l'ordre d'entraînement supposé (63 → 02, proche de 62 → 01, soit `Z_out`) donne les meilleurs scores, ce qui serait cohérent avec la correspondance plausible de `500p2a` sans la prouver. Écris cette étape dans le même protocole, avant tout calcul.

### 8. Livrables

1. Les commits 1 à 4, puis le commit 5 avec le rapport `docs/PHASE18_REPRODUCTION_343P.md`, dans le style des phases 13 à 17 :
   - réponse en gras ;
   - mention « non aveugle » ;
   - chronologie ;
   - tableau H1 à H3 par support ;
   - plan ordre × pas ;
   - sensibilités ;
   - test de placement ;
   - comparaison indicative avec EconLearn ;
   - remplacement de `phase17b-protocol.json` ;
   - limites et suite.
2. Les tests dans `tests/test_phase18.py`, sans réseau :
   - l'inversion de Z ne change que l'ordre des plans ;
   - le pas de 256 sans chevauchement couvre exactement la grille ;
   - les règles du support N (anneau T) et du support E (érosions, distance de 12 px, médiane IR, quantification aux percentiles) sur des images synthétiques ;
   - le critère de ± 2 % ;
   - le bootstrap par composante avec les mêmes tirages pour tous les scores ;
   - le refus d'un protocole modifié et d'une carte dont l'empreinte diffère.
3. Une section « Phase 18 » en tête de `docs/CLAUDE_HANDOFF.md`, et `docs/PHASE18_PR.md`.
4. Le brouillon `docs/PHASE18_COMMUNITY_FOLLOWUP.md` en anglais, marqué « brouillon, non envoyé ». Il donne nos chiffres sur les deux supports, l'effet du pavage, le caractère non aveugle, et la concordance des SHA-256 si elle a été faite.

### 9. Règles à ne pas enfreindre

- Ni étiquettes ni IR avant le commit 2.
- Aucune ROC-AUC avant le commit 3.
- Aucun seuil ne bouge après ouverture : T, érosions, distance de 12 px, médiane, quantification, ± 2 %, `MIN_CLASS`, taille des ROI, poids de fusion.
- Ne modifie aucun protocole figé antérieur, ni `phase17b-protocol.json`.
- Licence CC BY-NC 4.0 : pas d'image, pas de découpe d'étiquette ni d'IR, pas de transcription. Uniquement des statistiques agrégées, avec attribution à l'équipe du Vesuvius Challenge.
- Pas de données lourdes dans Git.
- `pytest` complet avant le dernier commit : donne le décompte et compare-le aux 314 / 13 / 8 de la phase 17.
- Phrases courtes, accents corrects, aucune conclusion au-delà des chiffres. Un résultat contraire à EconLearn ou à nos phases précédentes se rapporte tel quel.

### 10. Ce que tu rends au PO

Un résumé de sept lignes au plus :

1. la présence ou l'absence de PHerc0343P dans l'entraînement ;
2. la reconstruction du support E (effectifs, interprétation retenue) ;
3. les ROC-AUC de `Z_out` et `Z_in` par support, avec intervalles, et les verdicts H1 à H3 ;
4. la part du pavage dans l'écart d'EconLearn ;
5. l'écart indicatif avec ses chiffres et la concordance des SHA-256 ;
6. les commits ;
7. ce qui attend son accord (étape C, envoi du complément).
