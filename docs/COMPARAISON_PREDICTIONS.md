# Comparer les prédictions Reader sur une surface

Le panneau **Vesuvius — Comparer les prédictions** superpose les cartes A
(orange) et B (bleu) au CT projeté ou à la surface déroulée. Les deux cartes
partagent les coordonnées, le zoom et le point de vue. Régler le seuil
commun et l’opacité pour explorer la zone. Activer **Désaccord au seuil**
pour colorer les pixels où une seule carte atteint le seuil. Les accords
et les pixels dont un score manque sont transparents dans ce mode.
Le champ **Analyse** affiche aussi le consensus positif ou la
différence signée A−B. L’orange indique un score A plus élevé
et le bleu un score B plus élevé. La différence et le consensus
sont attachés à la même grille UV que les deux TIFF.

Utiliser une vue napari 2D dédiée au repère UV. Les couches CT 3D d’une autre scène utilisent des voxels ZYX. Le panneau compare des artefacts déjà projetés sur une grille UV commune. L’exporteur doit attester leur recalage, orientation, origine, recadrage et pas physique avant de créer le manifeste.

## Manifeste version 1

Préparer le CT projeté, le rendu de surface et jusqu’à quatre cartes dans le même dossier que le manifeste, ou dans ses sous-dossiers. Chaque TIFF doit être un plan scalaire de taille maximale de 1 048 576 pixels. Utiliser des fichiers de même forme en ordre `[v, u]`, v en lignes et u en colonnes. Les plans peuvent contenir des NaN pour les zones indisponibles. Les prédictions utilisent des scores entre zéro et leur `score_scale` déclaré.

```json
{
  "version": 1,
  "axes": ["v", "u"],
  "volume_id": "20250728140407",
  "segment_id": "20260316000000",
  "surface_revision": "nom-ou-hash-de-la-grille-orientee",
  "origin_vu": [640, 1200],
  "pixel_size_um_vu": [9.362, 9.362],
  "ct": "ct-projection.tif",
  "surface": "surface-deroulee.tif",
  "predictions": [
    {
      "name": "Reader V3",
      "model": "Reader V3, run et révision des poids",
      "path": "reader-v3.tif",
      "score_scale": 255,
      "provenance": {"checkpoint": "révision-ou-hash", "pile": "identifiant-de-la-pile"}
    },
    {
      "name": "Modèle témoin",
      "model": "Nom, version et révision des poids",
      "path": "temoin.tif",
      "score_scale": 1
    }
  ]
}
```

Pour un TIFF Reader entier 8 bits encodé sur `[0, 255]`, renseigner `255`. Pour une probabilité flottante sur `[0, 1]`, renseigner `1`. Un seuil de 50 % correspond alors à 127,5 et 0,5 unités des fichiers respectifs. Cette conversion harmonise l’affichage. Une même valeur de seuil ne démontre pas une calibration équivalente des modèles.

Pour une carte avec calibration attestée, ajouter
`"calibration": {"method": "...", "reference": "...", "event": "..."}`.
Le champ `reference` identifie les données et la recette de
validation. Le panneau affiche une différence de probabilités
lorsque les deux cartes déclarent une calibration pour le même
événement. Sinon, il affiche une différence de scores normalisés.
L’analyse et la calibration déclarée sont conservées dans
la session et la provenance des captures.

Le chargement valide les axes, l’origine, le pas, le format des plans, leurs formes et la plage des scores. Les métadonnées napari gardent le volume, le segment, la révision de surface, l’origine, le modèle et le fichier source. Les poids et les cartes sont produits par le pipeline Reader ou PyTorch/CUDA. Le contrôle de performance ou de précision d’un modèle doit porter sur des cartes calculées sur la même pile orientée, des témoins sans encre, et des zones annotées indépendantes. [Reader V3](https://github.com/DomRusso2/reader-v3) · [Tutoriel Vesuvius](https://scrollprize.org/tutorial5)

## Régions, captures et candidats

- Saisir la ligne V, la colonne U, la hauteur et la largeur dans **Région**.
  La boîte s’affiche sur les plans et les bornes dans le repère du segment
  apparaissent sous les champs.
- **Exporter la région en PNG** compose une image à la résolution des
  données à partir du fond et des réglages du panneau. Le bloc texte
  PNG `vesuvius_comparison` contient le JSON de provenance, les bornes
  [début, fin[ en pixels source et en µm, ainsi que les candidats. La
  vignette utilise le contraste min/max du plan de référence.
- **Ajouter un candidat à la région** associe un libellé hypothétique
  à la boîte courante. Sélectionner le candidat pour retrouver sa boîte
  ou le retirer. Le statut exporté `candidat_non_valide` exige une
  validation indépendante avant toute lecture paléographique confirmée.
- **Enregistrer la session** et **Reprendre une session** conservent les
  cartes sélectionnées, le mode, le seuil, l’opacité, la région et les
  candidats. Le manifeste et les pixels TIFF sont vérifiés par SHA-256
  à la reprise. L’objet facultatif `provenance` accueille les paramètres
  amont disponibles, par exemple la révision de la pile, l’orientation
  des normales, la méthode de projection, la normalisation et le hash
  des poids.
