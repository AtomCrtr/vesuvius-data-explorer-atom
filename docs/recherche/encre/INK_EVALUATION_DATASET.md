# Fenêtres de référence indépendantes des cartes PHerc0500P2

Le jeu contient huit fenêtres de 128 × 128 pixels tirées de deux
surfaces exposées d’EduceLab-Scrolls. Chaque fenêtre contient le CT
uint16 à la coupe 32 du volume de surface, la photographie infrarouge
déjà recalée par les auteurs et les annotations dérivées de cette
photographie. Les surfaces sont PHercParis2Fr47 (Frag1, rouleau
Paris 2) et PHercParis1Fr34 (Frag3, rouleau Paris 1), à 54 keV et
3,24 µm. Les dossiers source documentent les rendus de 65 coupes.
[Article, §4.1.3 et annexe A.8](https://arxiv.org/html/2304.02084v4#S4.SS1.SSS3) · [Frag1](https://dl.ash2txt.org/fragments/Frag1/PHercParis2Fr47.volpkg/working/54keV_exposed_surface/) · [Frag3](https://dl.ash2txt.org/fragments/Frag3/PHercParis1Fr34.volpkg/working/54keV_exposed_surface/)

## Fenêtres et relecture

Les positions sont des couples [V,U] dans la grille publiée, avec
origine inclusive et borne haute exclusive. Les fenêtres sont
disjointes et sélectionnées sur une grille de pas 128 à partir du
masque et des annotations publiées. Les positifs ciblent 18 % de
pixels annotés, les traces clairsemées 1 %, le fond zéro et le bord
une couverture de masque proche de la moitié. Les ex æquo sont
départagés par V puis U. Aucun score modèle n’a servi à cette
sélection. [Manifeste, fenêtres et empreintes](../../validation/phase5-reference-windows.json)

| Fragment | Région | [V,U] début → fin | Pixels d’encre annotés | Pixels ignorés |
|---|---|---|---:|---:|
| Frag1 | `ink` | [1792,3328] → [1920,3456] | 2 955 | 0 |
| Frag1 | `background` | [128,4608] → [256,4736] | 0 | 0 |
| Frag1 | `sparse_traces` | [3584,3072] → [3712,3200] | 166 | 0 |
| Frag1 | `mask_edge_artifact` | [7808,2944] → [7936,3072] | 0 | 8 161 |
| Frag3 | `ink` | [5248,1024] → [5376,1152] | 2 944 | 0 |
| Frag3 | `background` | [128,3072] → [256,3200] | 0 | 0 |
| Frag3 | `sparse_traces` | [2688,2816] → [2816,2944] | 158 | 0 |
| Frag3 | `mask_edge_artifact` | [5248,0] → [5376,128] | 0 | 8 078 |

Dans `labels.tif`, 1 désigne l’encre annotée, 0 le fond selon
l’annotation et 255 l’absence de décision utilisable hors du masque.
Les 48 pixels annotés hors masque sur Frag3 sont exclus à la source.
Le fond annoté fournit un témoin négatif opérationnel. Les traces
clairsemées fournissent des cas difficiles à cause du déséquilibre
des classes. Les deux cas de bord illustrent un artefact de support
concret. Tous les pixels extérieurs des deux fenêtres de bord valent
zéro sur cette coupe CT. Ils servent au contrôle du masque. Le témoin
de fond Frag1 contient aussi 21 zéros CT à l’intérieur du masque, à
examiner avant de l’utiliser comme exemple de fond pour l’entraînement.

Pour la première relecture manuelle, ouvrir les trois TIFF de
`Frag3/ink`, puis ceux de `Frag3/sparse_traces` et
`Frag3/mask_edge_artifact`. Les bornes ci-dessus permettent de
retrouver chaque fenêtre. `ir.tif` fournit un contrôle visuel,
`labels.tif` porte l’annotation publiée et `ct.tif` permet de situer
les fibres dans le rendu. Aucun score des modèles PHerc0500P2
n’est disponible sur ces fenêtres.

```powershell
.venv/Scripts/napari.exe data/phase5-reference/Frag3/ink/ct.tif data/phase5-reference/Frag3/ink/ir.tif data/phase5-reference/Frag3/ink/labels.tif
```

### Caractères grecs de référence

La figure 3 de Parsons et al. compare la lecture d’un papyrologue
sur la référence photographique et sur la prédiction CT publiée
de Frag3. La figure documente notamment des caractères partagés comme
Η et Ν à la première ligne de la couche a, et marque d’autres traces
comme incertaines. Ces exemples restent rattachés aux lignes et
à la figure de la publication. Aucun cadre UV individuel n’a été
attribué en l’absence de coordonnées de caractères publiées.
[Figure 3 et protocole papyrologique](https://arxiv.org/html/2304.02084v4#S2.F3)

## Indépendance et admission en test

L’IR et ses annotations apportent une référence indépendante de
la prédiction CT. Les fragments ont été publiés pour entraîner et
évaluer des modèles. Les données qui ont effectivement alimenté les
deux poids de juillet restent inconnues. Les fenêtres ont donc le
statut `reference_only` (ou `mask_qa_only` au bord). Elles restent
hors de toute mesure supervisée des deux modèles actuels.

Pour constituer un test admissible, figer les données d’entraînement,
de pseudo-annotation, de réglage et de test par **rouleau parent**
et par révision de surface. Par exemple Frag1 et Frag2 appartiennent
à Paris 2, Frag3 et Frag4 à Paris 1. Documenter les ensembles de chacun
des checkpoints, prouver la séparation du rouleau et de ses dérivés,
puis produire des scores sur la même face, résolution et grille. Une
fois les seuils fixés sur un groupe de validation séparé, rapporter
précision, rappel, FPR et résultats par strate sur les négatifs
annotés. Compter les pixels 255 à part. Le petit jeu de cette phase
sert à vérifier la chaîne de données et à préparer cette admission.

## Reproduction et droits

```powershell
.venv/Scripts/python.exe docs/validation/phase5_reference.py data/phase5-reference docs/validation/phase5-reference-windows.json
```

Le script lit les masques et les photographies (environ 16 Mo),
puis uniquement les plages nécessaires de la coupe CT (environ
12 Mo au total). Les SHA-256 des fichiers légers et des pixels de
chaque fenêtre, les URI, les plages d’octets et les identifiants
du volume de surface sont dans le manifeste. La relecture locale a
retrouvé les huit sélections et vérifié les 24 empreintes de pixels.
Les images générées
restent dans `data/`. Les conditions propres au serveur EduceLab
s’appliquent à ces données, notamment l’attribution à EduceLab,
l’Université du Kentucky et Parsons et al. et les conditions
de redistribution. [Conditions du serveur EduceLab](https://dl.ash2txt.org/LICENSE.txt) · [Référence scientifique](https://doi.org/10.48550/arXiv.2304.02084)
