# Phase 6 · Désaccord des cartes, CUDA et dossier d’examen

1. **Désaccord PHerc0500P2.** Le top 1 % de A occupe deux blocs et
   n’intersecte jamais celui de B pour les 14 641 translations
   testées. Le support commun et le contrôle CT favorisent la
   grille historique. Les corrélations globales sont sensibles
   aux 833 800 zéros partagés. [Audit et mesures](PHASE6_MODEL_DISAGREEMENT.md)
2. **Inférence CUDA.** Le checkpoint canonique public A tourne en
   FP32 sous Windows natif sur la RTX 4080 Laptop. L’inversion
   des 62 coupes suffit sur une tuile à rendre disjoints les top
   1 % et 5 % du même checkpoint. Les poids exacts de B, le
   digest de production et la face anatomique restent à établir.
   [Validation CUDA](../encre/CUDA_INFERENCE_VALIDATION.md)
3. **Évaluation.** Les huit fenêtres EduceLab restent utilisables
   pour le contrôle géométrique et la relecture exploratoire de
   l’IR et du CT. Aucun rouleau réservé à l’évaluation de ces
   checkpoints n’a été attesté. [Audit d’indépendance](../encre/EDUCELAB_INDEPENDENCE_AUDIT.md)
4. **Relecture.** Quatre régions de PHerc0500P2 ont été sélectionnées
   par des critères numériques explicites et conservées avec leurs
   sources dans un ZIP rouvrable dans napari. Elles sont à examiner.
   [Protocole et régions](../encre/CANDIDATE_REVIEW_PROTOCOL.md)
5. **Expérience suivante.** Obtenir le checkpoint B et les deux
   empreintes de production, puis croiser A et B avec les deux
   ordres Z sur la même grille et le même assemblage. Des fenêtres
   documentées avant le calcul permettent de tester si l’effet
   mesuré sur une tuile s’étend à d’autres régions. La face
   anatomique et l’encre requièrent une référence indépendante.

## Branche et restauration

La phase 6 utilise `feat/vesuvius-phase6` au départ de
`eba4082134df544dc56b5f9d6622d9fd0161f36c`. À la reprise, l’index
était vide et l’arbre contenait 61 modifications et ajouts des
phases précédentes. La branche précédente reste au même commit.
La nouvelle branche reprend les modifications de travail locales.
Le ZIP `data/phase6-restore/phase5-before-phase6.zip` contient
l’état Git, le patch binaire des suivis, les fichiers modifiés et
non suivis, ainsi que 32 entrées de reproduction locales. Son
contrôle CRC et les empreintes SHA-256 des entrées ont été vérifiés.

Le fichier `phase5-before-phase6.sha256` donne
`a1434f2de548d058aea71bc37107bf70acabd60fc6b16514ab50083bf7f255c4`.
Pour reconstituer l’état dans un répertoire de travail neuf,
partir du commit indiqué dans `restore.json` et recopier le contenu
de `tree/` aux mêmes chemins. Les listes `modified` et `untracked`
distinguent les deux ensembles. L’archive reste locale et inclut des
données avec leurs conditions de réutilisation propres. Les mesures
phase 5 et les artefacts sources ont été conservés.

## Vérification

Les calculs d’accord, la proposition de régions et les exports
s’exécutent dans les workers napari. Python reste le moteur
par défaut et le noyau Rust reste optionnel. L’environnement
de comparaison garde CUDA et PyTorch en dehors de ses dépendances.

La suite Windows native avec napari donne **334 réussites** et
un test ignoré pour le codec optionnel. Les **8 contrôles réseau**
réussissent sous Python 3.12 avec le codec. Les 73 contrôles ciblés
Rust, volumes et géométrie réussissent avec le moteur Rust activé.
Les tests valident notamment l’ordre Z, les décalages sur témoin
asymétrique, les ex æquo et données invalides, la sélection du
panneau, l’export répétable et la réouverture du dossier.

```powershell
$env:QT_QPA_PLATFORM = 'windows'
$env:LOCALAPPDATA = Join-Path $PWD 'data/phase6-appdata-confirm'
$env:VESUVIUS_RUST_SAMPLER = '0'
.venv/Scripts/python.exe -m pytest -q --basetemp data/phase6-tests-confirm
```

[Passation scientifique et technique](../../CLAUDE_HANDOFF.md)
