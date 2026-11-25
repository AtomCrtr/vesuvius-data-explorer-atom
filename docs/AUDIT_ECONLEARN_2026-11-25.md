# Audit du 25 novembre 2026 · la mesure d'EconLearn sur PHerc0343P, et la nôtre

**En bref : sur le sens, EconLearn a très probablement raison. Sur l'ampleur, ses chiffres ne permettent pas de conclure. Ce qui manque, on peut le combler nous-mêmes, sans attendre sa réponse.**

Sources : ses commentaires sur [villa#2627](https://github.com/ScrollPrize/villa/issues/2627) du 24 novembre (corrigé deux fois le 25) et du 25 novembre ; notre phase 17 ; l'inventaire `validation/phase17-inventory.json`.

## État du fil

- EconLearn **a retiré sa correction** du 25 novembre. Il écrit que cette correction « was mine and was wrong » et rétablit sa phrase d'origine : l'ordre inversé, papyrus → air, va dans le même sens que notre évaluation sur l'encre de Frag4.
- Il ne doute pas de ses chiffres. Ce qui reste incertain, c'est ce qu'il n'a pas mesuré : un intervalle sur l'écart entre les ordres, l'effet du pavage, et deux détails de reconstruction de la vérité terrain.
- Aucun mainteneur n'a répondu sur `500p2a`.

## Ce qu'il fait bien

1. **Aucun recalage.** Couches, IR, lettres tracées et masque partagent le même canevas. C'est un net avantage sur notre Frag4, où le recalage IR–CT laissait environ 52 µm de résidu.
2. **Entrée conforme à la recette.** 8 bits, écrêtage à 200, ÷ 200, 62 plans, pixel d'environ 2,215 µm. C'est le premier essai entièrement dans la recette de A. Sur Frag4, l'air n'était pas à zéro et le pas était de 3,24 µm.
3. **Le test de placement est bien conçu.** Déplacer les lettres en bloc garde leur forme et l'autocorrélation spatiale. Que les vraies positions battent les 2 000 placements aléatoires (meilleure ROC-AUC aléatoire 0,722), et qu'un décalage de 512 px effondre le score, montre que le signal suit les lettres, et pas seulement des régions du fragment. C'est plus robuste que notre bootstrap par blocs de 64², que nous savons optimiste.
4. **Le sens du résultat.** Notre règle de texture confirme sa lecture de l'air (r = 5,83). L'ordre qui gagne est donc `Z_out`, comme sur 5 de nos 6 fragments.
5. **Transparence.** Il donne ses effectifs, signale lui-même la différence de pavage et retire publiquement une correction fausse.

## Ce qui ne tient pas, ou pas encore

1. **L'ampleur de l'écart n'est pas due à l'ordre seul.** En ordre stocké, il a utilisé des tuiles sans chevauchement, au pas de 256. En ordre inversé, il a utilisé le pas de 128 avec fusion Hann. Sans chevauchement, chaque bord de tuile est prédit avec un contexte tronqué et sans pondération. Les coutures qui en résultent peuvent faire baisser la ROC-AUC. Une partie du passage de 0,599 à 0,936 peut donc venir du pavage. Le sens est probablement juste, l'ampleur est surestimée d'une quantité inconnue.
2. **Ses négatifs sont faciles.** Il ne garde que les pixels à au moins 12 px des lettres (environ 104 µm) **et** plus clairs que la médiane IR. Le papyrus sombre, abîmé ou taché est écarté, alors que c'est lui qu'un détecteur confond avec de l'encre. Les ROC-AUC absolues en sont gonflées. Comme les deux ordres partagent les mêmes négatifs, l'écart entre eux est moins touché, mais il n'est pas protégé pour autant.
3. **Pas d'intervalle sur la différence.** Le test de placement répond à la question « au-dessus du hasard ? ». Il ne dit pas si `Z_out` bat `Z_in` avec une marge sûre. Chaque chiffre vient d'un seul passage.
4. **PHerc0500P2 ne compte pas comme confirmation.** Le fragment fait partie de l'entraînement, et seul l'ordre inversé a été évalué.
5. **Le rapprochement avec 0,91 ne tient pas.** Ce score de la carte de l'équipe est mesuré contre la vérité de Russo, sur d'autres régions. Il l'avait cité « for reference », et notre réponse l'a déjà signalé.
6. **Deux détails manquent pour refaire son support.** Il ne dit pas comment il passe du canevas à la grille de 8,64 µm, ni sur quelle grille il calcule l'érosion de 10 px et la médiane IR.

## Nos propres faiblesses, à corriger dans T12

1. **Le pixel du canevas mesure environ 2,215 µm, pas 2 µm.** Son facteur 0,2564 × 8,64 µm donne 2,215 µm, la résolution de la recette de A, et le corps du ticket parle déjà d'un rendu à 2,215 µm. Toute conversion de µm en pixels (la tolérance de 301 µm, par exemple) doit utiliser 2,215 µm. Le nom `2um_front_surface` est arrondi.
2. **L'interprétation principale et le repli de T12 étaient trop rigides.** Si les deux échouaient, le support E devenait « approché ». Ses effectifs suffisent pourtant à trancher. On a six contraintes en tout (encre, propres et valides sur PHerc0343P ; encre et propres sur PHerc0500P2). Les effectifs ne dépendent que des étiquettes, de l'IR et du masque, et pas des cartes de scores, donc les chercher ne biaise aucune ROC-AUC. Les fichiers de PHerc0500P2 nécessaires pèsent environ 58 Mo, sans aucune couche.
3. **Les effectifs publiés sont cohérents avec une grille de 8,64 µm.** Sur le masque de 8416 × 13 924 px, la grille réduite fait 2158 × 3570 px. Ses 4 292 390 pixels valides en couvrent 56 %. Encre et propres représentent 53 % des valides, ce qui va avec le choix des pixels plus clairs que la médiane, calculée sur la région.
4. **T = 301 µm avait été fixé pour l'erreur de recalage de Frag4.** Sur un canevas commun, c'est très prudent : on écarte presque tous les négatifs difficiles proches des lettres. On le garde pour la continuité avec les phases 12 à 16, avec les sensibilités 100 µm et 0. Le rapport doit le dire.
5. **Notre décompte « 5 sur 6 » inclut Frag1 et Frag3,** fragments du concours Kaggle de 2023 dont l'absence de l'ascendance de A n'est pas attestée.

## Ce qu'on peut faire sans l'attendre

| Manque | Réponse de notre côté | Où |
| --- | --- | --- |
| Effet du pavage | Plan ordre × pas, mêmes cartes pour les deux ordres | T12, section 4.1 (déjà prévu) |
| Détails de reconstruction | Recherche dans un ensemble fini d'interprétations déclarées d'avance, choisie sur ses six effectifs, avant toute ROC-AUC | T12, section 4.3 (mis à jour) |
| Facilité de ses négatifs | Sensibilité « E sans filtre IR » et support N | T12, section 4.4 (ajouté) |
| Intervalle sur la différence | Bootstrap apparié par composante d'encre, avec son test de placement en complément | T12, section 4.4 (déjà prévu) |
| Taille du pixel | 2,215 µm, vérifiée par la cohérence avec son facteur 0,2564 | T12, section 4.1 (ajouté) |
| Rendu de `500p2a` | Hors de notre portée : il faut un mainteneur. On publiera nos SHA-256 pour qu'ils puissent comparer | Réponse à EconLearn |

## Recommandation

Lancer la phase 18 sans attendre. La réponse courte à EconLearn reste utile pour obtenir ses SHA-256, mais ses deux questions deviennent une simple confirmation : la recherche sur les effectifs les tranchera de toute façon.
