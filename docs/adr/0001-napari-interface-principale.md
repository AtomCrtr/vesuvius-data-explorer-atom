# ADR 0001 — napari comme interface principale d'exploration et de contrôle qualité

- **Statut :** Accepté
- **Date :** 2026-11-17
- **Décideurs :** Product Owner (validation), orchestrateur (proposition)

## Contexte

Le prototype v0.1 utilise Streamlit pour lire des ROI 2D (≤ 512 × 512) dans des volumes OME-Zarr
et calculer des diagnostics simples sur des grilles de surface TIFXYZ.

L'objectif produit est désormais double :

1. **Exploration** : naviguer dans des volumes CT réels du Vesuvius Challenge (multi-échelles,
   plusieurs To), superposer volume et surfaces.
2. **Contrôle qualité (QC)** : mesurer, localiser et annoter des anomalies (données manquantes,
   saturation, grilles de surface incohérentes), de façon reproductible.

Limites de Streamlit pour ces objectifs : ré-exécution complète du script à chaque interaction,
pas de navigation fluide multi-résolution, pas de rendu volumique GPU, gestion d'état fragile pour
l'annotation et les vues synchronisées.

## Décision

1. **napari** (application de bureau Python) devient l'interface principale, distribuée comme
   **plugin napari** installable par `pip`.
2. Le **QC est indépendant de l'interface** : un moteur QC en Python pur, exposé par une CLI
   (`vesuvius-qc`) produisant un rapport JSON (puis HTML). napari sert à investiguer ce que le
   rapport signale.
3. Le **cœur** (lecture de données, métriques) ne dépend d'aucune interface graphique.
4. **Streamlit est gelé** : l'app existante reste comme démo légère, sans nouveau développement,
   jusqu'à ce que le plugin napari couvre ses fonctions ; elle sera alors supprimée.

### Règles d'architecture

```
src/vesuvius_data_explorer/
  core/      # données et métriques — n'importe ni napari, ni Qt, ni streamlit, ni matplotlib
  qc/        # contrôles qualité → rapport sérialisable (dépend de core/ uniquement)
  napari/    # plugin : calques + widgets (dépend de core/ et qc/)
  cli.py     # point d'entrée en ligne de commande (dépend de core/ et qc/)
```

- Les dépendances graphiques (`napari`, `streamlit`, `matplotlib`) sont des **extras optionnels**.
  `pip install vesuvius-data-explorer` sans extra doit suffire pour le cœur, le QC et la CLI.
- Toute lecture de données reste **bornée et paresseuse** : jamais de chargement complet d'un volume.
- Convention d'axes : **(z, y, x)** partout.

## Alternatives considérées

| Option | Raison du rejet |
|---|---|
| Continuer Streamlit | Inadapté à la navigation fluide et à l'annotation (voir Contexte). |
| Neuroglancer + tableau de bord Panel | Excellent visualiseur web, mais deux outils à intégrer, QC personnalisé et annotation plus coûteux. Reste une **piste complémentaire** (lien « ouvrir dans Neuroglancer »), pas l'interface principale. |
| Application web sur mesure (FastAPI + React + vtk.js) | Coût de développement disproportionné pour l'équipe. |

## Conséquences

- **Positives :** réutilisation du code existant de `src/`, navigation multi-résolution 2D fluide,
  rendu 3D GPU, calques superposables, annotations, QC reproductible en CLI/CI.
- **Négatives / acceptées :**
  - application de bureau : installation locale, pas de partage par lien ;
  - en 3D, rendu d'une ROI ou d'un niveau réduit, pas du rouleau entier en pleine résolution ;
  - la CI doit tester le plugin sans affichage (tests de widgets en mode headless ou limités au
    code non graphique).
- **À réévaluer si :** un besoin fort de partage web apparaît (alors : Neuroglancer + rapports HTML).
