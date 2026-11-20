# Profil S3, Dask et napari sous Windows

19 novembre 2026. PHerc0800 `20250521135224`, six niveaux Zarr v2, voxels
`uint8` et blocs bruts de 128³. Windows x64, Python 3.11.9, Zarr 3.1.6,
Dask 2026.8.0, s3fs 2026.9.0, napari 0.10.0, Qt `windows` et RTX 4080
Laptop. La référence est le code de `eba4082`. Le script appelle le
point d’entrée du plugin avant et après les changements.
[Script de mesure](validation/phase3_profile.py)

Trois processus par version, avec cache disque vide au premier passage
et réouverture dans le même processus avec le cache rempli. Les vues
attendent une tranche chargée et une capture OpenGL non uniforme.
Quatre déplacements parcourent ensuite les coupes Z, avec un retour
sur la première coordonnée. Les essais Dask et Zarr directs suivent
des ROI axiales et coronales aux niveaux 0, 2 et 5, en alternant leur
ordre. Les empreintes des vues initiales et des quatre coupes
concordent entre versions.
[Avant](validation/phase3-profile-before.json) · [Après](validation/phase3-profile-after.json)

## Ouverture isolée et contribution des changements

Médianes de trois processus et étendues min–max. Les compteurs HTTP
comprennent les tentatives à la couche SDK, y compris `HEAD`, les
listages S3 et les réponses d’absence. Les octets utiles de métadonnées
sont de 4 477 à froid et de 0 après réouverture dans les trois séries.

| Version | À froid, s | HTTP | Réouverture, s | HTTP |
| --- | ---: | ---: | ---: | ---: |
| Référence | 4,13 [4,08–4,34] | 62 | 3,24 [3,23–3,24] | 36 |
| Tableaux réutilisés et niveaux lus en parallèle | 2,11 [2,05–2,16] | 48 | 0,74 [0,74–0,75] | 22 |
| Idem, un GET par objet S3 | 1,54 [1,52–1,60] | 24 | 0,41 [0,38–0,43] | 11 |

Chaque niveau est résolu une fois au moment de lire les attributs
NGFF. La même instance de tableau sert à napari ou à la construction
du graphe Dask. Jusqu’à huit résolutions indépendantes sont
découvertes en parallèle pour une pyramide distante non consolidée.
Le réglage `max_concurrency=1` évite la recherche de taille et le
fractionnement des petits objets dans s3fs 2026.9.0. Zarr continue
de lire plusieurs objets simultanément et peut demander des plages
dans les shards. En s3fs 2024.6, le paramètre est accepté et s’applique
aux téléversements. [Référence](validation/phase3-metadata-before.json) · [Niveaux seuls](validation/phase3-metadata-parallel.json) · [Deux changements](validation/phase3-metadata-after.json) · [Code de s3fs 2024.6](https://github.com/fsspec/s3fs/blob/2024.6.1/s3fs/core.py)

Zarr utilise les métadonnées consolidées lorsqu’elles sont publiées,
en v2 via `.zmetadata` et en v3 via `zarr.json`. Les tests vérifient
que les niveaux consolidés se résolvent sans requêtes enfant.
PHerc0800 utilise des métadonnées séparées.
[API de consolidation](https://zarr.readthedocs.io/en/latest/user-guide/consolidated_metadata/)

## Chronologie dans l’application

Médianes en millisecondes avec requêtes HTTP avant → après. Les
intervalles imbriqués et le chevauchement du travail Qt avec les
premières lectures empêchent d’additionner les lignes. Les requêtes
des premiers blocs incluent celles émises pendant l’ajout du calque.

| Étape | À froid, ms | HTTP | À chaud, ms | HTTP |
| --- | ---: | ---: | ---: | ---: |
| Construction locale du client fsspec | 2,65 → 7,22 | 0 → 0 | 0,16 → 0,16 | 0 → 0 |
| Racine, détection du format et attributs de groupe | 1 769 → 1 434 | 12 → 6 | 503 → 275 | 8 → 4 |
| Attributs des niveaux, formes, tri et construction des tableaux | 1 531 → 488 | 36 → 18 | 1 390 → 129 | 14 → 7 |
| Recherche répétée des tableaux dans la référence | comprise dans le total | 14 → 0 | comprise dans le total | 14 → 0 |
| **Total métadonnées** | **4 722 → 1 922** | **62 → 24** | **3 297 → 408** | **36 → 11** |
| Échantillon de contraste à L5 | 1 291 → 949 | 18 → 9 | 242 → 120 | 8 → 4 |
| Vue initiale à L4, de l’ajout du calque à la tranche prête | 9 011 → 2 195 | 88 → 44 | 872 → 380 | 42 → 21 |
| Capture OpenGL de la tranche prête | 9,4 → 12,9 | 0 → 0 | 11,4 → 10,4 | 0 → 0 |
| **Clic → première trame utile** | **15 161 → 5 486** | **168 → 77** | **4 628 → 1 110** | **86 → 36** |

L’étendue jusqu’à la première trame est de 9,51–17,27 s avant
et 5,18–5,69 s après à froid. À chaud, elle est de 4,59–4,67 s
avant et 1,08–1,11 s après. La capture chronomètre le canvas
OpenGL du processus.

À froid, les 28 blocs présents transfèrent 56 Mio dans les deux
versions, dont 10 Mio pour le contraste et 46 Mio pour les vues.
Avec les métadonnées, le total est de 58 724 733 octets utiles.
À la réouverture, les 36 GET après optimisation répondent 404,
avec 11 métadonnées de sondage et 25 blocs de remplissage absents.
Les compteurs portent sur les corps mesurés, hors en-têtes et
surcharge TLS. Le délai jusqu’aux en-têtes HTTP figure dans la
trace indépendamment de la durée de lecture de l’objet.

Chaque paire voit un seul client S3. Fsspec réutilise ses instances
selon les paramètres et le thread constructeur. Les vues initiales
sélectionnent L4, tandis que le contraste lit L5. Le
champ `tcp_tls` de l’essai complémentaire recense dix ouvertures
de socket de 228 à 245 ms à froid, qui se chevauchent. Le même
client réutilise ses sockets à chaud. La trace mesure ces
ouvertures à part du constructeur Python.
[Trace de connexion](validation/phase3-connections-windows.json)

## Graphe Dask, décompression et mémoire

- Napari indexe des tableaux Zarr paresseux. La construction d’un
  graphe Dask se mesure hors du parcours vers la trame. Son temps
  médian est de 4,32 → 3,88 ms sur neuf constructions. Une coupe
  sélectionne quatre blocs et produit neuf tâches, dont quatre
  lectures fusionnées avec la sélection et une finalisation. Le
  découpage Dask suit les blocs du store, y compris pour le v3
  shardé. Les 18 lectures Dask prennent 281 → 185 ms en médiane
  et les 18 lectures Zarr directes 390 → 204 ms. Ces séries
  mélangent S3, blocs disque et plages absentes. Le temps maximum
  Dask après atteint 3,78 s. L’alternance d’ordre révèle l’effet
  du cache et la dispersion réseau sur la comparaison.
- Chaque sortie de 48² pixels contient 2 304 octets. Quatre blocs
  bruts présents peuvent transférer 8 Mio. Zarr et Dask renvoient
  les mêmes octets de sortie. Le profil conserve le découpage
  natif des blocs, avec des allocations CPU et des copies OpenGL
  comptées dans les mesures de processus.
- Les blocs de PHerc0800 sont bruts. Les intervalles
  `codec_decode` couvrent la conversion locale des octets.
  Leur somme médiane à froid est de 10,3 → 17,9 ms et peut
  compter plusieurs intervalles simultanés. Le gain vient des
  requêtes évitées et des attentes réseau mises en parallèle.
  Le corpus scientifique mesure séparément le vrai codec
  `vc-delta3d`. Sur le volume publié, 62 décodages durent
  4,77 ms en médiane par bloc de codec. À L1, la ROI utilise 3 appels de store Zarr
  direct contre 16 via Dask, pour 3,28 contre 2,02 Mo utiles.
  Le regroupement des plages échange ici des octets contre des
  allers-retours. [Trace v3](validation/phase3-science-windows.json)
- La navigation passe de 733 [704–822] ms à 383 [374–432] ms
  jusqu’à la trame, sur douze coupes par version. Le cache disque
  sert les blocs présents et le réseau sonde encore les blocs
  absents. Le pic RSS médian est de 534 Mio dans les deux
  versions. WDDM relève 32,44 Mio dédiés au processus après
  la vue à chaud. C’est un point de mesure de la VRAM.
- Une minuterie Qt précise demandée toutes les 10 ms mesure la
  disponibilité du thread graphique. Le p95 médian jusqu’à la
  première trame à froid est de 17,01 → 17,12 ms. Le plus grand
  intervalle observé atteint 389 → 444 ms. L’ajout de calques,
  les mises à jour Qt et la capture restent synchrones, avec
  les lectures de métadonnées, de contraste et de vues en
  arrière-plan.

## Préchargement, cache et interruption

Le contraste prépare l’affichage à partir de cinq blocs présents
de L5. La première tranche à L4 et les vignettes suivent d’autres
sélections. Précharger une région plus large augmenterait le
trafic à froid. Un essai de vue progressive doit comparer une
première vue L5 suivie d’une relève L4 sur la même position,
avec un budget incluant la vignette et les changements de niveau.

Le cache conserve les objets présents et purge les fichiers de
plus de 30 jours ou au-delà de la limite globale. Les plages de
shards relues dans une session peuvent être gardées en mémoire par
`CacheStore`. Les absences sont vérifiées à chaque lecture. Pour
une nouvelle révision publiée à l’URI existante, vider le cache
depuis le panneau puis rouvrir le volume.

Deux essais ajoutent 350 ms à chaque lecture de store distant et
injectent une `ConnectionError` à la lecture des attributs de groupe.
Le panneau affiche l’erreur et réactive **Ouvrir** en 0,89–0,94 s.
La relance charge une première trame en 7,69–9,03 s avec la
latence injectée. Pendant l’erreur le p95 de la minuterie Qt
est de 19,4–20,9 ms. L’injection précède l’appel S3 et teste le
retour d’erreur et la relance par le bouton. Les délais d’une
vraie coupure à mi-transfert dépendent du SDK et du système.
[Traces de connexion lente et d’interruption](validation/phase3-profile-network.json)

## Critères et reproduction

L’étendue des temps métadonnées optimisés doit descendre sous
l’étendue de référence, avec moins de requêtes et les mêmes
empreintes de voxels. Les trois répétitions satisfont ces critères
à froid et à chaud. La navigation et la première vue ont également
des étendues disjointes dans le sens du gain. Le RSS et les
intervalles Qt servent de diagnostics. Trois ouvertures limitent
les conclusions sur la latence extrême.

```powershell
$env:LOCALAPPDATA = Join-Path $PWD 'data/phase3-qt-appdata'
$env:QT_QPA_PLATFORM = 'windows'
$env:PYTHONIOENCODING = 'utf-8'
git archive --format=zip -o data/phase3-base.zip eba4082
Expand-Archive data/phase3-base.zip data/phase3-base-src
$env:PYTHONPATH = Join-Path $PWD 'data/phase3-base-src/src'
.venv/Scripts/python.exe docs/validation/phase3_profile.py data/phase3-before data/phase3-profile-before.json
$env:PYTHONPATH = Join-Path $PWD 'src'
.venv/Scripts/python.exe docs/validation/phase3_profile.py data/phase3-after data/phase3-profile-after.json
.venv/Scripts/python.exe docs/validation/phase3_profile.py data/phase3-after data/phase3-profile-network.json --delay 0.35 --interrupt --repeats 2
```

`--metadata-only` exécute les ouvertures isolées et trace les sockets.
Pour reproduire la variante intermédiaire, utiliser la même source
en ôtant `max_concurrency` des options S3 dans `open_volume_store`.
Le script requiert `psutil` et le même environnement GUI que
l’application. Il utilise des dossiers de cache temporaires dédiés.
