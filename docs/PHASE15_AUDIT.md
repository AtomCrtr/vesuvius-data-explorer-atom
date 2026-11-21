# Phase 15 · Audit a posteriori du résultat de la phase 14

**Le résultat de la phase 14 tient.** Retirer n'importe quelle ROI ne fait pas tomber H3, et les deux ROI presque parfaites ne doivent rien au bord du support. Elles reflètent une grande composante d'encre bien classée, pas un artefact. Mais Frag5 dépend fortement d'une seule ROI, et une partie du classement se joue à l'échelle de la région plutôt que du trait.

Ce rapport est **exploratoire par construction**, car les étiquettes ont déjà été lues en phase 14. Les scores, ROI, supports et règles d'inclusion sont ceux de la phase 14, inchangés. [Script](validation/phase15_audit.py) · [valeurs](validation/phase15-audit.json)

## 1. Robustesse de H3 au retrait d'une ROI

Borne basse à 95 % de la ROC-AUC regroupée de Z_out, en retirant une ROI à la fois (bootstrap apparié 64², 499 tirages, graine 208).

| | Toutes les ROI | Pire retrait | Sans la ROI signalée |
| --- | ---: | ---: | ---: |
| Frag2 | 0,630 [0,599 ; 0,658] | ROI 2 : 0,600 [0,571 ; 0,628] | — |
| Frag5 | 0,730 [0,696 ; 0,760] | ROI 1 : 0,603 [0,567 ; 0,643] | ROI 1 : identique au pire retrait |
| Frag6 | 0,768 [0,740 ; 0,794] | ROI 4 : 0,740 [0,710 ; 0,769] | ROI 7 : 0,756 [0,728 ; 0,781] |

H3 tient pour **chacun des 20 retraits**. Frag5 perd 0,13 de ROC-AUC sans sa ROI 1 : sur ce fragment, l'effet regroupé repose en bonne partie sur une seule région.

## 2. Les deux ROI presque parfaites

| | Frag5 ROI 1 | Frag6 ROI 7 |
| --- | --- | --- |
| ROC-AUC Z_out / sur le cœur (sans la bande de 32 px au bord) | 0,987 / 0,987 | 1,000 / 1,000 |
| Témoins B1 / B2 | 0,63 / 0,52 | 0,42 / 0,57 |
| Composantes d'encre dans la ROI | 1 | 1 |
| Part des pixels d'encre à moins de 32 px du bord | 2 % | 17 % |
| ROC-AUC locale de Z_out (blocs 64² contenant les deux classes) | 0,90 sur 19 blocs | 0,97 sur 4 blocs |
| ROC-AUC avec étiquettes décalées de 500 / 1000 µm | 0,83 / 0,68 | 0,71 / 0,57 |

- **Pas d'artefact de bord.** La ROC-AUC calculée sur le cœur est identique, et l'écart dépasse 0,011 sur aucune des 20 ROI. Z_out est un peu plus élevé près du bord du support, sans étiquettes (ROC-AUC médiane de 0,56 pour « près du bord » parmi les pixels sans encre), mais cela ne pèse pas sur les résultats.
- **Une seule composante par ROI.** Frag5 ROI 1 contient un grand morceau d'étiquette, sur la moitié basse de la ROI. Frag6 ROI 7 n'en contient qu'un petit bout (7 346 pixels) collé au bord haut. Chacune vaut donc à peu près un seul exemple indépendant, quel que soit son nombre de pixels.
- **Un classement local réel.** Dans les blocs de 140 µm qui contiennent les deux classes, Z_out sépare encore l'encre du papyrus (0,90 sur 19 blocs pour Frag5 ROI 1), alors que la texture B2 n'y arrive pas (0,42). Pour Frag6 ROI 7, quatre blocs seulement : c'est trop peu pour conclure.

Un examen visuel local (superpositions non versées, licence EduceLab) va dans le même sens. Il n'est donné qu'en complément des mesures ci-dessus.

## 3. Échelle du signal sur les 20 ROI

| Décalage des étiquettes (µm) | 25 | 50 | 100 | 200 | 500 | 1000 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Variation médiane de la ROC-AUC de Z_out | −0,001 | −0,002 | −0,006 | −0,022 | −0,074 | −0,146 |

- La ROC-AUC baisse surtout entre 200 et 1000 µm, c'est-à-dire à l'échelle de la largeur des traits étiquetés (tableau ci-dessous). Un décalage de 100 µm ne la change presque pas. Le test ne peut donc pas distinguer un accord sur le trait d'un accord à 100 µm près.
- La ROC-AUC locale de Z_out (médiane 0,585) dépasse 0,5 dans 19 ROI sur 20 et B2 dans 16 sur 20, mais elle reste nettement sous la ROC-AUC globale. Une partie du classement vient donc de différences entre régions de la ROI, et pas seulement du contraste au bord des traits.

## 4. Granularité des étiquettes (image entière, grille au quart)

| | Composantes ≥ 0,01 mm² | Largeur inscrite médiane (µm) | P90 (µm) | Part de la plus grande composante |
| --- | ---: | ---: | ---: | ---: |
| Frag1 | 52 | 525 | 726 | 12,7 % |
| Frag2 | 193 | 440 | 734 | 2,2 % |
| Frag3 | 45 | 406 | 569 | 8,0 % |
| Frag4 | 71 | 427 | 568 | 8,8 % |
| Frag5 | **17** | 576 | 700 | **18,2 %** |
| Frag6 | 34 | 605 | 771 | 7,4 % |

Les étiquettes ont partout la même nature : des traits d'environ 0,4 à 0,6 mm de large, pas de grands polygones. Frag5 n'en a que 17, et la plus grande pèse 18 % de l'encre. Cela explique sa dépendance à une seule ROI.

## Conséquences

- Z_out reste un ordre par défaut justifié, et le critère de la phase 14 ne repose pas sur une ROI particulière.
- Dans les rapports, compter les ROI ou les composantes d'encre plutôt que les pixels. Les intervalles par blocs de 64² restent optimistes, car une composante couvre de nombreux blocs.
- Pour un prochain protocole : un bootstrap par ROI, ou par composante d'encre, en plus du bootstrap par blocs, et un minimum de composantes par ROI à la place du minimum de 1 000 pixels.

## Limites

- Analyse a posteriori sur des étiquettes déjà vues : elle peut affaiblir le résultat de la phase 14, pas le renforcer.
- Les étiquettes de Frag2, Frag5 et Frag6 ne sont pas validées géométriquement contre l'IR. Un décalage global de quelques centaines de µm resterait indétectable ici.
- La granularité est mesurée sur une grille de 13 µm, avec un seuil de 0,01 mm² pour les composantes.
