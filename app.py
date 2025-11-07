# ============================================================
# 🗺️ APP STREAMLIT – LEITOR KMZ/KML INTERATIVO
# ============================================================

from typing import Tuple, Dict
import sys
import os
import io
import json

import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon, MultiPolygon, MultiLineString, MultiPoint
import streamlit as st

# ============================================================
# AJUSTE DE PATH – GARANTE QUE /src É RECONHECIDO
# ============================================================
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

# ============================================================
# IMPORTAÇÕES INTERNAS
# ============================================================
from parsing import parse_kmz_or_kml
from mapping import build_folium_map, build_pydeck_map
from utils import (
    to_geojson_bytes,
    gdf_to_csv_bytes,
    detect_crs_or_default,
    reproject_if_needed,
    simplify_geometries,
    split_by_geom_type,
)

# ============================================================
# CONFIGURAÇÕES GERAIS DO STREAMLIT
# ============================================================
st.set_page_config(page_title="Leitor KMZ/KML", layout="wide")
st.title("🗺️ LEITOR INTERATIVO DE ARQUIVOS KMZ/KML")

with st.sidebar:
    st.header("⚙️ CONTROLES")
    st.markdown(
        "1️⃣ Faça upload de **.KMZ** ou **.KML**\n"
        "2️⃣ Selecione biblioteca de mapa\n"
        "3️⃣ (Opcional) Ajuste simplificação e estilo"
    )

    map_lib = st.radio("Biblioteca de mapa", ["folium", "pydeck"], horizontal=True)
    show_popups = st.checkbox("Mostrar popups (atributos)", value=True)
    show_tooltips = st.checkbox("Mostrar tooltips (nomes)", value=True)

    st.subheader("🎨 Estilo")
    pt_color = st.color_picker("Cor - Pontos", "#1f77b4")
    ln_color = st.color_picker("Cor - Linhas", "#ff7f0e")
    pg_color = st.color_picker("Cor - Polígonos", "#2ca02c")
    opacity = st.slider("Opacidade (0-1)", 0.0, 1.0, 0.6, 0.05)
    weight = st.slider("Espessura (linhas/bordas)", 1, 8, 3)

    st.subheader("🧩 Simplificação")
    simplify_tol = st.slider("Tolerância (graus) – 0 desativa", 0.0, 0.01, 0.0, 0.0005)

    st.subheader("🧭 CRS")
    force_crs = st.text_input("Forçar CRS de entrada", value="")
    target_crs = st.text_input("Reprojetar para", value="EPSG:4326")

    st.subheader("📁 Upload do arquivo")
    file = st.file_uploader("Selecione o arquivo KMZ/KML", type=["kmz", "kml"])

# ============================================================
# FUNÇÃO CACHEADA PARA PARSEAR KMZ/KML
# ============================================================
@st.cache_data(show_spinner=True)
def _cached_parse(file_bytes, filename):
    """Lê e converte o arquivo KMZ/KML em GeoDataFrame (com cache)."""
    return parse_kmz_or_kml(file_bytes, filename)

# ============================================================
# EXECUÇÃO PRINCIPAL
# ============================================================
if not file:
    st.info("💡 Faça upload de um arquivo KMZ ou KML para começar.")
    st.stop()

try:
    raw = file.read()
    gdf_all, layers = _cached_parse(raw, file.name)

    # Define CRS
    inferred_crs = detect_crs_or_default(gdf_all, force_crs.strip() or None)
    gdf_all.set_crs(inferred_crs, allow_override=True, inplace=True)
    if target_crs.strip():
        gdf_all = reproject_if_needed(gdf_all, target_crs.strip())

    # Simplificação opcional
    if simplify_tol > 0:
        gdf_all = simplify_geometries(gdf_all, simplify_tol)

    # Divide por tipo geométrico
    gdfs = split_by_geom_type(gdf_all)

    # Seleção de camadas (folders)
    if "__layer__" in gdf_all.columns:
        all_layers = sorted(list(gdf_all["__layer__"].dropna().unique()))
    else:
        all_layers = []

    if all_layers:
        selected_layers = st.multiselect(
            "Selecionar camadas/folders",
            all_layers,
            default=all_layers,
        )
        gdf_all = gdf_all[gdf_all["__layer__"].isin(selected_layers)]
        gdfs = split_by_geom_type(gdf_all)

    # ============================================================
    # MAPA INTERATIVO
    # ============================================================
    st.subheader("🌎 Visualização no mapa")
    style = {
        "point_color": pt_color,
        "line_color": ln_color,
        "poly_color": pg_color,
        "opacity": float(opacity),
        "weight": int(weight),
    }

    if map_lib == "folium":
        from streamlit_folium import st_folium
        fmap = build_folium_map(gdfs, style, show_popups, show_tooltips)
        st_folium(fmap, width=None, height=650)
    else:
        import pydeck as pdk
        deck = build_pydeck_map(gdfs, style, show_popups, show_tooltips)
        st.pydeck_chart(deck, use_container_width=True)

    # ============================================================
    # TABELA DE ATRIBUTOS + DOWNLOAD
    # ============================================================
    st.subheader("🧾 Tabela de atributos")
    if len(gdf_all) == 0:
        st.warning("Nenhuma geometria encontrada.")
    else:
        df = pd.DataFrame(gdf_all.drop(columns="geometry"))
        st.dataframe(df, use_container_width=True)

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "⬇️ Baixar GeoJSON",
                data=to_geojson_bytes(gdf_all),
                file_name="dados.geojson",
                mime="application/geo+json",
            )
        with col2:
            st.download_button(
                "⬇️ Baixar CSV (atributos)",
                data=gdf_to_csv_bytes(gdf_all),
                file_name="atributos.csv",
                mime="text/csv",
            )

except Exception as e:
    st.error(
        f"❌ Erro ao processar o arquivo.\n\n"
        f"Tipo: {type(e).__name__}\n"
        f"Detalhes: {e}\n\n"
        "Verifique se o arquivo KMZ contém ao menos um KML interno válido."
    )
