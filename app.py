"""Vesuvius Data Explorer — local-first Streamlit interface."""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import streamlit as st

from vesuvius_data_explorer.demo import demo_surface, demo_volume
from vesuvius_data_explorer.surface import load_surface_patch, surface_metrics
from vesuvius_data_explorer.volume import (
    get_array,
    list_levels,
    normalized_preview,
    open_volume_store,
    read_slice,
    slice_stats,
)

st.set_page_config(page_title="Vesuvius Data Explorer", page_icon="📜", layout="wide")
st.title("📜 Vesuvius Data Explorer")
st.caption("Données micro-CT · fenêtres bornées · géométrie des surfaces · exploration reproductible")
st.info(
    "Projet indépendant et non affilié au Vesuvius Challenge. "
    "La démonstration utilise uniquement des données **synthétiques**. "
    "Aucune identification d'encre ni lecture de texte antique n'est réalisée."
)


@st.cache_resource(show_spinner=False)
def cached_store(path: str):
    return open_volume_store(path)


@st.cache_resource(show_spinner=False)
def cached_demo():
    return demo_volume()


def plot_image(array: np.ndarray, title: str):
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.imshow(normalized_preview(array), cmap="gray", interpolation="nearest")
    ax.set(title=title, xlabel="Colonne dans la fenêtre", ylabel="Ligne dans la fenêtre")
    fig.tight_layout()
    st.pyplot(fig, clear_figure=True)
    plt.close(fig)


tab_volume, tab_surface, tab_about = st.tabs(["🔬 Volumes", "📐 Surfaces TIFXYZ", "📚 Sources"])
with tab_volume:
    source = st.radio("Source des volumes", ["Démonstration synthétique", "OME-Zarr local / S3"], horizontal=True)
    if source == "Démonstration synthétique":
        volume = cached_demo()
        level_label = "synthetic / zyx"
    else:
        st.markdown(
            "Ouvrir un chemin **complet** vers un dossier `.zarr`, par exemple "
            "`s3://vesuvius-challenge-open-data/PHerc.../volumes/<scan>.zarr`. "
            "Rechercher le vrai chemin dans [Data Browser](https://scrollprize.org/data_browser). "
            "Le chemin ci-dessus est un *modèle*, pas un scan existant."
        )
        path = st.text_input("Dossier Zarr local ou URI S3 publique", placeholder="s3://.../nom-du-volume.zarr")
        if not path:
            st.stop()
        try:
            with st.spinner("Lecture des métadonnées…"):
                root = cached_store(path)
                levels = list_levels(root)
            labels = [f"{lev.key} · {lev.shape} · {lev.dtype}" for lev in levels]
            selected = st.selectbox("Niveau multirésolution", range(len(levels)), index=len(levels)-1, format_func=lambda i: labels[i])
            volume = get_array(root, levels[selected].key)
            level_label = levels[selected].key
        except Exception as exc:
            st.error(f"Impossible d'ouvrir ce volume : {exc}")
            st.stop()

    shape = tuple(int(n) for n in volume.shape)
    st.caption(f"Niveau : `{level_label}` · Forme Z/Y/X : `{shape}` · dtype : `{volume.dtype}`")
    axis = st.selectbox("Orientation", ["z", "y", "x"], format_func=lambda s: {"z":"Axiale (Z)", "y":"Coronale (Y)", "x":"Sagittale (X)"}[s])
    fixed_size, row_size, col_size = {"z": (shape[0], shape[1], shape[2]), "y": (shape[1], shape[0], shape[2]), "x": (shape[2], shape[0], shape[1])}[axis]
    index = st.slider("Indice de la coupe", 0, fixed_size - 1, (fixed_size - 1) // 2)
    width = st.select_slider("Largeur maximale de la fenêtre (pixels)", options=[64, 128, 256, 512], value=256)
    left, right = st.columns(2)
    with left:
        start_a = st.number_input("Début ligne", min_value=0, max_value=row_size - 1, value=max(0, (row_size-width)//2))
    with right:
        start_b = st.number_input("Début colonne", min_value=0, max_value=col_size - 1, value=max(0, (col_size-width)//2))
    try:
        with st.spinner("Lecture de la fenêtre sélectionnée…"):
            cut = read_slice(volume, axis, index, int(start_a), int(start_b), int(width))
        plot_image(cut, f"Coupe {axis}={index} · ROI {cut.shape}")
        stats = slice_stats(cut)
        cols = st.columns(4)
        for col, (name, value) in zip(cols, stats.items()):
            col.metric(name, f"{value:.2f}")
        st.caption("Mesures descriptives d'image uniquement ; elles n'établissent pas la qualité scientifique de la segmentation.")
    except Exception as exc:
        st.error(f"Lecture impossible : {exc}")

with tab_surface:
    st.markdown("Analyse exploratoire de petites grilles de coordonnées x/y/z. **Ce n'est pas une validation topologique complète.**")
    surface_mode = st.radio("Source de surface", ["Surface synthétique", "Dossier TIFXYZ/NPY local"], horizontal=True)
    try:
        if surface_mode == "Surface synthétique":
            xx, yy, zz = demo_surface()
            st.caption("Grille synthétique contenant volontairement des points manquants.")
        else:
            folder = st.text_input("Chemin local du dossier contenant x, y, z (.npy ou .tif)", value="")
            if not folder:
                st.stop()
            xx, yy, zz = load_surface_patch(Path(folder), limit=256)
        metrics = surface_metrics(xx, yy, zz)
        cols = st.columns(4)
        names = {"valid_pct":"Points valides (%)", "median_step":"Pas médian", "p95_step":"Pas p95", "normal_flip_pct":"Normales inversées (%)"}
        for col, (key, value) in zip(cols, metrics.items()):
            col.metric(names[key], f"{value:.2f}" if np.isfinite(value) else "N/A")
        st.image(np.uint8(np.isfinite(zz) * 255), caption="Masque des coordonnées valides (blanc = valide)", clamp=True)
        st.caption("Le taux de normales inversées dépend de la courbure, de l'orientation et de l'échantillonnage ; ne pas l'assimiler directement à des erreurs de segmentation.")
    except Exception as exc:
        st.error(f"Analyse impossible : {exc}")

with tab_about:
    st.markdown(
        """### Données et attribution
- [Vesuvius Challenge — formats, sources et licences](https://scrollprize.org/data)
- [Catalogue des scans et artefacts](https://scrollprize.org/data_browser)
- [Documentation du bucket S3 public](https://github.com/ScrollPrize/open-data)
- [Code scientifique Vesuvius / villa](https://github.com/ScrollPrize/villa)

**Provenance** : pour chaque capture/export, consigner le sample ID, l'ID du scan, le chemin Zarr, le niveau, les coordonnées de la fenêtre, et les conditions de licence. Les données externes ne sont pas redistribuées ici. L'accès public n'implique pas une licence libre pour tous les usages ; voir CC BY-NC 4.0 et les conditions propres aux jeux de données.

### Limites
Ce prototype explore des coupes et fournit des diagnostics descriptifs. Il ne déroule pas un rouleau, ne reconnaît pas l'encre, et ne fournit pas de résultats de recherche validés. Les analyses TIFXYZ acceptent uniquement de petits extraits lisibles localement. Les chemins S3 doivent pointer vers un objet `.zarr` existant (ne pas utiliser de chemin d'exemple littéral).
"""
    )
