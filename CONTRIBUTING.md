# Contribuer à Vesuvius Data Explorer

Vous pouvez ouvrir une issue ou une pull request en français ou en anglais. Une contribution utile peut être aussi simple qu’une coupe sur laquelle la superposition d’un segment semble décalée. Indiquez comment la retrouver pour que quelqu’un d’autre puisse examiner la même feuille. [Ouvrir une issue](https://github.com/AtomCrtr/vesuvius-data-explorer-atom/issues/new) · [Guide de l’explorateur](docs/guide.md)

**English-speaking contributors are welcome.** For a scan or alignment issue, include the public volume and segment IDs, the resolution level, the slice or region, and what you expected to see. For a code change, open a pull request against `main` with the command and test result that reproduce it. [English alignment walkthrough](docs/en/alignment-map.md)

## Reproduire un problème

- **Interface ou CLI** — précisez le commit ou le tag, le système, la version de Python et la commande ou les actions dans napari. Décrivez le résultat attendu et celui observé.
- **Volume ou surface** — donnez l’identifiant de l’acquisition, le niveau de résolution et la coupe Z ou les coordonnées de la région. Pour un défaut d’alignement, ajoutez l’identifiant du segment et, si sa diffusion est permise, une capture annotée.
- **Performance** — comparez la même région et le même résultat avant et après. Indiquez le matériel, le moteur Python ou Rust, l’état du cache et le temps du parcours complet.

## Développer et tester

Depuis votre fork cloné, activez un environnement virtuel Python 3.11 ou plus. Pour installer le cœur et lancer ses contrôles locaux :

```sh
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
```

Pour modifier l’interface, installez `python -m pip install -e ".[dev,napari]" pytest-qt` et lancez `python -m pytest -q tests/gui`. Les tests réseau sont facultatifs et se lancent avec `python -m pytest -q -m network`. Les instructions Rust décrivent la construction de la roue et les tests de parité des voxels. [Architecture Rust](docs/ingenierie/RUST_ARCHITECTURE.md) · [Organisation du code](docs/README.md)

Dans la pull request, expliquez le problème résolu, les étapes de vérification et le résultat obtenu. Ajoutez un test pour une nouvelle logique, ou pour le cas qui reproduit un bug. Une capture avant/après aide à relire un changement de géométrie ou d’interface.

## Partager les données et les résultats

Le code original proposé au dépôt est distribué sous la licence MIT du projet. Pour tout contenu tiers, indiquez l’auteur, la source, la licence et les transformations effectuées. Gardez les volumes CT, poids de modèles, données restreintes et identifiants d’accès hors de Git. Une URI publique, une petite fixture synthétique ou un manifeste avec empreinte SHA-256 permet de reproduire la plupart des cas. [Licence du code](LICENSE) · [Exemples synthétiques](docs/examples/README.md) · [Attribution des données Vesuvius et EduceLab](https://scrollprize.org/data#how-to-cite)

Pour une expérience ML, identifiez les données d’entraînement et d’évaluation, le checkpoint, le protocole et les limites connues. Précisez si les annotations sont manuelles ou issues d’un modèle et si le résultat est exploratoire. [Exemple d’évaluation sur trois fragments](docs/PHASE13_INK_GENERALIZATION.md)

## Participation au concours

Ce dépôt public permet à la communauté de tester l’outil et de reproduire ses résultats. Pour proposer le travail à un prix, utilisez le formulaire de la catégorie visée. Les organisateurs des **Progress Prizes** privilégient notamment l’usage réel et les améliorations documentées sur les données du concours. Pour une découverte relevant d’un prix avec embargo, suivez les consignes de cette catégorie avant de la décrire dans une issue publique. [Critères et formulaires officiels](https://scrollprize.org/prizes)
