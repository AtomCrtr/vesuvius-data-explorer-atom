# Phase 2 · Validation sur surfaces publiées et profil de navigation

19 novembre 2026. Windows x64, Intel Core i9-14900HX, 31,6 Gio de RAM, RTX 4080 Laptop, Python 3.11.9, NumPy 2.4.6, Zarr 3.1.6, napari 0.10.0, PyQt6/Qt 6.12.0, Vispy 0.17.0, roue Rust 1.96.0 GNU x64 Release. Les temps locaux dépendent notamment de l’état du cache fichier Windows.

## Corpus réel et parité

Le corpus utilise les grilles publiées du Vesuvius Challenge et les intensités des volumes qui leur sont associés. Les fichiers de travail restent sous `data/`. Le protocole télécharge une seule boîte alignée sur les blocs par cas, bornée à 96 Mio décompressés. Le lecteur de validation garde la forme et les axes ZYX d’origine et échoue si l’algorithme sort de la boîte. Les points de surface conservent leurs coordonnées niveau 0. Les fichiers, les origines de recadrage UV et les bornes ZYX sont repris dans les mesures JSON avec leurs empreintes. Le cache OS et le cache de blocs applicatif sont distincts. [Données publiques et attribution](https://github.com/ScrollPrize/open-data#support-and-citation)

Chaque backend tourne dans un processus neuf pour chaque taille de grille. Un premier appel est suivi de sept répétitions, avec ordre Python/Rust mélangé. Trois opérations sont ventilées. La carte utilise les profils et les règles de fiabilité T10. Le rendu projette la surface réelle aux trois décalages normaux `−1, 0, +1` voxel source. Le parcours rapport appelle `run_map`, le recalage et `write_outputs`, donc ouvre le tifxyz de recadrage, produit les rendus avant/après et écrit TIFF, JSON et HTML. Le lecteur de ce parcours sert les voxels capturés en mémoire mappée. Les performances du réseau et de Zarr sont mesurées à part.

Le contrôle exige des types, dimensions, masques NaN, indices de tuiles, changements de feuille et ensembles de blocs identiques. Les tolérances sont `1e-8` absolu pour les tableaux `float64` et `0,004` unité CT pour le rendu `float32` (borne de la phase 1, conservatrice pour les données `uint8`). La comparaison garde la dispersion maximale et l’erreur quadratique moyenne de chaque champ. Les étiquettes de zone et les décisions près du seuil de fiabilité sont contrôlées. Les grilles de résolution les plus fines peuvent dépasser la boîte autorisée si le recadrage UV est trop large. [Script de parité](../validation/rust_real_bench.py)

| Segment publié | Acquisition → lecture | UV évaluées | CT décodé | Dispersion des normales |
| --- | --- | --- | ---: | ---: |
| PHerc0814 `20260226110425` | 9,362 → 9,362 µm, L0 | 8² et 16² | 96 Mio | 0,248 |
| PHerc0500P2 `20250825181928` | 2,215 → 8,859 µm, L2 | 12² et 24² | 50 Mio | 0,102 |
| PHerc0139 `20260316000000` | 1,129 → 9,030 µm, L3 | 8² et 16² | 68,44 Mio | 0,399 |
| PHerc0500P2 `20250825181928`, sous-région commune au L2 | 2,215 → 4,430 µm, L1 forcé | 6² et 8² | 64 Mio | 0,109 |

La dispersion est la norme des écarts types des trois composantes de la normale unitaire. Le cas PHerc0139 est le plus courbe de ce corpus. Le premier recadrage de ce segment a été écarté, car ses points se trouvaient hors du scan ciblé. Le corpus final représente 278,44 Mio décodés. Tous les blocs validés sont `uint8` et Zarr v2. Les lectures portent sur les seules boîtes définies.

| Région | Tuiles mesurées / fiables | Carte, ms Python → Rust | Rendu, ms Python → Rust | Rapport complet, ms Python → Rust | Pic RSS, Mio Python → Rust |
| --- | ---: | ---: | ---: | ---: | ---: |
| PHerc0814 L0, 8² | 1 / 1 | 3,10 → 1,64 | 3,25 → 1,08 | 16,66 → 13,56 | 98 → 99 |
| PHerc0814 L0, 16² | 4 / 2 | 15,44 → 3,31 | 13,54 → 3,88 | 41,33 → 20,01 | 130 → 127 |
| PHerc0500P2 L2, 12² | 4 / 1 | 9,76 → 2,43 | 108,61 → 27,08 | 116,23 → 52,61 | 130 → 120 |
| PHerc0500P2 L2, 24² | 9 / 5 | 25,41 → 5,18 | 480,61 → 118,55 | 453,75 → 196,15 | 250 → 158 |
| PHerc0139 L3, 8² | 1 / 0 | 3,51 → 1,46 | 53,62 → 12,73 | 50,60 → 28,72 | 113 → 106 |
| PHerc0139 L3, 16² | 4 / 4 | 14,76 → 3,31 | 257,08 → 61,54 | 245,31 → 105,25 | 183 → 139 |
| PHerc0500P2 L1, 6² | 1 / 1 | 3,64 → 1,85 | 91,24 → 23,02 | 79,03 → 44,31 | 127 → 117 |
| PHerc0500P2 L1, 8² | 1 / 0 | 6,45 → 2,29 | 193,16 → 45,95 | 182,82 → 81,16 | 156 → 128 |

Temps médians. Sur le plus grand cas, le p95 du rapport complet passe de 478,62 à 229,22 ms et celui du rendu de 503,63 à 125,82 ms. Le pic RSS est celui du processus, importations et mémoire mappée incluses. La carte s’accélère de 1,90× à 4,90× et le rapport complet de 1,23× à 2,33× dans ces conditions.

Les huit rendus coïncident élément par élément. L’unique écart non nul parmi les champs exportés est de 2,84 × 10⁻¹⁴ unité CT sur les profils du PHerc0139 16². Les tuiles fiables, y compris deux tuiles de PHerc0500P2 L2 à moins de 0,05 du seuil de fiabilité 3, gardent les mêmes décisions. Les grilles recalées de ce corpus coïncident également. [Provenance, échantillons et écarts par champ](../validation/rust-real-windows.json)

## Application napari jusqu’à la trame OpenGL

Chaque ROI CT originale devient le niveau fin d’une pyramide locale bornée. Un second niveau est décimé pour exercer le code multiscalaire. La surface publiée est translatée dans le repère de la ROI et le pas physique de la lecture est fourni au widget. Le test pilote les widgets de production, ouvre le volume, demande 13 coupes, charge le tifxyz et calcule cinq fois la carte de dérive. Il attend le résultat asynchrone puis force une capture du canvas OpenGL via le backend natif Windows. Les captures RGB non uniformes proviennent de la RTX 4080. Les chiffres incluent le rendu et la copie GPU vers le framebuffer lu par le test. Ils ne mesurent pas la présentation par le compositeur ni le taux d’images par seconde.

| ROI | Navigation médiane, ms Python → Rust | Navigation p95, ms | Dérive à la trame, médiane, ms | Dérive p95, ms | Worker de dérive, médiane, ms | Pic RSS, Mio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| PHerc0814 L0 | 21,32 → 20,46 | 23,57 → 26,12 | 222,04 → 204,50 | 241,23 → 240,72 | 55,22 → 38,52 | 394 → 395 |
| PHerc0500P2 L2 | 16,65 → 15,19 | 23,56 → 16,69 | 247,58 → 230,05 | 275,15 → 255,09 | 75,05 → 54,72 | 407 → 407 |
| PHerc0139 L3 | 18,63 → 18,39 | 19,97 → 20,45 | 227,09 → 210,63 | 258,78 → 254,05 | 54,53 → 37,37 | 403 → 402 |
| PHerc0500P2 L1 | 18,54 → 16,67 | 24,57 → 26,25 | 229,46 → 221,51 | 269,97 → 255,81 | 73,41 → 49,57 | 408 → 408 |

Le délai médian de dérive jusqu’à la trame baisse de 3,5 % à 7,9 %. Le worker baisse de 27 % à 32 % et les libellés de tuiles et de zones concordent. Les lectures Dask des blocs couvrent à elles seules 38 à 60 ms du worker Python en médiane, en comptant une seule fois les intervalles qui se chevauchent. La capture finale prend environ 44 à 46 ms, et la création des calques et l’attente de la boucle Qt restent dans le délai jusqu’à la trame. Les coupes seules ne font pas appel au noyau Rust. Leurs écarts donnent un ordre de grandeur de la variation de la mesure locale. La mesure du p95 de dérive n’utilise que cinq répétitions par cas. Le pic RSS app inclut Python, Qt, Dask et les buffers CPU. Il est stable sur ces parcours. La VRAM dédiée par processus n’a pas été relevée. [Ouverture, coupe initiale, ventilation Dask, compteurs, navigation et rendu](../validation/napari-real-windows.json)

## Navigation OME-Zarr et cache

Trajet sur PHerc0800 `20250521135224` via le store S3 anonyme, niveau 0. Dix demandes axiales, sagittales et coronales de 48² ou 128² pixels, chacune avec un à quatre blocs de 128³ voxels `uint8` non compressés. Le chronométrage mesure `read_slice`, puis `normalized_preview` séparément. Les compteurs de blocs et d’octets encadrent le cache de production. Les intervalles source concurrents sont comptés par union, ce qui évite de les additionner comme s’ils étaient séquentiels. [Mesures et profil bruts](../validation/zarr-navigation-windows.json)

| État du store | Ouverture avec métadonnées | Médiane coupe | p95 coupe | Blocs S3 | Trafic blocs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Direct | 2 780 ms | 658 ms | 923 ms | 28 | 56 Mio |
| Cache vide au départ | 2 004 ms | 150 ms | 393 ms | 7 | 14 Mio |
| Nouveau store, cache disque rempli | 1 651 ms | 2,34 ms | 9,81 ms | 0 | 0 Mio |

Les 28 demandes de blocs donnent les mêmes sommes de voxels et de prévisualisations dans les trois états. Le cache rempli sert les 28 demandes depuis le disque. À froid, les premières demandes nouvelles prennent environ 287 à 415 ms avec cache, puis les répétitions de ces clés retombent à environ 2 à 13 ms dans la même session. Le profil à chaud attribue 14 ms sur 21 ms à l’attente synchrone du lecteur pendant dix demandes et 3 ms à la normalisation. Le bloc de ce volume étant brut, ces chiffres couvrent le transfert et la sélection des voxels sans coût de décompression. Les latences au disque restent mêlées au cache de l’OS.

À la réouverture avec cache chaud, neuf demandes de métadonnées amont renvoient zéro octet, avec 1 628 ms d’union. La prochaine expérience devra identifier chaque clé absente et mesurer une mise en cache négative à TTL court pour les métadonnées optionnelles ou tester des métadonnées consolidées lorsqu’elles sont publiées. Cette mesure ne justifie pas un nouveau lecteur Rust. Sur cette trajectoire répétitive, précharger plus de voxels avant de servir la coupe risquerait de consommer du débit pour un cache déjà efficace. Un essai séparé peut tester les changements de direction et d’échelle. Une campagne Zarr v3 avec shards `vc-delta3d` reste nécessaire pour généraliser. [Codec du Vesuvius Challenge](https://github.com/ScrollPrize/vc-delta3d)

## Diagnostic Qt/OpenGL

Dans un processus qui importe seulement napari et crée `napari.Viewer(show=False)`, `QT_QPA_PLATFORM=offscreen` produit `GL_INVALID_OPERATION` (1282) sur `GL_MAX_TEXTURE_SIZE`, avant tout chargement d’un widget Vesuvius. Avec `QT_QPA_PLATFORM=windows`, le même test réussit et rapporte des textures maximales 2D et 3D de 32 768 et 16 384. Les 46 tests des widgets existants passent sur le backend natif. La suite finale avec l’extension activée donne 304 réussites, un test ignoré pour le codec optionnel et huit tests réseau désélectionnés par la configuration pytest. L’échec intermittent du contrôle de destruction du fixture napari, vu en phase 1 lors d’un test isolé, n’a pas bloqué cette suite complète. Aucune correction de production Qt/OpenGL n’a été nécessaire pour ces résultats. [Installation Windows et Qt](https://napari.org/dev/getting_started/installation.html) · [Diagnostic napari](https://napari.org/dev/troubleshooting.html)

Pour reproduire sur Windows avec le profil de test isolé du compte utilisateur, depuis la racine dans PowerShell.

```powershell
$env:LOCALAPPDATA = Join-Path $PWD 'data/rust2-qt-appdata'
$env:QT_QPA_PLATFORM = 'windows'
$env:PYTHONIOENCODING = 'utf-8'
.venv/Scripts/python.exe -m pytest -q --basetemp data/rust2-tests
```

## Reproduction des mesures

Construire et installer la roue Release, installer `psutil` et les dépendances napari, puis exécuter les commandes ci-dessous. Conserver `QT_QPA_PLATFORM=windows` pour la mesure Qt. Le test de navigation manipule un cache temporaire dédié. Les empreintes et les temps bruts permettent une comparaison sur une autre machine. [Installation Rust](RUST_ARCHITECTURE.md)

```text
python docs/validation/rust_real_bench.py data/rust2 --prepare
python docs/validation/rust_real_bench.py data/rust2 --repeats 7 --output data/rust-real.json
python docs/validation/napari_real_bench.py data/rust2 --repeats 5 --output data/napari-real.json
python docs/validation/zarr_navigation_bench.py data/rust2 data/zarr-navigation.json
```

## Comparaison Reader

Le panneau napari affiche un CT projeté, une surface déroulée et des prédictions dans un même repère UV déclaré. Le seuil et le modèle sélectionnés modifient les couches affichées. Les tests portent sur les métadonnées et les contrôles affine UV, les plages de scores, la visibilité et la conservation des TIFF. Les essais du panneau utilisent des scores de test contrôlés. Les futurs essais Reader sur des segments réels demandent des cartes effectivement produites sur la même pile orientée. L’inférence reste en Python/PyTorch/CUDA. [Manifeste et mode d’emploi](../COMPARAISON_PREDICTIONS.md)
