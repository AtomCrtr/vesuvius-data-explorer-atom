# Phase 11 · Confrontation CT–IR : bloquée

> **Suite (phase 12).** L'évaluation a été faite après décisions et gel du protocole. [Rapport](PHASE12_INK_EVALUATION.md)

**Aucune métrique d'encre n'a été calculée sur Frag4. Les trois conditions d'ouverture fixées avant la phase ne sont pas réunies, et les étiquettes n'ont pas été téléchargées.** Calculer précision, rappel, Dice ou PR-AUC maintenant produirait des chiffres que l'on ne pourrait ni interpréter comme une généralisation ni défendre comme une mesure géométriquement correcte.

## Conditions et état

| Condition | Critère fixé avant la phase | État | Référence |
| --- | --- | --- | --- |
| Recalage | RMS et P90 réservés < 6,5 µm, couverture ≥ 25 % | **Non** : 52 µm médian sur une fissure, couverture limitée à cette fissure ; seuil inatteignable avec un IR natif de 20 µm/px | [Recalage](PHASE11_FRAG4_REGISTRATION.md) |
| Correspondance physique et prétraitement | Entrée de A dans le domaine de sa recette | **Non** : air ≈ 0,48 au lieu de 0, pas réel 3,05–4,09 µm, normalisation ÷ 255/÷ 200 non résolue | [Compatibilité](PHASE11_CHECKPOINT_COMPATIBILITY.md) |
| Indépendance | Exclusion de Frag4 attestée pour le poids exact | **Partielle** : absence probable de la liste publiée, ascendance des étiquettes inconnue | [Indépendance](PHASE11_TRAINING_INDEPENDENCE.md) |

La partie de l'étape E qui ne dépend pas des étiquettes, la sensibilité à l'ordre Z, a été exécutée. [Résultats](PHASE11_Z_GENERALIZATION.md)

## Protocole proposé pour lever le blocage

À décider et à geler **avant** de télécharger `PHercParis1Fr39_54keV_inklabels.png` :

1. **Tolérance spatiale.** Exclure des métriques une bande de 3σ ≈ 200 µm (≈ 62 px CT) autour des bords d'étiquettes, ou utiliser des métriques à tolérance (précision/rappel de bord à distance d), avec d fixé par le résidu B3. Rapporter aussi la sensibilité des métriques à un décalage imposé de 0, ±25, ±50 et ±100 µm.
2. **Fenêtre d'intensité.** Fixée sur le CT seul (niveau d'air, percentile du papyrus) et appliquée identiquement aux deux ordres Z.
3. **Zones et seuils.** ROI d'évaluation choisies par la règle géométrique déjà utilisée (masque érodé), seuils 0,5 et top-k pré-déclarés, PR-AUC si les deux classes sont présentes, intervalles par blocs.
4. **Statut.** Tant que l'attestation d'indépendance manque, l'intitulé reste « évaluation exploratoire, fragment probablement exclu de l'entraînement direct ».

L'outil existant `vesuvius-qc` (module `qc/ink.py`) calcule déjà VP, VN, FP, FN, Dice, Jaccard et AUC à partir d'un manifeste ; il suffira de lui fournir les cartes et la tolérance gelées.
