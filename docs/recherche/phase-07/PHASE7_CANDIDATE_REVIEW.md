# Phase 7 · Quatre régions pour une relecture indépendante

Le dossier local `data/phase7/examen-PHerc0500P2-phase7.zip`
préserve le CT, la surface UV, les deux TIFF publics, les deux
sorties assemblées du checkpoint public A et quatre annotations
descriptives. Les sources ont été contrôlées avant comparaison.
Chaque région garde un lien vers son identifiant phase 6, ses
coordonnées, le critère de sélection original et son identifiant
dans le nouveau dossier. Les annotations indiquent la coupe
CT observée et les incertitudes.
[Notes et identifiants d’origine](../../validation/phase7-candidate-notes.json) · [Rapport par région](../../validation/phase7-model-comparison.json)

| Région phase 6 | Bornes [V,U], fin exclusive | Observation au CT et sur les cartes | Question de relecture |
|---|---|---|---|
| `1cd8a75406a446a6deb3`, A seule | [516,764] → [644,892] | Texture granuleuse et structures obliques diffuses à la coupe 59. Le plateau de A publié réapparaît dans A+. A− reste bas. B présente un gradient différent. | La réponse large est-elle liée au relief du support ou à un autre signal en profondeur ? |
| `c6d6da47479063e44ef2`, B seule | [644,764] → [772,892] | Plages sombres bordées de reliefs en arc, avec un point clair en haut à gauche. B publié sélectionne une zone diffuse. A+ retrouve le gradient de A publié. | B/A− est proche par rang (0,759), malgré l’amplitude faible de A−. Comparer les coupes voisines et la continuité des bords. |
| `5121a59842084faad865`, A et B | [644,636] → [772,764] | Bande allongée, claire, légèrement inclinée, à deux bords visibles. Les plages de scores élevés restent larges et décalées. Le critère de top 5 % commun porte sur onze pixels. | La bande suit-elle des fibres ou un bord de couche ? Faire la première lecture sans les cartes. |
| `0a451e906e4d03a32bd0`, témoin bas | [516,508] → [644,636] | Lignes claires quasi parallèles formant un faisceau oblique. Une structure transverse apparaît à une extrémité. Les scores restent principalement faibles. | Ce témoin aide à reconnaître les motifs CT susceptibles d’être pris pour des tracés. Son statut négatif pour l’encre n’est pas établi. |

La sélection reste celle de la phase 6. Elle couvre deux
désaccords, une intersection rare et un témoin, à partir du
top 5 % des cartes publiques et de leur seuil de scores bas.
La relecture des images dans la phase 7 a été descriptive.
Aucune région n’a reçu d’hypothèse de lettre ou de validation
paléographique. [Règle de sélection](../encre/CANDIDATE_REVIEW_PROTOCOL.md)

## Parcours de relecture

1. Décompresser le ZIP et ouvrir `session.json` avec **Reprendre
   une session**. Examiner le CT et le rendu moyen sans cartes
   visibles avant de prendre des notes.
2. Choisir une région dans la galerie. Comparer A publié et B
   publié avec **Désaccord au seuil**, puis regarder les deux
   résultats contrôlés via **Comparer les conditions Z en 2 × 2**.
   La grille affiche l’empreinte UV commune, les scores sur CT,
   le top 1 % avec ex æquo et les histogrammes. B+ et B− sont
   indiquées comme indisponibles.
3. Documenter la coupe, le motif observé et les causes possibles
   (fibres, frontière de couche, artefact). Associer une référence
   vérifiable à toute interprétation paléographique proposée.
   Relecture et validation externe restent des étapes distinctes.
4. Exporter le dossier d’examen. `examen.json` permet de vérifier
   les SHA-256. Remettre le dossier avec le contexte des modèles,
   les bornes UV et les conditions d’attribution des données.
   Le cartouche B désigne une carte publique, tandis que B±
   désigne des interventions non mesurées.
   [Attribution des données](https://github.com/ScrollPrize/open-data#support-and-citation)

Le montage de travail `data/phase7/relecture.png` présente les
mêmes régions à échelle fixe. Le rapport machine conserve aussi
l’effet A+/A−, les rapprochements descriptifs et les notes pour
chaque fenêtre.

```powershell
.venv/Scripts/python.exe docs/validation/phase7_compare.py data/phase7 docs/validation/phase7-model-comparison.json --notes docs/validation/phase7-candidate-notes.json
.venv/Scripts/python.exe docs/validation/phase7_visuals.py docs/validation/phase7-model-comparison.json data/phase7/review/comparison.json docs/validation/phase7-contrasts.png data/phase7/relecture.png
```
