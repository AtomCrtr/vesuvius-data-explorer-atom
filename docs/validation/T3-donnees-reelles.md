# T3 — Contrôle qualité sur un volume réel masqué

Volume : `s3://vesuvius-challenge-open-data/PHerc0332/volumes/20251211183505-2.399um-0.2m-78keV-masked.zarr`
(URI vérifiée lors de la validation de T2 ; données : Vesuvius Challenge, *CT Scans of Herculaneum
Papyri*, CC BY-NC 4.0). Le rapport ne contient que des statistiques, aucune donnée image.

## Avant / après la gestion du fond

Mêmes paramètres que le rapport initial : `--level 5 --samples 1 --seed 0 --max-voxels 65536`.

| | Avant | Après |
|---|---|---|
| `volume.saturation` | **fail, 17,59 %** | pass, 0 % |
| `volume.background` (informatif) | — | pass, 17,59 % |
| Résumé | 8 pass, 1 fail | 10 pass |
| Code de sortie | 1 | 0 |

La part de fond mesurée est **exactement** l'ancienne « saturation » : l'échec venait des voxels mis
à 0 hors du rouleau par le masquage, pas d'une saturation du détecteur.

## Échantillon plus large

`--level 5 --samples 16 --seed 0` (1 048 576 voxels matérialisés, 5,5 s) : **10 pass**.
Fond échantillonné : 56,5 % ; 4 ROI sur 16 entièrement dans le fond, ignorées par les contrôles
de saturation, de zones vides et de contraste. Rapport complet :
[`t3-pherc0332-16roi.json`](t3-pherc0332-16roi.json).

Ces résultats ne valident pas les seuils sur un seul volume : ils restent provisoires.
