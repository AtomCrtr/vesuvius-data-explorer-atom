# Comparer les prédictions Reader sur une surface

Le panneau **Vesuvius — Comparer les prédictions** superpose une carte de scores au CT projeté ou au rendu de surface déroulée. Le choix de la prédiction et du fond garde les mêmes coordonnées, le même zoom et le même point de vue. Le seuil règle la transparence d’affichage. Les fichiers source et leurs valeurs restent disponibles pour les métriques et la revue scientifique.

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
      "score_scale": 255
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

Le chargement valide les axes, l’origine, le pas, le format des plans, leurs formes et la plage des scores. Les métadonnées napari gardent le volume, le segment, la révision de surface, l’origine, le modèle et le fichier source. Les poids et les cartes sont produits par le pipeline Reader ou PyTorch/CUDA. Le contrôle de performance ou de précision d’un modèle doit porter sur des cartes calculées sur la même pile orientée, des témoins sans encre, et des zones annotées indépendantes. [Reader V3](https://github.com/DomRusso2/reader-v3) · [Tutoriel Vesuvius](https://scrollprize.org/tutorial5)

La version suivante pourra ajouter des panneaux UV côte à côte synchronisés, des annotations exportables et un contrôle de provenance par hash. Enregistrer la génération CT, l’orientation des normales, la méthode de projection, la profondeur de la pile, les paramètres de normalisation et le hash des poids avant d’utiliser une telle comparaison pour une conclusion scientifique.
