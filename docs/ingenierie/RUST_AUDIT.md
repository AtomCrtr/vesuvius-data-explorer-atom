# Audit Rust de Vesuvius Explorer

19 novembre 2026 · `AtomCrtr/vesuvius-data-explorer-atom` · base `426e712`.

L’arborescence contient un paquet Python, un plugin napari, une CLI QC, des tests, des scripts de validation et des rapports. Aucun notebook, modèle entraîné ou pipeline PyTorch n’est livré dans le dépôt. Les travaux locaux d’évaluation d’encre ont aussi été examinés. Ils comparent des cartes préexistantes avec des labels, sans lancer d’inférence. [Feuille de route](../ROADMAP.md) · [Validation T10](../validation/T10-carte-alignement.md)

| Classe | Périmètre et code | État et décision |
| --- | --- | --- |
| A · Python/CUDA | Inférence et entraînement Reader V3 ou modèles locaux, segmentation de surfaces | Prendre les poids et recettes en amont, avec Python et PyTorch/CUDA. Importer les prédictions avec leurs coordonnées et leur provenance. Le dépôt ne produit actuellement aucun checkpoint. |
| A · Python/CUDA | `core/flatten.py`, `core/alignment.py`, `core/alignment_map.py` | NumPy et SciPy assurent les normales, l’interpolation dense, les profils et la géométrie de recalage. Conserver la convention ZYX et les algorithmes validés. |
| B · Rust | `core/chunkcache.py` · interpolation sur blocs décodés | Premier port. Le profil CPU montre le coût des huit passages NumPy, qui calculent et regroupent les voisins par bloc. Mesurer sur l’interpolation, le rendu complet et la carte. |
| B · à mesurer | Gestion des blocs, voisinage et génération de patches géométriques | Tester le regroupement de lectures, les volumes épars et l’assemblage de stencils. Réutiliser VC3D pour le traçage, les conversions de meshes et la génération de piles orientées. |
| C · Python | `core/catalog.py`, `core/volume.py`, `core/cache.py` | Catalogue distant avec copie locale, OME-Zarr multi-échelle local/HTTPS/S3, ROI bornée, cache disque Zarr et concurrence des lectures. Priorité aux requêtes inutiles, au partage du cache et aux statistiques de hit/miss. |
| C · Python | `core/tifxyz.py`, `core/surface.py` | Trois grilles `x.tif`, `y.tif`, `z.tif`, métadonnées et sentinelle, décimation bornée par lecture partielle des strips, fallback Pillow pour LZW avec prédicteur flottant. Le format historique accepte aussi les grilles NPY. Aucun lecteur de piles TIFF CT génériques dans le chemin d’exploration. |
| C · Python | `qc/engine.py`, `qc/checks`, `qc/batch.py`, `qc/carte.py`, `cli.py` | Analyse de coupes et de surfaces, localisation, rapports sérialisés, cartes de dérive et rendu de contrôle. Ventiler l’ouverture, l’échantillonnage et l’export avant de modifier le QC. |
| C · Python | `napari/reader.py`, `widget.py`, `surface_widget.py`, `qc_widget.py` | Chargement paresseux Dask, tâches hors thread graphique, inspection 2D/3D et calques. La latence image visible implique aussi Vispy/OpenGL. |
| C · Python | Évaluation d’encre locale et annotations | Le travail `qc/ink.py` mesure des pixels, composantes et glyphes sur des TIFF inscrits dans un manifeste. Le projet offre des points et overlays natifs napari. Un registre de lectures grecques avec export scientifique reste à concevoir. |

## Profils et entrées/sorties

- **Réseau.** Sur PHerc0800, T6 mesurait 3,24 s à la première vue, 0,67 s avec le cache disque déjà rempli, et 0,20 s pour la coupe suivante après remplissage. Une vue de niveau 0 pouvait demander 64 blocs de 2 Mio. Cette comparaison historique inclut préparation et rendu. [Campagne T6](../validation/T6-performance.md)
- **CPU.** Le premier profil local à ouvertures répétées a attribué 0,545 s des 0,659 s cumulés de `flatten` à `sample_trilinear` sur trois rendus synthétiques. La source instrumentée était une vue NumPy. Son accès total a pris moins de 0,2 ms pour 440 lectures, échauffement compris. Les générateurs de grille et le rendu SciPy contribuaient au reste. [Mesures et méthode](../RUST_BENCHMARKS.md)
- **Disque et codecs.** Le census historique contient 74 entrées, dont 66 lectures réussies d’OME-NGFF 0.4 en Zarr v2, 65 sans compression et une en Blosc/Zstd. Il ne couvre pas toutes les données récentes. Les volumes Zarr v3 avec shards et `vc-delta3d` ont un chemin Python dédié, qui dépend de l’extra codec à partir de Python 3.12. Mesurer requêtes, octets encodés, décompression et encodage d’export séparément. [Census](../investigations/I1-volumes-census.json) · [Codec en amont](https://github.com/ScrollPrize/vc-delta3d)
- **RAM.** Le cache disque T6 est distinct du LRU des blocs décodés utilisé pour une carte ou un rendu. Ce dernier a un plafond nominal de 1 Gio et garde au minimum un bloc. Les plans de tuiles, blocs en vol, calques et tableaux NumPy s’y ajoutent. Sur T10, une carte pouvait lire de 1 à 7 Gi-voxels, dont la majorité pouvait être évincée avant le rendu. [Validation T10](../validation/T10-carte-alignement.md)
- **GPU et VRAM.** RTX 4080 Laptop détectée avec 12 282 Mio. L’environnement testé ne contient pas PyTorch. Le profil Rust porte sur le CPU. En inférence, instrumenter transfert hôte/appareil, CUDA synchronisé, pic alloué et réservé, débit de patches et précision numérique. Mesurer séparément le rendu Vispy. [Recette officielle d’inférence](https://scrollprize.org/tutorial5)
- **Sérialisation et pont.** Le cœur passe des tableaux en mémoire aux bibliothèques natives. Les rapports JSON/HTML/PNG constituent une phase distincte. Le pont Rust emprunte des vues NumPy par lot et par bloc. La durée du pont est incluse dans les performances. [Contrat et copies](RUST_ARCHITECTURE.md)

## Évaluation de `rust-anything`

Le projet est sous MIT. Son flux porte une unité à la fois. Ses binaires Windows sont publiés via GitHub Releases, et son intégration Windows documentée et testée en CI cible MSVC. Le README donne aussi une installation CLI isolable. `setup` enregistre un serveur MCP et une compétence, avec des changements dans les réglages de l’agent. [README et licence](https://github.com/erkamyaman/rust-anything) · [Installation Windows](https://github.com/erkamyaman/rust-anything/blob/main/docs/install.md)

| Commande | Utilité et limite pour Vesuvius |
| --- | --- |
| `profile` | Automatise `cProfile` et repère les appels chauds. Une mesure séparée reste nécessaire pour le réseau, la décompression asynchrone, la mémoire native et le GPU. |
| `analyze` | Propose un ordre de portage et des dépendances. Les liens entre métadonnées NGFF, codecs privés, coordonnées physiques et règles de validation exigent une revue manuelle. |
| `bridge` | Génère les interfaces et les stubs. Pour `DecodedChunks`, les tableaux NumPy stridés et les vues modifiées en place, le pont doit définir dimension, dtype, ordre d’axes, endianness, alignement et ownership. |
| `record` | Capture des cas et des erreurs, permet des entrées personnalisées et une tolérance flottante. Dans ce dépôt, un cas utile inclut masque attendu, tableaux typés, coordonnées physiques et clés consultées. |
| `diff` | Rejoue le corpus. Il faut contrôler exactement les dimensions, dtypes et indices, comparer les flottants avec un seuil en unités CT et vérifier les classes scientifiques après l’interpolation. Les valeurs qui fluctuent entre exécutions peuvent être traitées comme jokers par l’outil. Pour le GPU, répéter les runs sous une graine et mesurer la dispersion. |
| `bench` | Mesure le coût du pont sur le corpus. Le Vesuvius Explorer exige aussi les conditions de cache, la décompression, les distributions de latence et la mémoire par processus. |
| `gate` | Enchaîne formatage, lints, tests, audit d’`unsafe` et parité capturée. La validation scientifique inclut les ROI réelles, les versions de volume et de modèle, le protocole réseau et les seuils de décision. |

La méthode de migration a été reprise avec `cProfile`, PyO3/NumPy, tests sur sorties de référence, mesures Release et activation explicite. Une installation de `rust-anything` n’apportait pas de validation supplémentaire à ce noyau dépendant d’un cache Python et de vues NumPy, donc le pilote n’en dépend pas. Un futur essai isolé a du sens pour une fonction à entrée et sortie scalaires ou JSON. [Fonctionnement et limites amont](https://github.com/erkamyaman/rust-anything/blob/main/docs/how-it-works.md)
