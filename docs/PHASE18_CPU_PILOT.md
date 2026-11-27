# Phase 18 · Comparaison CPU sur une région de PHerc0343P

L’inversion des couches change fortement le classement des scores sur les **65 536 pixels** du cœur, avec une corrélation de Spearman proche de zéro aux deux pas. Changer le tuilage perturbe aussi la sélection des scores les plus élevés. Pour `Z_in`, les deux tuilages ne partagent aucun pixel parmi leurs 1 % les mieux classés. [Résultats JSON](validation/phase18-cpu-pilot.json)

| Comparaison sur le même cœur | Spearman | Écart absolu moyen des scores | Pixels communs dans le 1 % le mieux classé |
| --- | ---: | ---: | ---: |
| Ordre `Z_in` → `Z_out`, pas 256 | 0,021 | 0,273 | 0 / 656 |
| Ordre `Z_in` → `Z_out`, pas 128 | −0,007 | 0,250 | 15 / 656 |
| Pas 256 → 128, ordre `Z_in` | 0,598 | 0,125 | 0 / 656 |
| Pas 256 → 128, ordre `Z_out` | 0,781 | 0,150 | 262 / 656 |

Le pilote mesure la stabilité des scores du checkpoint A quand on change l’ordre des couches ou le tuilage. Il utilise la pile CT et le masque de préparation. Une mesure de ROC-AUC demande les étiquettes d’encre et intervient après le gel des cartes de l’essai complet. [Protocole de la phase 18](validation/phase18-protocol.json) · [Préparation du fragment](validation/phase18-prepare.json)

Le code choisit une fenêtre de 512 × 512 px sur la grille des tuiles, dont le cœur de 256 × 256 px est entièrement dans le masque. Parmi ces fenêtres, il prend celle dont le centre est le plus proche du centroïde du masque. Les quatre cartes utilisent le même cœur et les mêmes 62 couches (02–63). Le pas de 256 laisse une seule prédiction par pixel. Le pas de 128 fusionne les prédictions avec la fenêtre Hann du protocole. Les quatre tuiles communes aux deux pas sont calculées une seule fois par ordre, soit 18 inférences au total. [Script](validation/phase18_cpu_pilot.py)

Le cœur commence à `(v=6016, u=4480)` sur le canevas. Le pilote a pris 4 min 37 s avec PyTorch 2.8.0 et deux threads CPU. La médiane de 13,88 s par tuile donne environ 81 h pour les 21 108 inférences de l’essai complet sur cette instance, hors calcul des métriques. C’est une estimation à partir d’une seule région. [Mesures de temps](validation/phase18-cpu-pilot.json)

Pour reproduire le pilote depuis la racine du dépôt, utiliser l’environnement Python équipé de PyTorch et le cache préparé par la phase 18.

```sh
python docs/validation/phase18_cpu_pilot.py --output data/phase18/cpu-pilot.json
```

## Réplication et contrôles du tuilage

Les deux nouvelles fenêtres visent les lignes qui cumulent 25 % et 75 % de la surface du masque, à l’abscisse de son centroïde. Chacune suit la même grille de 256 px et contient un cœur entièrement masqué. Les fenêtres de 512 px sont disjointes entre elles et de celle du premier pilote. La règle et les tests ont été commités avant les inférences des deux régions (`3e90dcd`).

Les contrôles réutilisent les neuf tuiles par ordre et comparent les scores sur le même cœur dans chaque région.

| Contrôle | Comparaison |
| --- | --- |
| Décalage de grille | Pas de 256 px dans les deux cas, avec un décalage de 128 px sur les deux axes. La tuile centrale couvre alors exactement le cœur. |
| Recouvrement | Pas de 256 px et pas de 128 px, avec des poids uniformes dans les deux cas. |
| Pondération | Poids uniformes puis Hann, au même pas de 128 px et sur les mêmes tuiles. |

### Effet de l’ordre dans les trois régions

| Région et origine V/U du cœur | Spearman au pas 256 | Spearman au pas 128 | Pixels communs dans le top 1 %, pas 256 / 128 |
| --- | ---: | ---: | ---: |
| Centrale `(6016, 4480)` | 0,021 | −0,007 | 0 / 15 |
| Haute `(3456, 4480)` | −0,492 | −0,606 | 0 / 0 |
| Basse `(8320, 4480)` | −0,676 | −0,410 | 0 / 0 |

Chaque classement retient 656 pixels sur 65 536. Les deux ordres ont aussi des top 1 % disjoints dans les deux nouvelles régions avec la grille décalée au pas de 256 et avec les poids uniformes au pas de 128. Le changement de classement se répète dans le fragment, avec des corrélations plus négatives dans les deux nouvelles régions. [Région haute](validation/phase18-cpu-upper.json) · [Région basse](validation/phase18-cpu-lower.json)

### Pixels du top 1 % conservés par chaque contrôle

| Contrôle | Haute `Z_in` | Haute `Z_out` | Basse `Z_in` | Basse `Z_out` |
| --- | ---: | ---: | ---: | ---: |
| Décalage de la grille au pas 256 | 0 | 0 | 2 | 0 |
| Recouvrement avec poids uniformes | 41 | 0 | 175 | 0 |
| Ajout de Hann au pas 128 | 258 | 39 | 389 | 0 |

Le décalage de la grille change presque entièrement le top 1 %, même quand le pas et la fusion restent identiques. Le changement de pondération à tuiles identiques a un effet variable selon la région et l’ordre. Dans la région haute en `Z_in`, passer du pas 256 au pas 128 avec Hann déplace les scores de 0,008 en moyenne absolue et remplace tous les pixels du top 1 %. L’origine de la grille et les poids de fusion font donc partie des paramètres à fixer pour une comparaison de cartes. Ces mesures décrivent trois régions du même fragment à un seul checkpoint et portent sur les scores. [Données des deux contrôles](validation/phase18-cpu-upper.json) · [Région basse](validation/phase18-cpu-lower.json)

```sh
python docs/validation/phase18_cpu_pilot.py --region upper --output data/phase18/cpu-upper.json
python docs/validation/phase18_cpu_pilot.py --region lower --output data/phase18/cpu-lower.json
```
