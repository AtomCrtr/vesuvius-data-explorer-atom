# Passation à Claude Opus

## Décision après la phase 2

Conserver Rust en option sur les blocs CT entiers. Sur huit recadrages réels de PHerc0814, PHerc0500P2 et PHerc0139, les rendus et les coordonnées recalées coïncident. L’écart maximal est de 2,84 × 10⁻¹⁴ unité CT sur un profil. La carte gagne jusqu’à 4,90× et le chemin de rapport complet jusqu’à 2,33×. Sur le plus grand essai de rapport, le RSS passe de 250 à 158 Mio. Ces résultats couvrent Zarr v2 `uint8` et des niveaux de lecture 0 à 3. [Rapport et reproductibilité](RUST_PHASE2.md)

Les essais S3 attribuent l’essentiel du coût à froid au store. Le cache disque ramène 28 lectures réseau à sept au premier passage et à zéro pour les données lors d’une nouvelle ouverture. La médiane de lecture à chaud est de 2,34 ms. Ne pas prioriser un port du lecteur Rust. Au prochain profil, identifier les neuf réponses de métadonnées à zéro octet encore émises à la réouverture et évaluer un TTL court pour les seules clés optionnelles, avec contrôle des métadonnées mises à jour. Pour le chemin de dérive napari, comparer les accès Dask actuels à des lectures Zarr groupées hors du thread graphique et mesurer le délai jusqu’à la trame. [Trace S3](validation/zarr-navigation-windows.json) · [Trace napari](validation/napari-real-windows.json)

Dans napari, les gains sur le worker de dérive se traduisent par une baisse de 3,5 à 7,9 % de la médiane jusqu’à la trame. La suite complète sous Qt `windows` compte 304 réussites. Un `napari.Viewer` seul reproduit l’échec de `GL_MAX_TEXTURE_SIZE` sous `offscreen`. Garder le test Windows natif et la CI Linux configurée avec Xvfb. Le panneau **Comparer les prédictions** lit des cartes déjà produites, avec origine UV, pas physique, provenance et seuil d’affichage. Conserver les runs Reader/PyTorch/CUDA en Python et exporter les plans sur la même grille avant de les comparer. [Manifeste de comparaison](COMPARAISON_PREDICTIONS.md)

## État du premier lot

- Branche locale `feat/rust-explorer-first-kernel`, base `426e712`. L’extension facultative et les mesures se relisent indépendamment des travaux locaux d’évaluation d’encre.
- Le chemin de projection `core/chunkcache.py` utilise le noyau `rust/src/lib.rs` sur activation. La CLI `vesuvius-qc carte` et l’interface napari **Surfaces** partagent le point d’entrée. La version Python est le choix par défaut.
- Windows GNU x64, Release, grand rendu Zarr local médian 307,30 ms en Python, 175,07 ms avec le témoin SciPy optimisé, 128,34 ms en Rust. Sur le bloc PHerc0800 réencodé localement, 51,87 / 33,22 / 27,23 ms. Les géométries de ces mesures sont synthétiques.
- Les tests vérifient les sorties Python/Rust, y compris une carte synthétique multithread, et le script de benchmark vérifie la parité des tableaux. Sur Windows, l’essai napari a ouvert un Zarr local, superposé un tifxyz et affiché la carte de dérive avec Rust. La suite graphique complète reste à reproduire. Une matrice CI Linux/Windows valide la construction et l’import de la roue sur les prochains runs. [Profil et mesures](RUST_BENCHMARKS.md)

## Suite à orchestrer

1. Étendre le corpus à un vrai `uint16` et à un Zarr v3 shardé `vc-delta3d`, puis vérifier les mêmes champs et les décisions au seuil. Pour les très grands segments, relever les relectures et évictions causées par les lots plus grands que le cache et figer un budget avant l’essai.
2. Tester les métadonnées et les alternatives Dask/Zarr sur une trajectoire avec plusieurs résolutions et changements de direction. Mesurer les octets réseau et les temps jusqu’à la trame avant d’évaluer un préchargement borné.
3. Faire un essai VC3D/HerculeX sur la même coupe et examiner face, coutures et trous. Pour l’encre, produire une pile orientée une fois, exécuter Reader V3 et un modèle indépendant sur les mêmes pixels avec batch et VRAM enregistrés, puis préserver cartes brutes et contrôles. Alimenter le panneau UV avec ce lot, puis évaluer une présentation côte à côte et les annotations exportables.
4. Vérifier une roue Windows MSVC et une roue Linux/WSL2. Passer le même corpus et la même version NumPy. Geler les critères de gain du parcours complet avant de changer le réglage par défaut.

Les exigences d’axes, de provenance, de compatibilité des codecs et de licence sont documentées avec la feuille de route. [Audit](RUST_AUDIT.md) · [Architecture](RUST_ARCHITECTURE.md) · [Interface](VESUVIUS_EXPLORER.md)
