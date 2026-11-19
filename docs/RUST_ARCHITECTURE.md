# Architecture du moteur Vesuvius Explorer

Le premier module natif accélère l’interpolation sur blocs déjà décodés. `sample_trilinear` reste le point d’entrée de `flatten` et de `alignment_map`. Le paquet Python principal et sa distribution PyPI conservent leur installation habituelle. L’extension facultative est une roue distincte.

## Contrat du noyau

- Les coordonnées sont `(N, 3)` en ZYX, au niveau déjà résolu par l’appelant. Les conversions niveau 0/centre voxel et l’orientation des normales restent chez l’appelant.
- Les blocs `uint8` et `uint16` d’endianness native sont échantillonnés dans un lot de 65 536 points au plus. Le Rust groupe les huit voisins par bloc, avec un chemin pour les points intérieurs et une liste de contributions pour les franchissements de blocs. Python charge les clés via `DecodedChunks`. Les bornes sont saturées au bord du volume.
- Rust emprunte les vues NumPy stridées des coordonnées et des blocs. La sortie `float64` est allouée une fois et complétée dans des vues de la même allocation. `np.asarray` peut convertir les coordonnées non `float64`. `np.require` copie une vue exceptionnellement non alignée. Le plan, son index et les listes de contributions sont des allocations temporaires. L’extension conserve le GIL lors des emprunts et Python peut l’utiliser entre les appels par bloc. Le pilote n’ajoute ni Rayon ni parallélisme imbriqué.
- `VESUVIUS_RUST_SAMPLER=1` active le moteur lorsqu’il est disponible. Retirer la variable ou fixer `0` revient à la version Python. Un import impossible produit un avertissement et revient à Python. Les autres dtypes et les lots comportant des coordonnées non finies suivent aussi le chemin Python. Une erreur de lecture demeure visible. Sur une surface qui dépasse la capacité du cache, un lot peut relire un bloc évincé par un lot précédent. Mesurer cet effet sur les grands segments avant de généraliser l’activation.

## Module A · Lecture volumétrique

Garder `open_levels` et Dask/fsspec/Zarr pour l’instant. Ils connaissent les métadonnées, alignent le niveau de lecture, limitent la fenêtre et servent S3 et HTTPS. Si un profil par étage justifie un autre lecteur, commencer avec une ROI locale sur des OME-Zarr v2 sans compression et en Blosc/Zstd, puis vérifier le séparateur `/`, les chunks partiels, les fills, l’ordre des octets et les échelles. Tester ensuite les shards v3 avec une fixture `vc-delta3d` et le codec C++ ou son adaptateur Rust. Comparer chaque voxel avant d’activer un fallback pour les métadonnées ou codecs non pris en charge. [zarrs et couverture v2/v3](https://docs.rs/zarrs/latest/zarrs/) · [VC-Delta3D](https://github.com/ScrollPrize/vc-delta3d)

| Bibliothèque | Usage envisagé et condition |
| --- | --- |
| `ndarray` | Utilisé via `rust-numpy`. Des vues évitent une conversion de volume et respectent les strides. [ndarray](https://github.com/rust-ndarray/ndarray) |
| `rayon` | Tester sur des lots de buffers dont Rust possède la mémoire, après avoir séparé la concurrence des tuiles et du codec. [Rayon](https://github.com/rayon-rs/rayon) |
| `tokio` | Envisager pour une future source Rust. Définir priorité des lectures à l’écran, annulation, budget total du cache et du préchargement voisin. [Tokio](https://github.com/tokio-rs/tokio) |
| `memmap2` | Évaluer pour un fichier local contigu immuable. Les TIFF compressés, shards et clés distantes exigent encore un décodage ou un accès au store. [memmap2](https://github.com/RazrFalcon/memmap2-rs) |
| `tiff` | Construire une matrice de fixtures avant adoption, incluant strips et tuiles, float32 LZW et prédicteur flottant, ordre des octets, BigTIFF si présent, piles CT et alpha de masques si applicable. [image-tiff](https://github.com/image-rs/image-tiff) |

## Modules B à D

- **Géométrie.** VC3D reste le comparateur pour traçage, maillage et rendu d’une pile orientée. HerculeX fournit une approche différente de détection de feuilles, de résolution des tours et d’assemblage. Sur le même segment/ROI, comparer axes, face, pas physique, profondeur, trous, coutures et sauts de feuille. Le pilote local échantillonne une surface donnée. Les sorties VC3D et HerculeX n’ont pas été comparées expérimentalement ici. [VC3D](https://github.com/ScrollPrize/villa/tree/main/volume-cartographer) · [HerculeX](https://github.com/adambetka2/HerculeX)
- **Encre.** Piloter Reader V3 et les autres modèles via Python/PyTorch. Une tâche reçoit une pile de surface, un identifiant de modèle, le hash des poids, son environnement et un dossier de destination. Elle produit des cartes immuables et un manifeste d’orientation, de normalisation et de seuils. Tester le batching, la VRAM et l’écriture des overlays. Envisager Rust pour un post-traitement CPU lorsque sa parité et son gain sont établis. Utiliser NumPy pour des cartes CPU groupées. Évaluer DLPack si un noyau GPU natif devient pertinent, en traitant explicitement les streams, la durée de vie et la propriété du buffer. [PyO3](https://pyo3.rs/v0.26.0/) · [Rust-NumPy](https://github.com/PyO3/rust-numpy) · [Reader V3](https://github.com/DomRusso2/reader-v3)
- **Index.** Le catalogue local JSON couvre déjà les volumes et segments. Ajouter SQLite lorsque les observations et prédictions exigent des requêtes croisées. Clés stables proposées, basées sur `sample_id`, `volume_id`, `level`, `segment_id`, révision de la surface, provenance du modèle et `run_id`. Conserver les fichiers lourds dans leur format d’origine. Écrire les nouvelles références en transaction, privilégier un seul écrivain, versionner le schéma et enregistrer l’URI, le hash, la licence et les coordonnées de chaque produit.

## Compilation et contrôle

Windows x64 avec Rust MSVC et Visual Studio Build Tools C++, ou WSL2 avec Python et un compilateur Linux dans la distribution. Activer l’environnement Python du projet. La roue doit être construite dans l’OS et avec l’interpréteur qui la chargera. WSL2 est surtout pertinent pour les outils géométriques ou GPU disponibles en Linux. [Rust sur Windows](https://rust-lang.github.io/rustup/installation/windows.html) · [Maturin](https://www.maturin.rs/)

```text
python -m pip install maturin==1.10.2
python rust/build_release.py
cargo test --release --locked --manifest-path rust/Cargo.toml
cargo fmt --manifest-path rust/Cargo.toml --check
cargo clippy --locked --manifest-path rust/Cargo.toml --all-targets -- -D warnings
```

Installer la roue générée dans `rust/target/wheels/`, puis lancer `python -m pytest -q tests/test_rust_sampler.py`. En PowerShell, activer avec `$env:VESUVIUS_RUST_SAMPLER = '1'`. Sous WSL2, utiliser `export VESUVIUS_RUST_SAMPLER=1`.

La mesure de ce lot a utilisé Rust 1.96.0 GNU x64 pour Windows, installé dans `data/rust-dev` avec Cargo et rustup isolés. Elle a utilisé `RUSTFLAGS='-C linker=rust-lld -C linker-flavor=ld.lld'`. Les commandes MSVC et WSL2 sont proposées pour l’installation et restent à vérifier sur ces cibles. Le lockfile Rust fixe les dépendances. Le code ajouté est MIT. Maturin, PyO3 et `ndarray` sont MIT/Apache-2.0. La crate `numpy` 0.26.0 est BSD-2-Clause. VC3D/villa, HerculeX et Reader V3 publient le code sous MIT. Les scans issus d’Open Data suivent CC BY-NC 4.0 et leur protocole de citation. Vérifier séparément les licences de chaque jeu d’annotations, checkpoint et modèle avant redistribution. [Code et licence du projet](../LICENSE) · [Données et citation](https://github.com/ScrollPrize/open-data#support-and-citation) · [Licence villa](https://github.com/ScrollPrize/villa/blob/main/LICENSE) · [Licence HerculeX](https://github.com/adambetka2/HerculeX/blob/main/LICENSE) · [Licence Reader V3](https://github.com/DomRusso2/reader-v3/blob/main/LICENSE)
