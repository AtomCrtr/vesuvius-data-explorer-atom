# T10 — Carte d'alignement et recalage des surfaces tifxyz (candidature Progress Prize)

- **Origine :** décision du PO du 18 novembre 2026 ; état de l'art
  [I2](../investigations/I2-etat-de-l-art-2026.md).
- **Statut :** spécification validée par le PO le 18 novembre 2026 (5 points, section finale).
  Première version développée et validée sur 8 segments réels
  ([validation](../validation/T10-carte-alignement.md)) ; **un écart à décider** (section « Écarts
  constatés »).
- **But :** une contribution qui **fait avancer directement le déroulement**, condition des Progress
  Prizes, sur un problème ouvert nommé par l'équipe du Vesuvius Challenge : la qualité des surfaces
  tracées (dérive hors de la feuille, sauts de feuille), le **label snapping** et l'**apprentissage
  actif**.

## Ce que l'outil fera

Pour un segment tifxyz et son volume :

1. **Carte de décalage dense.** Pour chaque tuile de la grille (par défaut 8 × 8 points, soit
   160 voxels de côté), la distance signée entre la surface et la feuille de papyrus la plus proche,
   le long de la normale (méthode de T5.1), avec sa **fiabilité** (proéminence) et son
   **incertitude** (borne de Cramér-Rao, section 3.2 de I2).
   - **Choix du pic** : le maximum local le plus proche de la surface, raffiné sous le pas
     (parabole), et non plus le maximum le plus clair de la fenêtre. L'audit d'I2 (section 4,
     point 7) a montré que l'ancienne règle peut choisir une feuille voisine quand les feuilles
     sont serrées.
   - **Référence** : la carte publie le décalage brut et le décalage **relatif à la médiane du
     segment**. Les surfaces publiées sont en médiane à environ −10 µm du centre clair de leur
     feuille (elles suivent probablement une face) : c'est la dérive par rapport à cette
     habitude qui compte, pas l'écart au centre.
2. **Sauts de feuille localisés par le signal CT.** Le décalage est converti en phase
   `φ = 2π·d/Δ`, où `Δ` est l'espacement des feuilles estimé sur le segment (autocorrélation du
   profil moyen). Les **résidus** de phase sur chaque boucle de 2 × 2 tuiles signalent un saut de
   feuille (section 3.3 de I2). Contrôle direct en complément : décalage entre tuiles voisines
   supérieur à `Δ/2`.
3. **Zones à revoir, par ordre de priorité.** Liste des régions à faire corriger par un humain :
   sauts de feuille, dérive forte et fiable, zones sans feuille identifiable. Elle est triée par
   gravité, avec les coordonnées 3D de chaque région (apprentissage actif).
4. **Recalage (label snapping), sur demande.** Le champ de décalages est régularisé : moindres
   carrés pondérés par la fiabilité, avec une pénalité de régularité, pour le lisser sans franchir
   les sauts de feuille. Chaque point est ensuite déplacé le long de sa normale, de son **décalage
   relatif** : la surface garde la face qu'elle suivait. Le résultat est un
   **nouveau dossier tifxyz**, dont `meta.json` note la provenance. L'original n'est jamais modifié.
   Les zones de saut de feuille et les zones peu fiables ne sont **pas** déplacées.
5. **Preuve visuelle.** Rendu aplati de la surface avant et après recalage, en échantillonnant le
   volume sur la surface : on doit y **voir les fibres de papyrus** plus nettement, comme le demande
   le règlement des prix. Une coupe transversale montre la surface sur la feuille.

## Sorties (formats de la communauté)

- `decalage.tif`, `fiabilite.tif`, `incertitude.tif` : cartes float32 aux dimensions de la grille
  des tuiles, avec une correspondance documentée vers la grille du segment.
- `zones.json` : régions à revoir (type, gravité, boîte en (ligne, colonne), centre 3D en voxels du
  niveau 0).
- `recale/` (sur demande) : tifxyz recalé (`x.tif`, `y.tif`, `z.tif`, `meta.json`).
- `rapport.html` : carte colorée des décalages, sauts de feuille, rendus avant et après, chiffres.
- Commande : `vesuvius-qc carte <segment> --volume <URI> [--recaler] -o <dossier>`, avec
  `--catalogue <identifiant du segment>` pour retrouver automatiquement le volume et sa taille de
  voxel.
- napari : calque coloré sur la trace du segment et liste des zones à revoir dans le widget
  Surfaces. Sélectionner une zone centre la coupe à ses coordonnées 3D.

## Validation (avant toute candidature)

1. **Décalages synthétiques non uniformes.** Sur des segments réels, appliquer une dérive lente
   connue (par exemple une rampe de 0 à 40 µm) et un saut de feuille artificiel (une région décalée
   de `Δ`). Critères :
   - la carte retrouve la dérive à 2 pas d'échantillonnage près sur au moins 80 % des tuiles
     fiables ;
   - au moins 80 % des sauts artificiels sont localisés, pour au plus une fausse alerte par segment
     sain en moyenne.
2. **Recalage.** Après une dérive imposée, le recalage ramène le décalage médian sous 1 pas
   d'échantillonnage. Sur des segments publiés, il ne dégrade jamais la proéminence moyenne.
3. **Fibres.** Rendus avant et après sur au moins 5 segments de 3 résolutions. Mesure quantitative
   de la netteté des fibres (énergie de la dérivée perpendiculaire aux fibres, ou contraste local)
   et inspection visuelle, documentée.
4. **Coût.** Temps et voxels lus pour un segment médian et un grand segment ; budget respecté.
5. **Comparaison honnête** avec les outils voisins (ScrollFiesta, raffinement nnInteractive, patchs
   de W. Stevens) : ce que T10 apporte (mesure chiffrée et incertitude, sauts localisés par le signal,
   aucun GPU ni modèle entraîné) et ce qu'il ne fait pas.

## Diffusion et candidature

- Publication tôt dans le mois visé, sur le dépôt public et PyPI (T9), avec une documentation
  **bilingue** (anglais pour la communauté et le jury, français pour le projet) et des images.
- Message illustré sur le **Discord du Vesuvius Challenge** (canal des outils) pour obtenir des
  retours et de l'usage, que le jury prend en compte. **L'inscription au Discord, à faire par le PO,
  est obligatoire pour être primé.**
- Formulaire mensuel des Progress Prizes, avec la validation ci-dessus.
- Calendrier (décision du PO) : **essayer l'échéance du 30 novembre 2026** ; si la validation
  n'est pas complète à temps, candidature fin **décembre 2026**. Aucune candidature sans la
  validation ci-dessus.

## Écarts constatés au développement (à décider par le PO)

1. **Sauts de feuille par la phase : non applicable aux données réelles.** L'espacement des
   feuilles n'est mesurable sur aucun des segments essayés : les feuilles ne forment pas un réseau
   périodique à l'échelle d'une tuile. La détection fonctionne sur données synthétiques et reste
   dans le code, mais le critère 1b ne peut pas être validé. Un saut de feuille réel n'apparaît
   que comme zone peu fiable ou forte dérive.
2. **Cible du recalage.** Par défaut, le recalage ramène chaque tuile au décalage habituel du
   segment : une dérive locale disparaît, un décalage d'ensemble reste. Ajout de l'option
   `--cible` (décalage visé, en µm) pour corriger aussi un décalage d'ensemble.
3. **Plafond de déplacement** (50 µm par défaut, `--deplacement-max`) : au-delà, la tuile a pu
   accrocher une autre feuille ; elle n'est pas déplacée et reste signalée.
4. **Zones exclues.** Tous leurs points restent fixes. Depuis le 22 novembre 2026, chaque tuile
   recalée est déplacée en bloc et le maillage forme une marche à la frontière. La transition
   sur une demi-tuile brouillait les tuiles recalées, presque toutes en bordure, et faisait
   échouer le critère 2b ([diagnostic](../validation/T10-carte-alignement.md#7-correctif-de-la-transition-et-critère-2b-révisé)).
5. **Netteté des fibres.** Fibres visibles sur tous les rendus ; sur des segments publiés, déjà bien
   placés, aucun gain de netteté mesurable (intensité +0,7 à +3,4 %, contraste −0 à −5 %). Le gain
   est net sur un segment dégradé volontairement.

## Hors périmètre

Remplacer GrowPatch, lasagna ou le spiral fit ; corriger automatiquement les sauts de feuille (ils
sont signalés, pas réparés) ; détection d'encre ; intégration C++ dans VC3D (étape suivante possible,
après des retours de la communauté).

## Décisions du PO (18 novembre 2026)

1. Calendrier : viser le **30 novembre** si possible, sinon la **fin décembre 2026**.
2. Recalage **sur demande**, sans jamais modifier l'original, et **sans déplacer** les zones de saut de
   feuille ni les zones peu fiables : validé.
3. Documentation **bilingue** (anglais et français) : validé.
4. Inscription du PO au **Discord du Vesuvius Challenge** et message de présentation (texte préparé
   par l'orchestrateur) : validé.
5. Étapes ultérieures, selon les résultats : recalage optimal par graphe (I2, section 3.4) et
   critère de courbure de Gauss (I2, section 3.5) : validé.
