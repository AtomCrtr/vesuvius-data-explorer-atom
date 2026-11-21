# Publier une version (PyPI et napari hub)

La publication passe par le **« trusted publishing » de PyPI** : GitHub prouve à PyPI qu'il s'agit
bien du workflow de ce dépôt. **Aucun mot de passe ni jeton n'est stocké** dans le dépôt.

## Une seule fois (le PO, environ 10 minutes)

1. **Compte PyPI.** Créer un compte sur [pypi.org](https://pypi.org/account/register/) et activer la
   double authentification (obligatoire pour publier).
2. **Éditeur de confiance en attente.** Sur PyPI : menu du compte → **Publishing** → **Add a new
   pending publisher** → onglet GitHub, puis saisir :
   - PyPI Project Name : `vesuvius-data-explorer` (nom libre au 18 novembre 2026) ;
   - Owner : `AtomCrtr` ;
   - Repository name : `vesuvius-data-explorer-atom` ;
   - Workflow name : `publish.yml` ;
   - Environment name : `pypi`.
3. **Environnement GitHub.** Sur GitHub : dépôt → **Settings** → **Environments** → **New
   environment** → `pypi`. Recommandé : **Required reviewers** avec votre compte, pour approuver
   chaque publication d'un clic.

## À chaque version

1. Vérifier que `version` dans `pyproject.toml` (et `__version__` dans
   `src/vesuvius_data_explorer/__init__.py`) est la nouvelle version, par exemple `0.2.0`.
2. Dans **Releases → Draft a new release**, sélectionner le tag existant de la version
   (par exemple `v0.2.0`) ou le créer sur le commit validé de `main`. Vérifier le commit cible,
   renseigner le titre et les notes, puis choisir **Publish release** lorsque le paquet est prêt pour PyPI.
3. Le workflow **Publish** construit le paquet, vérifie que le tag correspond à la version, puis
   publie sur PyPI (après votre approbation si l'environnement l'exige).
4. Vérifier sur `https://pypi.org/project/vesuvius-data-explorer/`, puis dans un environnement neuf :
   `pip install "vesuvius-data-explorer[napari]"`.

## napari hub

[napari hub](https://napari-hub.org) référence automatiquement les paquets PyPI qui déclarent le
classifieur `Framework :: napari` (c'est le cas), en général sous un jour. La page utilise
`.napari-hub/DESCRIPTION.md` et `.napari-hub/config.yml`. Adresse attendue :
`https://napari-hub.org/plugins/vesuvius-data-explorer`.

## Après la première publication

Remplacer, dans le README et le guide, l'installation depuis GitHub par :

```bash
pip install "vesuvius-data-explorer[napari]"
```
