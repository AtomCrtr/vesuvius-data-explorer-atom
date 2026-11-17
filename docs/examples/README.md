# Exemples de rapports QC

`qc-synthetic.json` et `qc-synthetic.html` proviennent d'un volume artificiel propre à trois
niveaux 128³, 64³ et 32³, uint8, chunks 32³. L'URI `synthetic://…` est une étiquette explicite,
pas un chemin de données réel. Aucun volume CT original n'est inclus.

```bash
python docs/examples/generate_qc_example.py
```

La graine est 0. Le budget de 2 048 voxels réduit quatre ROI demandées à deux ROI de 32² au niveau
2 ; les dix contrôles passent (dont `volume.background`, informatif, à 0 %). Une seule clé de chunk est demandée (deux coupes du même chunk).
Les rapports régénérés sont identiques sauf `created_at` et `duration_s`.

Pour le test de trou de surface, `demo_surface(size=75)` donne 94,67 % de points valides et déclenche
`surface.valid` au seuil provisoire 95 %. La taille par défaut 180 ne contient que 300 points
manquants sur 32 400, soit 99,07 % valides : elle doit passer ce seuil. Le test réduit explicitement
la fenêtre synthétique, sans modifier les seuils ou le générateur existant.
