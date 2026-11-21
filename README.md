# Vesuvius Data Explorer

Explorez les scans 3D des rouleaux d’Herculanum dans **napari**. L’explorateur lit les blocs OME-Zarr à la demande. Vous pouvez parcourir une coupe, superposer une surface VC3D et examiner une anomalie sans télécharger le volume entier. La commande `vesuvius-qc` permet de reproduire les contrôles et d’exporter leurs résultats.

![Dans napari, les points cyan du segment suivent le bord d’une feuille sur une coupe de PHerc0800.](docs/validation/t5-surface-pherc0800.png)

Sur PHerc0800, la ligne de points cyan indique où le segment `20251029010146` traverse la coupe 12 058. En changeant de coupe, on peut suivre le segment à travers les couches du papyrus. [Voir le détail agrandi](docs/validation/t5-surface-pherc0800-zoom.png) · [Validation sur PHerc0800](docs/validation/T5-surfaces.md)

## Ouvrir un premier rouleau

Avec **Python 3.11 ou plus** et Git, créez un environnement virtuel.

```sh
python -m venv .venv
```

Activez-le avec `source .venv/bin/activate` sous Linux ou macOS, ou `.\.venv\Scripts\Activate.ps1` sous Windows PowerShell. Installez le plugin et lancez napari.

```sh
python -m pip install "vesuvius-data-explorer[napari] @ git+https://github.com/AtomCrtr/vesuvius-data-explorer-atom.git"
napari -w vesuvius-data-explorer
```

1. Dans **Vesuvius — Ouvrir un volume**, cliquez sur **Charger le catalogue officiel**, choisissez **PHerc0332** et son volume, puis cliquez sur **Ouvrir**.
2. Parcourez les coupes avec le curseur sous l’image. Le cache local réutilise les blocs déjà lus.
3. Dans **Plugins → Vesuvius — Contrôle qualité**, cliquez sur **Lancer le QC**, puis sélectionnez une anomalie et sa localisation pour centrer la vue sur la zone mesurée.

| Ouvrir une coupe depuis le catalogue | Examiner une alerte sur la coupe |
| --- | --- |
| ![Coupe entière de PHerc0332 avec sa taille de voxel et ses niveaux de résolution à droite.](docs/validation/t6-contraste-pherc0332.png) | ![Le rectangle rouge localise la région mesurée et le tableau à droite affiche le contrôle de saturation.](docs/validation/t4-anomalie-fond.png) |
| Le volume sélectionné a un pas de **2,399 µm**. Le panneau liste les six niveaux de résolution disponibles. [Capture en grand](docs/validation/t6-contraste-pherc0332.png) | Dans cet essai, le calcul inclut le fond noir autour du rouleau. Le cadre montre pourquoi cette région déclenche l’alerte de saturation. [Détail du contrôle](docs/validation/T4-donnees-reelles.md) |

Pour travailler sur un serveur, installez le même paquet en retirant `[napari]`. Les volumes `*.vcd3d.zarr` nécessitent **Python 3.12 ou plus** et l’option `vcdelta3d`, par exemple `[napari,vcdelta3d]` avec l’interface graphique. [Guide d’utilisation et dépannage](docs/guide.md)

## Essayer la ligne de commande

**Contrôler un volume public.** Cette commande échantillonne PHerc0332 et écrit un rapport JSON ainsi qu’une version HTML à ouvrir dans un navigateur.

```sh
vesuvius-qc volume s3://vesuvius-challenge-open-data/PHerc0332/volumes/20251211183505-2.399um-0.2m-78keV-masked.zarr -o rapport.json --html rapport.html
```

Pour contrôler les segments d’un même volume, utilisez `vesuvius-qc lot 20250804134230 -o PHerc0814`. Le dépôt contient la synthèse obtenue sur ses 19 segments. [Résultats de PHerc0814](docs/validation/T7-qc-en-lot.md)

**Comparer deux cartes d’encre hors ligne.** Depuis la racine du dépôt cloné, après installation, générez deux fenêtres synthétiques puis lancez la comparaison dans un nouveau dossier de sortie.

```sh
python docs/examples/generate_ink_example.py data/encre-demo
vesuvius-qc encre data/encre-demo/manifest.toml -o data/encre-rapport
```

L’exemple permet d’examiner les accords et les erreurs des deux cartes sur des pixels dont la référence est connue. Pour des prédictions déjà calculées sur une même surface, napari propose aussi un panneau de comparaison interactif. [Exemple de comparaison synthétique](docs/validation/ink-synthetic/comparaison-001.png) · [Comparer des prédictions dans napari](docs/COMPARAISON_PREDICTIONS.md)

## Se repérer dans le dépôt

| Pour… | Point d’entrée |
| --- | --- |
| Utiliser le plugin ou automatiser un contrôle | [Guide illustré](docs/guide.md) · [Référence CLI et API](docs/reference.md) |
| Retrouver un protocole, un benchmark ou une campagne sur données réelles | [Index de la documentation](docs/README.md) · [Exemples de rapports](docs/examples/README.md) |
| Modifier l’explorateur | [Code Python](src/vesuvius_data_explorer/) · [Extension Rust facultative](rust/) · [Tests](tests/) · [Contribuer](CONTRIBUTING.md) |
| Suivre les travaux en cours | [Feuille de route du projet](docs/ROADMAP.md) · [Prochaines étapes scientifiques](docs/ROADMAP_SCIENTIFIC_NEXT_STEPS.md) |

## Données et licence

Vesuvius Data Explorer est un projet communautaire indépendant du Vesuvius Challenge. Le code est distribué sous licence MIT. Les captures de PHerc0332 et PHerc0800 reproduisent des extraits des scans du Vesuvius Challenge sous CC BY-NC 4.0. Pour réutiliser une autre acquisition, vérifiez sa licence et citez le jeu de données correspondant. [Licence du code](LICENSE) · [Données et attribution](https://scrollprize.org/data) · [Outils officiels de déroulement virtuel](https://github.com/ScrollPrize/villa)
