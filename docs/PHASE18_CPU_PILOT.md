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
