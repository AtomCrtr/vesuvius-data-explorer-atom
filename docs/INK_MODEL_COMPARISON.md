# Comparaison de cartes d’encre publiées

## Sources examinées

Le dépôt contient les témoins contrôlés de la phase 3 et des liens
vers Reader V3. La publication Reader V3 fournit le checkpoint
et les instructions d’inférence, des figures compositées ainsi
que des tableaux de métriques par région. L’inventaire du dépôt
public ne contient que les figures, les JSON et les scripts de
reproduction pour ses essais comparatifs. Les figures utilisent
des fenêtres d’affichage propres aux modèles. L’auteur décrit la
sortie TIFF 8 bits comme un score relatif. La campagne cible
Reader V3 et épingle la révision de ses poids.
[Publication Reader V3](https://github.com/DomRusso2/reader-v3) · [Checkpoint public](https://huggingface.co/domenicor046/reader-v3)

L’Atlas contient une paire de cartes pleine résolution pour
PHerc0500P2, segment `20250919184428`, ciblant l’acquisition
`20250526151718`. Les publications de ces modèles et le
protocole de traitement sont distincts du code de l’explorateur.
Le répertoire de mesures enregistre les URI, les identifiants
Atlas, les empreintes des TIFF et des pixels, les ETag, les
paramètres de modèle publiés et le SHA du catalogue de départ.
[Catalogue et conditions d’attribution](https://github.com/ScrollPrize/open-data#support-and-citation) · [Mesures](validation/phase4-ink-windows.json)

| Carte | Modèle public, d’après le catalogue | Données disponibles |
| --- | --- | --- |
| A | `20260417190342`, new canon autoresearch, ResNet3D-152 et décodeur 3D | TIFF uint8, tuile 256, stride 128 |
| B | `20260709123958`, mrg20736-1um-s1z2, ResNet3D-152 | TIFF uint8, tuile 256, stride 128, inversion de rendu déclarée par le modèle |

## Ce que le test valide

Les deux TIFF sont des plans de 1 160 × 1 400, d’orientation TIFF
usuelle, comme les plans YX de la pile publiée de 118 profondeurs.
Le TIFXYZ historique compte 58 × 70 sommets et un pas nominal de
20 pixels, cohérent avec ces dimensions. La pile donne 2,215 µm
par pixel UV. Les trois sources sont recadrées à la même origine
V/U `[388, 508]`, sur 384 × 384 pixels. Le fond CT vient du plan
59 de la pile et la vue déroulée de la moyenne des plans 57–61.
Les masques et les différences utilisent les valeurs TIFF
telles que publiées, en conservant le type et les octets des
pixels. La comparaison du score divisé par 255 harmonise l’unité
d’affichage.

La révision t2 et le TIFXYZ historique sont testés comme témoins
CT à quatre fenêtres UV. Ces contrôles confrontent les valeurs
interpolées CT L0 à la pile effectivement publiée. Au plan 59,
la corrélation est de 0,966–0,981 avec le TIFXYZ historique et de
0,600–0,884 avec t2 dans les quatre fenêtres de 19×19 pixels. Le
meilleur plan est 58 ou 59 pour le témoin historique. Ce contrôle
établit la cohérence locale du raster avec la projection historique.
Les TIFF n’établissent
pas la révision exacte, le choix de face ni la transformation
utilisés pour produire **chacun** des deux TIFF de scores.
L’Atlas indique un mesh historique remplacé et les configurations
de candidats diffèrent. La paire sert donc à une exploration
dans la grille publiée et aux tests du panneau. L’estimation
d’exactitude par rapport au CT et les conclusions sur les
lettres restent bloquées.

| Seuil commun | A seule | B seule | Consensus positif | Les deux sous le seuil | Jaccard positif |
| --- | ---: | ---: | ---: | ---: | ---: |
| 35 % | 37 043 | 13 066 | 60 926 | 36 421 | 0,549 |
| 50 % | 35 941 | 13 428 | 45 060 | 53 027 | 0,477 |
| 65 % | 40 114 | 12 808 | 28 697 | 65 837 | 0,352 |

L’écart signé moyen A−B est de 0,125 et l’écart absolu moyen de
0,242 sur cette fenêtre, en unités de score normalisé. Ces valeurs
mesurent la concordance des deux exports. Les taux d’erreur et les
probabilités absolues exigent des références indépendantes et une
calibration documentée. Les TIFF de ce lot portent des scores
quantifiés. La résolution des logits de départ et leur calibration
ne sont pas documentées.

Le panneau a été exécuté dans napari avec les deux TIFF issus de
cette fenêtre. Les trois modes produisent une trame utile.
Sur ce passage natif, le chargement du panneau dure 671 ms.
La différence, le consensus puis le désaccord s’affichent en
254, 88 et 115 ms. L’ajout du premier calque d’analyse est
compris dans la mesure de différence.
Le script enregistre et recharge une session comprenant une
annotation témoin, puis exporte une capture PNG de la boîte
160×160 avec origine, pas, modèle, calibration et statut de
l’annotation. Les tests de non-régression contrôlent également
l’annulation logique d’un calcul dépassé. Les TIFF et captures
restent dans le dossier de travail. [Mode d’emploi](COMPARAISON_PREDICTIONS.md)

## Protocole pour une première campagne RTX 4080 Laptop

Le pilote observe 12 282 Mio de VRAM sur la machine testée. La
campagne vise deux modèles, une pile identique, une seule face
fixée par les repères, une validation géométrique avant inférence
et un maximum de huit fenêtres de 512² par acquisition. L’essai
des cartes publiées ci-dessus est une qualification technique
distincte. Les mesures de qualité et de faux positifs commencent
après vérification des labels et des manifestes d’entraînement.

1. **Geler les entrées.** Épingler Reader V3 et un modèle
   `ink_9um` public dont la fiche permet d’auditer le split,
   ainsi que leur code d’inférence. Utiliser le même rendu natif
   ~9 µm, pas normal, pose, contexte UV et masque. Hacher les
   poids, rendus, labels, masques et la configuration. Enregistrer
   les révisions de volume et surface, la préparation du stack,
   l’ordre des axes et de la profondeur, la transformation UV et la
   licence. Toute orientation choisie doit être fixée en validation
   par un repère indépendant.
2. **Séparer les rôles par papyrus.** L’entraînement et les
   éventuelles données héritées des poids sont un ensemble
   d’exclusion commun. PHerc0841 est candidat pour la validation
   de la calibration et du seuil. PHerc1447, notamment w058, est
   candidat pour l’évaluation gelée, avec annotations humaines
   indépendantes. Reader V3 publie des essais sur ces deux
   rouleaux. Geler la liste exacte des segments et contrôler
   le chevauchement avec les ancêtres des deux checkpoints
   avant de déclarer ces ensembles admissibles. En cas de
   provenance d’entraînement inconnue, réserver le cas à
   l’exploration et chercher un témoin admissible.
   [Fiches `ink_9um`](https://huggingface.co/scrollprize/ink_9um) · [Annotations](https://huggingface.co/buckets/scrollprize/datasets/tree/ink_9um/README.md)
3. **Contrôler le recalage avant le GPU.** Chercher au moins
   quatre repères espacés dans chaque fenêtre sur la pile,
   la projection CT et le témoin indépendant. Exiger un résidu
   d’au plus un pixel dans le raster final et une orientation
   confirmée, enregistrer les pixels exclus et tester les
   inversions comme contrôles négatifs. Corriger le rendu en
   amont si une transformation est attestée, puis régénérer
   les deux entrées et leurs empreintes. Les prédictions restent
   hors de la décision de recalage.
4. **Faire tenir l’inférence sur la machine.** Une fenêtre
   d’échauffement en validation avec batch 1, une seule
   tuile active, transformations d’inférence désactivées,
   `torch.inference_mode()` et mesures synchronisées CUDA.
   Garder la profondeur et la taille de tuile requises par le
   checkpoint, utiliser un recouvrement fixé. Démarrer avec une
   référence FP32, et n’autoriser un mode mixte qu’après comparaison
   des écarts sur validation. Relever pic GPU réservé et alloué,
   mémoire dédiée du processus, RSS, temps de préparation /
   inférence / assemblage, débit UV et débits S3 séparément.
   Pour chaque modèle, réaliser trois passages chronométrés
   avec ordre alterné. Utiliser le mode `--no-compile` sur
   Windows lorsque le pipeline Reader le demande.
5. **Évaluer sur des masques validés.** Étiqueter indépendamment
   les pixels évaluables en encre, papyrus vierge et surfaces
   exclues ou incertaines. Mesurer AP et précision/rappel, et
   le taux de pixels positifs sur papyrus vierge au seuil gelé
   en validation. Rapporter séparément les activations hors
   papyrus, le Jaccard de consensus, l’écart absolu entre scores
   et leur dispersion par fenêtre. Pour une probabilité estimée,
   ajuster un calibrateur sur validation, documenter la courbe
   de fiabilité, le score de Brier et le domaine d’application,
   puis appliquer sans ajustement à l’évaluation. Calculer les
   intervalles par rééchantillonnage des fenêtres plutôt que des
   pixels corrélés. Pour l’outil, relever première trame, temps de
   changement de mode, p50/p95/max Qt et sortie PNG contrôlée.
6. **Relire les candidats.** Exporter des zones de consensus,
   de désaccord et des témoins négatifs, avec coordonnées et
   provenance. Deux relectures indépendantes, idéalement avec
   photo ou acquisition de référence, sont nécessaires avant
   toute interprétation paléographique. Conserver les désaccords
   des relecteurs et les révisions dans la session.

```powershell
$env:QT_QPA_PLATFORM = 'windows'
$env:XDG_CACHE_HOME = Join-Path $PWD 'data/phase4-cache'
.venv/Scripts/python.exe docs/validation/phase4_ink.py data/rust2/catalog.json data/phase4-ink data/phase4-ink-windows.json --napari
```

Le catalogue passé au script est le document JSON public
`metadata.json`, éventuellement gzip, du bucket Open Data.
