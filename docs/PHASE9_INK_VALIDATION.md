# Première confrontation avec l’encre optique

Le modèle A n’a pas été évalué contre ν2. Le champ n’est pas localisé, la couche et la face pertinentes dans le CT restent indéterminées et l’échelle physique n’est pas corroborée. Les conditions de calcul d’une précision, d’un rappel ou d’une AUC ne sont donc pas réunies. L’analyse de la phase 8 demeure une mesure de sensibilité des scores à l’ordre Z. [Localisation](PHASE9_CT_OPTICAL_REGISTRATION.md) · [Indépendance](PHASE9_DATA_INDEPENDENCE.md)

## Comparaison admissible après validation géométrique

1. Geler l’identification du champ, du volume et de la face, la calibration, les repères d’ajustement et de contrôle, le masque utilisable et la transformation. Conserver leur provenance. Les scores A± et les masques d’encre sont masqués pendant le choix des repères et la validation de la transformation.
2. Reprojeter l’annotation binaire sur la grille CT et croiser les supports finis. Employer les acquisitions natives pour l’évaluation. Appliquer la même géométrie et les mêmes pixels à A+ et A− et rapporter les deux orientations.
3. Rapporter VP, VN, FP, FN, précision, rappel/sensibilité, spécificité, Dice et Jaccard aux seuils préétablis de 20, 35, 50, 65 et 80 %. Pour les deux classes présentes, conserver la courbe précision–rappel, l’AUC ROC, l’AUC PR trapézoïdale et la précision moyenne. Les ex æquo sont groupés et une métrique sans dénominateur reste indéfinie.
4. Répéter sur les pixels éloignés des frontières du masque au-delà du P90 géométrique plus un demi-pixel CT, puis pour des déplacements systématiques selon les deux axes. Documenter les tailles et classes après masquage. Les analyses de sensibilité ne règlent ni les seuils ni l’orientation. À terme, pour une campagne multi-champs, échantillonner l’incertitude par blocs et regrouper par manuscrit.
5. Attribuer le statut **indépendant** seulement si l’ascendance exhaustive du modèle et l’exclusion du manuscrit sont attestées. Avec une géométrie fiable et une ascendance inconnue ou liée, classer les mesures comme **exploratoires** et préciser l’emprise éventuellement partagée.

[Calcul conditionnel des mesures](../src/vesuvius_data_explorer/core/optical_validation.py) · [Critères géométriques](PHASE9_GEOMETRIC_UNCERTAINTY.md)

## Inspection dans napari

Dans **Vesuvius — Comparer les prédictions**, utiliser **Ouvrir une validation CT–optique** et sélectionner [le manifeste local](../data/phase9/validation/validation.json), ou extraire [le dossier portable](../data/phase9/validation-CT-optique-phase9.zip). Le chargement vérifie les SHA-256 des couches et présente le CT59 et la photographie dans deux repères explicitement distincts. Les couches conservent la surface déroulée, le relief, le masque et les deux cartes A. Elles peuvent être affichées individuellement. Par défaut, le masque d’encre et A± sont masqués. Le bouton d’export regroupe le manifeste, ses sources visuelles et leurs empreintes. Pour un manifeste avec repères, le panneau affiche les mesures individuelles et la provenance. Il ne crée une couche recalée et une carte d’incertitude qu’après validation du recalage, de la localisation et de l’échelle. La face reste un critère supplémentaire pour les métriques d’encre.

Les images du pilote restent dans leurs repères d’origine, avec un décalage d’affichage réservé à la présentation. Aucune superposition CT–optique réelle n’est présentée. Les seuls contrôles de scores exécutés ici sont des tests sur données synthétiques, avec résultats attendus vérifiables.
