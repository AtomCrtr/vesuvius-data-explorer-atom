# Validation indépendante des prédictions d’encre

Aucune des huit fenêtres EduceLab n’a d’exclusion de l’entraînement attestée pour les checkpoints étudiés. Une nouvelle référence optique documente l’encre sur quatre régions de PHerc0500P2. Son recalage sur le segment CT, la face commune et l’exclusion du fragment ou de ses dérivés des jeux d’entraînement restent à établir.

## EduceLab

Les images IR et annotations sont issues d’une observation des fragments exposés. Les TIFF d’encre Atlas ne servent pas de référence. L’audit vérifie le parent, les coordonnées, les empreintes des pixels CT/IR/annotation, les comptes des classes et le masque. Le comptage distingue les annotations 0 et 1 et les pixels 255 à ignorer. [Publication EduceLab](https://arxiv.org/html/2304.02084v4#A8) · [Données et conditions](../encre/INK_EVALUATION_DATASET.md) · [Huit traces](../../validation/phase8-ink-references.json)

| Fenêtre | Parent | Pixels annotés encre | Pixels ignorés | Classe d’usage |
| --- | --- | ---: | ---: | --- |
| Frag1 / ink | PHercParis2 | 2 955 | 0 | Évaluation exploratoire |
| Frag1 / background | PHercParis2 | 0 | 0 | Évaluation exploratoire |
| Frag1 / sparse_traces | PHercParis2 | 166 | 0 | Évaluation exploratoire |
| Frag1 / mask_edge_artifact | PHercParis2 | 0 | 8 161 | Contrôle géométrique |
| Frag3 / ink | PHercParis1 | 2 944 | 0 | Évaluation exploratoire |
| Frag3 / background | PHercParis1 | 0 | 0 | Évaluation exploratoire |
| Frag3 / sparse_traces | PHercParis1 | 158 | 0 | Évaluation exploratoire |
| Frag3 / mask_edge_artifact | PHercParis1 | 0 | 8 078 | Contrôle géométrique |

L’Atlas distingue les spécimens compatibles et les acquisitions, mais cela n’atteste pas les groupes exclus de l’entraînement. Le poids A public expose des hyperparamètres d’architecture, de normalisation et de durée, sans liste attestée des sources ou des groupes réservés. L’audit doit suivre chaque fragment jusqu’au manuscrit parent et couvrir les rendus dérivés, les pseudo-annotations et les phases d’ajustement du modèle. Les fenêtres de fond seules ne permettent ni rappel ni AUC. Aucune fenêtre ne remplit aujourd’hui les conditions d’une évaluation indépendante confirmée de ces poids. Aucun nouveau chiffre de précision, rappel, spécificité, faux positifs ou AUC n’est publié. [Audit public A/B](../phase-07/PHASE7_CHECKPOINT_AUDIT.md) · [Audit d’indépendance EduceLab](../encre/EDUCELAB_INDEPENDENCE_AUDIT.md)

## Autres sources publiques

| Source | Classe d’usage pour notre essai | Condition ou limite |
| --- | --- | --- |
| Profilométrie Angelotti et al., PHerc0500P2 | Évaluation exploratoire, avec un potentiel de validation indépendante | Géométrie et encre optique accompagnées de masques manuels. Il manque un rattachement vérifié à `wrap01_0919`, la preuve de face et l’exclusion des données d’entraînement. |
| Masque volumique du même scan, `0500p2_5217` | Contrôle géométrique | Le sondage n’observe pas d’intersection aux six témoins. |
| Papyrus carbonisé de référence, NIST MDS2-4227 | Contrôle géométrique et méthodologique | L’écriture sur matériau moderne et l’encre au plomb servent à tester une procédure de recalage et de contrôle. Le contraste obtenu ne mesure pas la performance sur l’encre carbonée antique. |
| `ink-labels` Vesuvius, annotations manuelles et pseudo-annotations sur CT | Non exploitable comme référence indépendante de l’encre pour cette campagne | La référence peut dériver des mêmes données et prédictions. |

[Article de profilométrie](https://pmc.ncbi.nlm.nih.gov/articles/PMC13547395/) · [Dépôt optique](https://huggingface.co/datasets/scrollprize/profilometer) · [Ressources NIST](https://data.nist.gov/od/id/mds2-4227) · [Étude du papier carbonisé](https://doi.org/10.1371/journal.pone.0353485) · [Catalogue d’annotations Vesuvius](https://scrollprize.org/data_datasets#ink-labels-2026-07)

Le manifeste optique épinglé à `a806bead2f3b9100c20e19de37814fb285cfeefd` contient 14 entrées, dont 4 pour PHerc0500P2 acquises le 23 septembre 2025. Pour ces quatre entrées, il indique un pas publié dans les fichiers de 0,68793625 µm par pixel et des champs dont les dimensions s’étendent de 3,09 à 4,89 mm en X et de 2,49 à 3,68 mm en Y. La publication décrit un échantillonnage de 0,34 µm. Le recalage doit vérifier l’échelle sur les coordonnées calibrées brutes et résoudre cette divergence avant d’utiliser le TIFF de hauteur normalisé. Les métadonnées vérifiées référencent la hauteur brute, le TIFF de hauteur, le champ clair et le masque. Elles ne donnent pas de transformation vers la grille U,V étudiée. La date d’acquisition antérieure au modèle A et la publication ultérieure ne prouvent aucune exclusion de l’entraînement. Le dépôt indique CC BY-NC 4.0. L’audit n’a téléchargé que les manifestes et métadonnées. [Manifeste épinglé](https://huggingface.co/datasets/scrollprize/profilometer/blob/a806bead2f3b9100c20e19de37814fb285cfeefd/manifest.csv) · [Réglages d’échantillonnage](https://huggingface.co/datasets/scrollprize/profilometer/blob/a806bead2f3b9100c20e19de37814fb285cfeefd/configs/sampling.json)

## Expérience suivante

1. Obtenir le rattachement des quatre acquisitions optiques à une photographie d’ensemble, aux repères du fragment et au côté observé. Prendre d’abord un seul champ et ses fichiers autorisés.
2. Choisir des repères géométriques, par exemple des contours, déchirures ou reliefs distinctifs, dans le CT et la topographie. Caler les repères dans la géométrie 3D, sans consulter les scores A. Vérifier la couche et sa face dans les coupes voisines. Rapporter l’erreur de recalage en micromètres sur des repères tenus à l’écart et geler le masque commun.
3. Obtenir l’exclusion documentée par manuscrit parent pour A et B. Si le recouvrement CT/optique est établi et l’exclusion confirmée, fixer les seuils avant lecture des annotations. Mesurer précision, rappel, spécificité, taux et nombre de faux positifs et AUC sur les classes présentes, avec sensibilité à la tolérance de recalage et incertitude par blocs. Quand l’exclusion demeure inconnue, classer les mesures éventuelles comme exploratoires.

## Checkpoint B et demande de reproductibilité

B est le modèle de production Atlas `20260709123958-mrg20736-1um-s1z2`, identifiant `mrg20736_1um_s1z2` avec `force_reverse=true`. Les recherches ciblées dans Villa, la fiche Atlas, le Hub officiel et le registre de poids n’ont pas trouvé les poids exacts. La fiche demandée au Hub a répondu HTTP 401 et l’accès anonyme au registre S3 HTTP 403. Les TIFF de production demeurent disponibles pour un examen descriptif. Aucune condition B± n’a été inférée. [Requêtes et métadonnées](../../validation/phase8-ink-references.json) · [Audit du registre](../../validation/phase7-checkpoints.json)

Brouillon à adresser à **erdpx**, intervenant et responsable déclaré sur le ticket public Villa. Envoi en attente d’accord. [Ticket Villa #1377](https://github.com/ScrollPrize/villa/issues/1377)

> Hello erdpx,
>
> We are reproducing the PHerc0500P2 Atlas ink maps on historical segment `20250919184428`. Could you point us to the exact weights and SHA-256 hashes, with their reuse terms, for `20260417190342` and `20260709123958-mrg20736-1um-s1z2`? The production job or container digests, input render revision, depth range and direction, preprocessing and tile assembly settings would also help us reproduce each map.
>
> For an independent evaluation, could you share the manuscript-level training and tuning groups or exclusions, including derived renders and pseudo-labels? In particular we are checking PHerc0500P2, PHercParis1 and PHercParis2. If there is a published registration from the PHerc0500P2 profilometry fields to the historical CT or a record of the photographed face, we would appreciate a pointer.
>
> Thank you.
