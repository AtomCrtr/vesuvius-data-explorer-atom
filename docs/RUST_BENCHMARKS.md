# Benchmarks du noyau Rust

Les validations sur segments publiés, les mesures napari et le profil S3 sont dans le [rapport de phase 2](ingenierie/RUST_PHASE2.md).

19 novembre 2026 · Windows x64, Intel Core i9-14900HX (24 cœurs, 32 threads, 31,6 Gio de RAM), RTX 4080 Laptop (12 282 Mio, pilote 616.64). Python 3.11.9, NumPy 2.4.6, SciPy 1.17.1, Zarr 3.1.6, Rust GNU 1.96.0, Maturin 1.10.2, roue Release. Les comparaisons ci-dessous incluent le coût du pont Python–Rust. [Mesures brutes](validation/rust-bench-windows.json) · [Script](validation/rust_bench.py)

Chaque variante dispose d’un processus neuf, d’un premier appel et de 15 répétitions chronométrées. L’ordre des variantes est mélangé à graine fixe par taille. Pour le rendu 2D, le cache de blocs décodés est recréé à chaque rendu. Pour les points épars, il est conservé pendant les répétitions. La première opération intervient après ouverture de la source, et l’extension est déjà importée. Le cache disque de l’OS n’a pas été purgé. Les trois colonnes d’exécution correspondent au Python actuel, à un témoin optimisé NumPy/SciPy qui groupe les points intérieurs puis appelle l’interpolation C et conserve Python aux frontières, et à l’extension Rust.

## Rendu 2D complet

Médiane en millisecondes. Les grilles sont synthétiques et projetées selon trois décalages normaux. Le cas PHerc0800 utilise des intensités réelles et une **grille synthétique**, avec le bloc réencodé en Blosc/Zstd pour la variante Zarr locale.

| Entrée ZYX | Source | Python | NumPy/SciPy | Rust | Gain Rust vs Python | Gain Rust vs SciPy |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 48 × 101 × 117, `uint8` | RAM | 20,15 | 9,91 | 6,29 | 3,20× | 1,58× |
| 48 × 101 × 117, `uint8` | Zarr local | 31,05 | 20,58 | 16,61 | 1,87× | 1,24× |
| 96 × 301 × 333, `uint16` | RAM | 235,43 | 93,20 | 65,75 | 3,58× | 1,42× |
| 96 × 301 × 333, `uint16` | Zarr local | 307,30 | 175,07 | 128,34 | 2,39× | 1,36× |
| PHerc0800, 128³, `uint8` | RAM | 30,25 | 16,35 | 11,99 | 2,52× | 1,36× |
| PHerc0800, 128³, `uint8` | Zarr local | 51,87 | 33,22 | 27,23 | 1,91× | 1,22× |

Pour le grand Zarr local, moyennes de 313,32 / 179,69 / 129,35 ms, p95 de 348,96 / 208,33 / 136,77 ms et débits de 0,91 / 1,59 / 2,21 millions d’échantillons par seconde. Les pics RSS du processus entier étaient de 157,2 / 135,4 / 122,0 Mio. Les temps médians passés dans la source étaient de 64,64 / 68,11 / 61,90 ms. Cette mesure de source inclut le store, le décodage et l’assemblage Zarr. Elle distingue ces appels du calcul de projection, sans attribuer leur durée au seul disque.

Sur le petit Zarr local, la première opération Rust a pris 231,32 ms, dont 221,94 ms dans la source, contre 32,43 ms pour la référence. Le premier rendu SciPy du grand Zarr a aussi subi un pic source (1 236,65 ms sur 1 343,62 ms). Ces observations isolées ne donnent pas de conclusion sur la latence à froid du moteur. [Temps d’ouverture, premiers appels, CPU, RSS et distributions](validation/rust-bench-windows.json)

## Contrôles d’étage

| Cas | Résultats médians | Portée |
| --- | --- | --- |
| Interpolation sur points épars, décodage déjà en cache | 1,45 / 0,47 / 0,053 ms en petit, 8,73 / 1,30 / 0,42 ms en grand, 2,08 / 1,00 / 0,10 ms sur le bloc PHerc0800 | Référence, SciPy, Rust. Projection et géométrie locale sur coordonnées éparses, sans tracé de mesh. |
| Lecture d’un fichier bloc brut | 0,072 ms (32 Kio) en petit, 0,038 ms (64 Kio) en grand | Lecture avec OS chaud, sans décodage. |
| Décompression d’un bloc en RAM | 0,003 ms sur le grand bloc synthétique de 64 Kio, 0,025 ms sur le bloc de 32 Kio issu de PHerc0800 | Blosc/Zstd et shuffle. Les blocs aléatoires compressent peu. |
| Extraction d’une ROI 32³ | 1,89 ms en petit, 2,43 ms en grand, 2,16 ms sur PHerc0800 | Lecture Zarr locale, conversion en tableau, sans moteur Rust. |
| Coupe et normalisation de prévisualisation | 4,13 ms dans le petit Zarr local et 27,22 ms dans le grand, dont 3,85 et 25,44 ms dans Zarr | Coût de préparation d’une image. La latence Qt jusqu’à l’affichage relève du benchmark T6. |
| Seuil et composantes connexes de scores synthétiques | 0,043 ms (101 × 117) et 0,300 ms (301 × 333) | Contrôle SciPy CPU de post-traitement. Les métriques complètes et l’inférence restent à mesurer avec des prédictions réelles. |

Le pont n’effectue aucune copie par voxel. Les vues alignées `uint8`/`uint16` des blocs et `float64` des coordonnées passent sans copie et la sortie est écrite directement. Les copies potentielles de conversion vers `float64` et d’alignement, les allocations temporaires et le pic RSS sont documentés séparément. La durée de `normalized_preview` inclut les conversions de son propre chemin. Aucun temps GPU, transfert hôte→GPU ni pic VRAM d’inférence n’a été mesuré. [Contrat des buffers](ingenierie/RUST_ARCHITECTURE.md)

## Parité et décision

Pour les points, comparer les `float64` avec `rtol=0`, `atol=1e-8` en unités CT. Pour les rendus `float32` `uint16`, `atol=0,004` couvre un ULP près de 65 535. Les tests de rendu sur un petit Zarr codant les axes utilisent `atol=1e-4`. La dimension, le dtype, les masques NaN, les indices et les valeurs aux coordonnées entières sont contrôlés exactement. Les tests couvrent axes ZYX, bords saturés, chunks partiels, axe singleton, vues stridées et contributions aux huit blocs. Le benchmark a enregistré un écart maximal de `0` pour Rust sur ses neuf comparaisons. Le témoin SciPy atteint `2,19e-11` au maximum. [Tests Python/Rust](../tests/test_rust_sampler.py)

Activation à la demande. Avant généralisation, comparer la carte de dérive et le rendu sur plusieurs véritables tifxyz, vérifier les zones et les décisions près des seuils, et mesurer le côté écran avec des requêtes de navigation. Aucun gain de navigation S3 ni de qualité de lecture grecque ne découle de ces seuls essais. [Protocole T10](validation/T10-carte-alignement.md)

## Reproduction

Construire et installer la roue Release, puis installer `psutil` dans l’environnement de développement si nécessaire. Le script exécute tout le protocole synthétique en local.

```text
python docs/validation/rust_bench.py --profile --repeats 15 --output data/rust-bench.json
```

Pour reproduire le bloc réel, télécharger **uniquement** la clé listée ci-dessous, vérifier un fichier de 2 097 152 octets et le SHA-256, puis le convertir avec `np.fromfile(path, dtype=np.uint8).reshape(128, 128, 128)` et `np.save`. Relancer avec `--crop chemin.npy --source 'PHerc0800 20250521135224 niveau 0 bloc 94/48/26'`. Aucun volume complet ni poids de modèle n’est nécessaire. [Bloc brut](https://vesuvius-challenge-open-data.s3.amazonaws.com/PHerc0800/volumes/20250521135224-8.640um-1.2m-116keV-masked.zarr/0/94/48/26) · [Licence et attribution](https://github.com/ScrollPrize/open-data#support-and-citation)

```text
ZYX [12032:12160, 6144:6272, 3328:3456]
SHA-256 210f1f0c101db009af117bcb12a0ed63689e819425acb5a6f8b1428170d89a6f
```
