# Protocole de relecture des régions candidates

Le dossier local `data/phase6/examen-PHerc0500P2.zip` contient
quatre régions de la fenêtre CT auditée. Décompresser l’archive et
ouvrir `session.json` avec **Reprendre une session** dans le panneau
napari. **Galerie des observations** recentre la vue et présente le
CT, la surface UV et les deux scores sources. L’onglet **Provenance**
de la fenêtre d’accord expose les identifiants, réglages déclarés,
révisions et références des modèles.
[Sélection et paramètres](validation/phase6-review-windows.json)

## Règle de sélection

**Proposer des régions par rang** examine une grille de blocs
disjoints de 128² à l’intérieur du recadrage courant. Pour une
fenêtre plus petite, la taille est ramenée à sa dimension minimale.
Les blocs incomplets et ceux ayant moins de 75 % de scores appariés
finis sont écartés. Les top 5 % de chaque carte sont calculés sur
l’ensemble du recadrage courant, avec tous les ex æquo au seuil.
Les blocs sont retenus dans cet ordre, A seule, B seule, intersection
puis témoin de scores bas sur les deux échelles (<20 %).
Pour chaque catégorie, le bloc encore disponible qui possède la
plus grande fraction de pixels de la catégorie est proposé.
Les ex æquo se départagent par V puis U. Un bloc déjà utilisé
n’est pas repris. L’ordre de priorité explique que le bloc
d’intersection contienne peu de pixels mutuels. Une catégorie
vide n’est pas forcée.

La règle utilise uniquement les scores, leur masque de validité et
des coordonnées fixes. Elle ne compare aucune forme à un alphabet.
Elle conserve la formulation de la règle et les effectifs avec
chaque région. Les coordonnées ci-dessous sont des bornes [V,U]
sur la grille historique à 2,215 µm, fin exclusive.

| Identifiant | Catégorie | Début → fin | Pixels de la catégorie |
|---|---|---|---:|
| `1cd8a75406a446a6deb3` | A seule | [516,764] → [644,892] | 5 164 / 16 384 |
| `c6d6da47479063e44ef2` | B seule | [644,764] → [772,892] | 6 305 / 16 384 |
| `5121a59842084faad865` | A et B | [644,636] → [772,764] | 11 / 16 384 |
| `0a451e906e4d03a32bd0` | Témoin bas | [516,508] → [644,636] | 4 847 / 16 384 |

Pour le premier passage, examiner le CT et la surface seules et
consigner les motifs et défauts visibles. Puis afficher A et B
séparément et le désaccord au seuil. Documenter les rapports aux
fibres, fissures et bords. Relire aussi le témoin de scores bas.
Le périmètre se limite au CT vérifié de la phase 4 et à la grille
retracée dans Atlas.

## Niveaux d’annotation

| Niveau | Ce qui est enregistré |
|---|---|
| Trace observée | Description d’un motif dans une représentation nommée et coordonnées exactes. |
| Encre candidate | Compatibilité proposée avec de l’encre, accompagnée du modèle et du critère de sélection. |
| Caractère hypothétique | Interprétation explicitement incertaine, critères de forme et références de comparaison éventuelles. |
| Caractère validé par expertise | Confirmation explicitement cochée, avec observation, hypothèse, expert ou experte, preuve indépendante et référence paléographique. |

Le logiciel enregistre l’attestation saisie. Les preuves et
l’expertise se vérifient hors du logiciel. Un identifiant DOI,
une cote, une ligne et une figure, ou une page d’édition citée
servent de point de contrôle. L’assistance reste documentaire,
sans transcription ni promotion automatique d’une hypothèse.
La figure 3 de Parsons et al. montre la présentation séparée
des lectures et des incertitudes sur Frag3. Elle ne permet pas
d’attribuer ces caractères aux régions PHerc0500P2.
[Référence de méthode](https://arxiv.org/html/2304.02084v4#S2.F3)

## Dossier reproductible

**Exporter le dossier d’examen** assemble le PNG de la vue, les
TIFF copiés octet pour octet, le manifeste copié, une session
rouvrable et `examen.json`. L’index consigne les SHA-256 des fichiers
et les identifiants, sources et coordonnées restent résolus depuis
le manifeste archivé. La session conserve les paramètres de rendu,
le seuil, le mode, l’opacité et les annotations. La copie valide
de nouveau le manifeste et les pixels avant publication de l’archive.
L’export s’effectue en arrière-plan et se termine par remplacement
atomique du fichier. Les chiffres de sélection utilisent le rang,
tandis que l’aperçu livré affiche le désaccord au seuil de 50 %.

```powershell
.venv/Scripts/python.exe docs/validation/phase6_review.py data/phase6 data/phase4-ink/comparison-phase5.json data/phase5-reference docs/validation/phase5-reference-windows.json docs/validation/phase6-cuda-windows.json docs/validation/phase6-review-windows.json
```
