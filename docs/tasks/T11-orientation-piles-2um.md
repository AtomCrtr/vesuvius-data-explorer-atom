# T11 · Orientation physique des piles `2um_front_surface` (phase 17) · prompt Codex

- **Origine :** commentaire d'EconLearn sur [villa#2627](https://github.com/ScrollPrize/villa/issues/2627) (24 novembre 2026, corrigé le 25) ; analyse du 25 novembre ; brouillon de réponse [PHASE17_COMMUNITY_REPLY.md](../PHASE17_COMMUNITY_REPLY.md).
- **Statut :** à lancer. Étape A autorisée. Étape B soumise à l'accord explicite du PO.
- **Branche :** `feat/vesuvius-phase17`, créée depuis `main` (`7ea4013`).

---

## Prompt à donner à Codex (copier tel quel à partir d'ici)

Tu travailles dans le dépôt `vesuvius-data-explorer-atom`. Les documents sont en français, le code et ses commentaires en anglais, comme dans le reste du dépôt. Le PO travaille sous Windows (`.venv/Scripts/python.exe` pour l'environnement principal, `data/phase6-cuda/Scripts/python.exe` pour l'inférence CUDA, RTX 4080). Crée la branche `feat/vesuvius-phase17` depuis `main`. N'écris rien sur GitHub. Ne poste aucun commentaire.

### 1. Contexte à lire avant d'écrire une ligne

Lis, dans cet ordre :

1. `docs/CLAUDE_HANDOFF.md`, sections phases 11 à 16.
2. `docs/PHASE11_CHECKPOINT_COMPATIBILITY.md` : recette du checkpoint A (`r152_3ddec_v2_l5_epoch13.ckpt`, SHA-256 `36dd0de8…`) et ligne « Ordre Z ». Le script d'entraînement fixe `reverse_layers=True` pour `500p2a`.
3. `docs/PHASE11_Z_GENERALIZATION.md` : définitions. **`Z_out` = plans croissants vers l'air (papyrus → air) ; `Z_in` = l'inverse.**
4. `docs/PHASE12_INK_EVALUATION.md`, `docs/PHASE13_INK_GENERALIZATION.md`, `docs/PHASE14_HELDOUT_ORDER.md` : sur les étiquettes d'encre, `Z_out` classe l'encre au-dessus du hasard sur 5 fragments sur 6 (Frag3 fait exception).
5. `docs/validation/phase13_eval.py` : la fonction `direction()` est la **règle de sens sans étiquettes**, figée en phase 13. Pour chaque couche, on prend la médiane, sur des patchs de 64 px à l'intérieur du masque, de l'écart-type des voxels. Les extrémités sont `AIR_ENDS = {"low": 0–12, "high": 52–64}`, et l'extrémité la moins texturée est l'air. Lis aussi `read_frozen_protocol`, `PROTOCOL_SHA` et le contrôle `--protocol` ajouté en phase 14.
6. `docs/PHASE17_COMMUNITY_REPLY.md` : le brouillon de réponse que ta phase doit pouvoir compléter.

### 2. Ce qu'EconLearn a rapporté (déjà connu, non aveugle)

Il a utilisé le checkpoint A sur les piles `2um_front_surface` de l'équipe (couches 02 à 63) et les a scorées contre les lettres tracées sur l'infrarouge, avec du papyrus propre sur la photo comme négatifs :

| | couches telles que stockées | couches inversées |
| --- | ---: | ---: |
| PHerc0343P, ROC-AUC | 0,599 | 0,936 |
| PHerc0500P2, ROC-AUC | — | 0,878 |

Il place l'air du côté des couches basses parce qu'elles sont plus sombres (moyenne d'environ 56–58 en couche 02 contre 80–91 en couche 63). Dans sa correction, il écrit que cette lecture « may be wrong » et qu'il ne l'a pas vérifiée autrement. PHerc0500P2 fait partie de l'entraînement de A (`500p2a`).

### 3. La question de la phase 17

**De quel côté se trouve l'air dans chaque pile `2um_front_surface` (PHerc0343P, PHerc0500P2), d'après la règle de sens figée en phase 13, sans toucher aux étiquettes, à l'IR ni à la photo ?**

Conséquences, fixées d'avance :

- **PHerc0343P.** Si l'air est du côté des couches basses, l'ordre « inversé » d'EconLearn est `Z_out`, et son résultat va dans le même sens que nos phases 12 à 14 (le fragment devient le 6e sur 7). Si l'air est du côté des couches hautes, « inversé » est `Z_in`, et PHerc0343P se comporte comme Frag3.
- **PHerc0500P2.** Si la pile est bien le rendu `500p2a` de l'entraînement, l'ordre d'entraînement est l'ordre stocké inversé. Avec l'air côté couches basses, l'ordre d'entraînement est alors **`Z_out`**. Avec l'air côté couches hautes, c'est **`Z_in`**. Ce serait la première indication sur l'ordre physique dans lequel A a été entraîné.

### 4. Étape A (autorisée) · orientation sans étiquettes

#### 4.1 Inventaire, sans rien ouvrir de sensible

- Liste `https://dl.ash2txt.org/fragments/PHerc0343P/` et `https://dl.ash2txt.org/fragments/PHerc0500P2/paths/2um_front_surface/` (voir `docs/validation/phase10-sources.json` pour les URL déjà connues de 500P2 : `layers/NN.png`, `500P2_mask.png`, `500P2_ir.png`, `500P2_inklabels.png`). Trouve le chemin équivalent pour PHerc0343P.
- Pour chaque fichier de couche et de masque : URL, `Content-Length`, format, dimensions et type de pixel (lus dans l'en-tête seul). Note aussi les noms et tailles des fichiers d'IR, de photo et d'étiquettes, **sans les télécharger**.
- Écris `docs/validation/phase17-inventory.json`. Si une pile ne contient pas les couches 02 à 63, ou si aucun masque n'est publié, arrête-toi et documente l'écart dans le rapport : n'invente pas de masque.

#### 4.2 Protocole figé avant toute lecture de pixel de couche

Commit **avant** de télécharger la moindre couche :

- `docs/validation/phase17-protocol.json`, avec :
  - les fragments, les URL de base et le hash de `main` ;
  - **la règle de sens inchangée** : même statistique (médiane par couche de l'écart-type intra-masque), mêmes patchs de 64 px, et la même sélection de patchs que `phase11_geometry.select_patches` (mêmes paramètres et même graine, adaptées seulement aux dimensions de la pile) ;
  - **l'adaptation des extrémités**, qui est la seule différence déclarée : les piles commencent en 02, donc `low = 02–14` et `high = 51–63`, avec 13 couches de chaque côté, comme en phase 13 ;
  - **le critère de décision** : rapport `r = max(std_low, std_high) / min(std_low, std_high)`. Si `r ≥ 2`, conclure (l'extrémité au plus faible écart-type est l'air). Si `r < 2`, déclarer le résultat « indéterminé ». Pour mémoire, Frag4 donne `r ≈ 5,8`. N'ajuste pas ce seuil après coup ;
  - les descripteurs secondaires, **sans valeur de décision** : moyenne par couche (le critère d'EconLearn), couche où l'écart-type est maximal, couche où la moyenne est maximale, fraction de voxels proches de zéro par extrémité ;
  - un budget de téléchargement par fragment (voir 4.3), et la règle d'arrêt en cas de dépassement.
- `docs/validation/phase17_orientation.py`, qui importe `direction`, ou en reprend le corps à l'identique, depuis `phase13_eval.py`. Seuls le lecteur de couches (PNG au lieu de TIFF non compressé) et les extrémités changent. Ajoute l'empreinte SHA-256 du protocole dans un dictionnaire `PROTOCOL_SHA` propre à la phase 17 et refuse un protocole modifié, comme en phase 14 (fins de ligne normalisées).
- Le message de commit dit explicitement : « protocole figé avant toute lecture de couche ».

#### 4.3 Lecture des couches

- Les PNG ne se lisent pas par plages d'octets. Mesure la taille réelle (`Content-Length`) avant de choisir une méthode :
  - si une couche entière tient dans le budget, télécharge-la dans `data/phase17/` (hors Git), calcule son SHA-256 et décode-la ;
  - sinon, décode en flux (par exemple `pypng`, lecture ligne à ligne) et ne garde en mémoire que les lignes qui coupent les patchs.
- Ne lis que les 26 couches des extrémités (02–14 et 51–63) et le masque. La couche 32 est optionnelle, comme contrôle de la surface.
- Vérifie que toutes les couches ont les mêmes dimensions que le masque. Le budget par défaut est de 8 Gio téléchargés par fragment ; au-delà, arrête et documente.
- Avec une couche 8 bits, ne convertis rien : la règle compare deux extrémités de la même pile, l'échelle n'importe pas. Note le type de pixel dans le JSON.

#### 4.4 Sorties

- `docs/validation/phase17-orientation.json` contient, pour chaque fragment : le profil d'écart-type médian par couche, les moyennes des deux extrémités, `r`, l'extrémité retenue comme air (ou « indéterminé »), les descripteurs secondaires, les SHA-256 des fichiers lus, le nombre de patchs et le hash du protocole.
- Contrôle de reproductibilité : relance la règle avec une autre graine de sélection de patchs (déclarée dans le protocole) et donne la conclusion obtenue, sans valeur de décision.
- Tests dans `tests/test_phase17.py`, sans réseau :
  - pile synthétique (côté papyrus texturé, côté air lisse et **plus clair**) : la règle choisit l'air par la texture et non par la luminosité ;
  - un cas où `r < 2` renvoie « indéterminé » ;
  - un protocole modifié est refusé ;
  - le lecteur PNG en flux et le lecteur complet donnent les mêmes patchs sur un petit PNG généré.

### 5. Vérifier que la pile 500P2 est le rendu `500p2a` de l'entraînement

Sans données sensibles :

- Dans le script Villa épinglé (`deprecated/ink-detection/train_resnet3d_3d_decoder.py` au commit `c8f3ba45304f0a317a49a155929e30d294f201eb`, voir `docs/PHASE11_TRAINING_INDEPENDENCE.md`), relève le chemin, le nom de segment, la plage de couches et les dimensions attendues pour `500p2a`, ainsi que la ligne exacte où `reverse_layers=True` est appliqué, et ce qu'elle fait (inversion de l'axe des couches lues ? avant ou après la sélection de la fenêtre ?).
- Compare avec l'inventaire : nom du dossier, nombre et numérotation des couches, dimensions, et `pred_shape` [4608, 13824] si ça s'applique.
- Classe la correspondance en trois niveaux : **établie** (même chemin ou mêmes dimensions et numérotation), **plausible** ou **non établie**. La conclusion sur l'ordre physique d'entraînement ne vaut que si la correspondance est établie, et le rapport le dit.

### 6. Étape B (soumise à l'accord du PO, ne pas commencer sans lui)

Reproduction exploratoire des ROC-AUC d'EconLearn avec notre chaîne (inférence de la phase 11, W2, tuiles 256/128, fusion Hann), dans les deux ordres, sur PHerc0343P. Avant tout lancement :

- vérifier la licence des lettres tracées et de l'IR de PHerc0343P, ainsi que celle de `ir-truth-9um` (Domenico Russo) ;
- figer un protocole séparé, `phase17b-protocol.json` (ROI tirées sans étiquettes, négatifs, tolérance de recalage, bootstrap par ROI ou par composante, comme le recommande la phase 15) ;
- déclarer d'emblée que l'analyse n'est pas aveugle, puisque les scores d'EconLearn sont connus.

Si le PO n'a pas donné son accord, écris seulement le projet de protocole, marqué « non figé ».

### 7. Livrables et ordre des commits

1. Inventaire, protocole, script et tests (aucun pixel de couche lu). Message : « Phase 17 : protocole figé de l'orientation des piles 2 µm, avant toute lecture de couche ».
2. Résultats : `phase17-orientation.json` et la vérification de `500p2a`.
3. Rapport `docs/PHASE17_ORIENTATION_2UM.md`, dans le style des phases 13 à 16. Il commence par la réponse en gras, en une ou deux phrases, puis donne la chronologie avec les commits, le tableau des résultats, la lecture (avec le tableau de décision de la section 3), les limites et la suite.
4. Mise à jour du brouillon `docs/PHASE17_COMMUNITY_REPLY.md` : remplis le paragraphe « Our result on your stacks » en anglais, en trois à cinq phrases factuelles, sans image ni chiffre tiré d'étiquettes.
5. Nouvelle section « Phase 17 » en tête de `docs/CLAUDE_HANDOFF.md` ; description de PR dans `docs/PHASE17_PR.md`.

### 8. Règles à ne pas enfreindre

- **N'ouvre en étape A** ni les étiquettes d'encre, ni l'IR, ni la photo, ni les lettres tracées, ni `ir-truth-9um`. L'inventaire n'en lit que les métadonnées HTTP.
- Ne modifie aucun protocole déjà figé (`phase13-protocol.json`, `phase14-protocol.json`, `phase16-protocol.json`) ni leurs empreintes.
- Ne change ni le seuil `r ≥ 2` ni les extrémités après avoir vu un profil. Si une règle se révèle inapplicable, documente l'échec plutôt que de la corriger en silence.
- Ne publie ni image, ni découpe d'étiquette, ni transcription (licence EduceLab-Scrolls).
- Pas de données lourdes dans Git : tout ce qui est téléchargé va dans `data/phase17/`.
- Lance la suite complète (`pytest`) avant le dernier commit et donne le nombre de tests dans le rapport. Les tests réseau restent désélectionnés.
- Rédaction : phrases courtes, accents corrects, aucune conclusion au-delà de ce que montrent les chiffres. « Indéterminé » est un résultat acceptable.

### 9. Ce que tu rends au PO

Un résumé de cinq lignes au plus :

1. le côté air de chaque pile et `r` ;
2. le niveau de correspondance de 500P2 avec `500p2a` ;
3. la conclusion du tableau de décision ;
4. la liste des commits ;
5. ce qui attend son accord (étape B, envoi de la réponse).
