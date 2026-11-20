# Pauses du thread graphique napari

Le profil rejoue l’ouverture et la navigation PHerc0800 de la phase 3
dans trois processus frais par version. Une minuterie Qt demandée
toutes les 10 ms mesure les intervalles de service jusqu’à la
première trame OpenGL. Les appels tracés portent une horloge commune,
leur identité de thread et le temps CPU du thread. Les intervalles
de méthodes imbriquées se chevauchent.
[Script](validation/phase4_napari.py) · [Avant](validation/phase4-napari-before.json) · [Après](validation/phase4-napari-after.json)

## Attribution du plus grand intervalle

À froid, les trois plus longs intervalles avant changement durent
402–435 ms. `OpenVolumeWidget._loaded` en occupe 384–420 ms,
presque entièrement dans `Viewer.add_image`. Le constructeur
`Image` prend 203–209 ms sur le thread graphique et le passage
`QtViewer._add_layer` 18–22 ms. Le reste correspond à l’insertion
dans la liste napari et à ses notifications synchrones. À chaud,
la construction du modèle passe sous 3 ms avant modification,
avec l’insertion et ses rappels encore sur le chemin critique.

Les lectures Zarr du contraste et de la vue s’exécutent dans leurs
workers. Dask calcule les ROI du benchmark hors du chemin de
l’application. La conversion du tableau vers la vue, le transfert
des textures et les shaders sont tracés distinctement. Les uploads
de texture à froid restent sous 4 ms par appel dans les traces.
Certaines trames et compilations de shaders ont des pointes séparées
du retard d’ajout du calque. La mesure attribue le retard dominant
de phase 3 au même chemin que les trois retards reproduits.

## Changement et résultat

Le worker construit le modèle `Image` avec ses données paresseuses,
avant son rattachement au viewer. L’insertion Qt/Vispy continue sur
le thread graphique. La barre indique l’ouverture et l’attente de
la première vue. Une modification du chemin invalide le résultat
et l’erreur de la requête en vol, même si l’utilisateur revient au
même texte avant la fin. Le test natif couvre ce scénario.

Les percentiles ci-dessous sont les médianes des trois répétitions.
La dernière colonne donne l’étendue du plus long intervalle d’une
répétition.

| Ouverture | Version | p50 Qt, ms | p95 Qt, ms | Maximum par processus, ms |
| --- | --- | ---: | ---: | ---: |
| À froid | Avant | 15,23 | 17,24 | 402–435 |
| À froid | Après | 15,26 | 17,53 | 196–207 |
| À chaud | Avant | 15,21 | 18,16 | 189–200 |
| À chaud | Après | 15,29 | 17,78 | 192–216 |

L’empreinte de la première tranche reste identique dans les six
processus à froid et à chaud. La première trame à froid varie de
5,96 à 13,76 s avant et de 5,47 à 13,36 s après. Le profil montre
une baisse du blocage maximal à froid. Il ne caractérise pas un
gain de temps de bout en bout sous cette variabilité S3 ni un gain
du maximum à chaud.

## Panneau de comparaison

La préparation des copies d’affichage et les calculs de différence,
consensus et désaccord s’exécutent hors de Qt. Un seul calcul
d’analyse est actif à la fois et les changements rapides ne gardent
que la dernière demande. Les tests instrumentent le thread
exécutant le calcul et vérifient qu’un résultat dépassé
n’apparaît jamais comme calque. Le profil sur les deux cartes
publiées relève séparément le temps de chargement du panneau et
les temps jusqu’à la trame de chaque analyse.
[Essai sur cartes réelles](INK_MODEL_COMPARISON.md)

## Reproduction

Exécuter le script phase 4 avec le source figé de la phase 3 dans
`PYTHONPATH`, puis avec la phase 4. Les scripts et données
proviennent du même dépôt. Le cache est isolé par répétition.

```powershell
$env:LOCALAPPDATA = Join-Path $PWD 'data/phase4-qt-profiler'
$env:QT_QPA_PLATFORM = 'windows'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONPATH = Join-Path $PWD 'data/phase4-base-src'
.venv/Scripts/python.exe docs/validation/phase4_napari.py data/phase4-ui-before data/phase4-napari-before.json
$env:PYTHONPATH = Join-Path $PWD 'src'
.venv/Scripts/python.exe docs/validation/phase4_napari.py data/phase4-ui-after data/phase4-napari-after.json
```

L’instantané local `data/phase4-base-src` a été pris avant
les modifications de la phase 4. Il conserve notamment les
optimisations S3 de la phase 3, de sorte que les deux séries
utilisent le même parcours réseau.
