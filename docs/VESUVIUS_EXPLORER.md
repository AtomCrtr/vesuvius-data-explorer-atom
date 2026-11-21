# Vesuvius Explorer

Le plugin napari existant sert d’interface desktop au premier moteur Rust. Il donne accès au catalogue, aux volumes CT, aux segments et au contrôle qualité dans la même session. La carte de dérive appelle le nouveau noyau lorsqu’il est activé et que le volume sélectionné fournit des blocs entiers compatibles. [Décision napari](adr/0001-napari-interface-principale.md) · [Contrat et installation](ingenierie/RUST_ARCHITECTURE.md)

## Parcours local

1. Activer l’environnement Python du projet. Pour essayer le noyau natif, installer la roue Release et définir `VESUVIUS_RUST_SAMPLER=1` avant de lancer `napari` ou `vesuvius-qc`.
2. Ouvrir **Vesuvius — Ouvrir un volume** dans le menu Plugins. Choisir un rouleau et un scan dans le catalogue ou ouvrir un chemin local. Les niveaux sont paresseux. Découper la zone et tourner les axes avant de charger un affichage 3D fin.
3. Dans **Vesuvius — Surfaces**, choisir la couche du volume, ajouter la grille tifxyz et cliquer sur **Cartographier la dérive**. Inspecter les tuiles, naviguer vers les zones signalées et comparer avec les coupes CT.
4. Pour exporter les rendus aplatis, les TIFF de la carte et le rapport HTML, lancer `vesuvius-qc carte CHEMIN_SEGMENT --volume CHEMIN_VOLUME -o data/carte-essai`. Le dossier de sortie peut être différent à chaque essai. [Guide détaillé](guide.md) · [CLI et paramètres](reference.md)

## Fonctions et étapes suivantes

| Fonction | Disponible et prolongement |
| --- | --- |
| Explorateur de données | Le catalogue indique rouleaux, volumes, identifiants, taille des voxels et segments. Étendre les filtres à l’état des prédictions et observations lorsqu’un index persistant devient utile. |
| Viewer CT | Navigation par coupes Z/Y/X, zoom et défilement dans napari, affichage 3D à échelle adaptée, ROI bornées dans QC. Ajouter trois vues synchronisées et une ROI 3D exportable en coordonnées physiques. |
| Surfaces | Calques de grille et trace, carte de dérive, rapports et projection 2D. Pour le traçage, le maillage et les piles orientées, utiliser les outils VC3D. |
| Encre et comparaison | **Comparer les prédictions** superpose une carte Reader au CT projeté ou à la surface déroulée dans le même repère UV et règle la transparence par seuil. Le manifeste conserve la provenance et permet de basculer entre prédictions. `vesuvius-qc encre` évalue des TIFF existants. [Guide du manifeste et du panneau](COMPARAISON_PREDICTIONS.md) |
| Annotations | Les calques Points et Shapes de napari permettent un marquage manuel. Le format scientifique à livrer doit stocker caractère ou hypothèse, incertitude, auteur, révision du segment, coordonnées UV, position ZYX lorsque connue et identifiants de prédiction. Prévoir JSON et CSV, et distinguer les annotations de la vérité terrain. |
| Performances | Le rapport CLI et le benchmark permettent de consulter des mesures locales. Le panneau à construire devra afficher temps jusqu’à la première coupe, p95 en navigation, lectures/décodage/calcul/rendu, cache, CPU, RAM et VRAM par tâche sur les plateformes qui l’exposent. [Mesures](RUST_BENCHMARKS.md) |

Tauri 2 est une option pour une distribution desktop dédiée. Son intégration Windows demande notamment MSVC et WebView2, et il faut choisir un visualiseur 3D et développer la synchronisation du viewport. Napari couvre déjà le navigateur local et les calques. Neuroglancer constitue un candidat pour la navigation volumétrique partageable. VC3D couvre les opérations de segmentation et de rendu scientifique. Mesurer le délai entre la demande de coupe et son affichage, le cache et la RAM avant de décider si le coût d’une interface supplémentaire est justifié. [Napari](https://github.com/napari/napari) · [Neuroglancer](https://github.com/google/neuroglancer) · [VC3D](https://github.com/ScrollPrize/villa/tree/main/volume-cartographer) · [Prérequis Tauri](https://v2.tauri.app/start/prerequisites/)
