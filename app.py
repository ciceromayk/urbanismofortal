import sys
import os
import streamlit as st

# --- GARANTE QUE O DIRETÓRIO RAIZ ESTÁ NO PYTHONPATH ---
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

# --- IMPORTAÇÕES LOCAIS (SEM PREFIXO src.) ---
from typing import Tuple, Dict
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

# ------------- CONFIG -------------
st.set_page_config(page_title="KMZ/KML Viewer", layout="wide")
st.title("🗺️ LEITOR KMZ/KML – MAPA INTERATIVO")

with st.sidebar:
    st.header("⚙️ CONTROLES")
    st.markdown(
        "1) FAÇA UPLOAD DE **.KMZ** OU **.KML**\n"
        "2) ESCOLHA O MOTOR DE MAPA\n"
        "3) OPCIONAL: SIMPLIFIQUE GEOMETRIAS\n"
        "4) EXPLORE ATRIBUTOS E BAIXE OS DADOS"
    )

    map_lib = st.radio("BIBLIOTECA DE MAPA", ["folium", "pydeck"], horizontal=True)
    show_popups = st.checkbox("MOSTRAR POPUPS (NOME/DESCRIÇÃO/ATRIBUTOS)", value=True)
    show_tooltips = st.checkbox("MOSTRAR TOOLTIP (NOME)", value=True)

    st.subheader("🎨 ESTILO POR TIPO")
    pt_color = st.color_picker("COR – PONTOS", "#1f77b4")
    ln_color = st.color_picker("COR – LINHAS", "#ff7f0e")
    pg_color = st.color_picker("COR – POLÍGONOS", "#2ca02c")
    opacity = st.slider("OPACIDADE (0-1)", 0.0, 1.0, 0.6, 0.05)
    weight = st.slider("ESPESSURA (LINHAS/BORDAS)", 1, 8, 3)

    st.subheader("🧩 SIMPLIFICAÇÃO (OPCIONAL)")
    simplify_tol = st.slider("TOLERÂNCIA (GRAUS) – 0 DESATIVA", 0.0, 0.01, 0.0, 0.0005)

    st.subheader("🧭 CRS")
    force_crs = st.text_input("FORÇAR CRS DE ENTRADA (EX: EPSG:4326)", value="")
    target_crs = st.text_input("REPROJETAR PARA (EX: EPSG:4326)", value="EPSG:4326")

    st.subheader("📁 UPLOAD")
    file = st.file_uploader(
        "ARQUIVO KMZ/KML", type=["kmz", "kml"], accept_multiple_files=False
    )
    st.caption("DICA: ARRASTE E SOLTE O ARQUIVO AQUI.")

# ------------- PLACEHOLDER E EXEMPLOS -------------
with st.expander("📖 INSTRUÇÕES RÁPIDAS"):
    st.markdown(
        "- ACEITA **KMZ** (DESCOMPACTADO EM MEMÓRIA) E **KML**\n"
        "- SUPORTA **PASTAS/CAMADAS** E **PLACEMARKS** (PONTOS/LINHAS/POLÍGONOS)\n"
        "- PRESERVA **NOME/descrição/ExtendedData** COMO ATRIBUTOS\n"
        "- MAPA **FOLIUM** (DEFAULT) OU **PYDECK** (WEBGL)\n"
        "- TABELA FILTRÁVEL E **DOWNLOAD** EM **GEOJSON/CSV**\n"
        "- PARA ARQUIVOS GRANDES, USE **SIMPLIFICAÇÃO**"
    )

# ------------- CACHE DO PARSING -------------
@st.cache_data(show_spinner=True)
def _cached_parse(file_bytes: bytes, filename: str) -> Tuple[gpd.GeoDataFrame, Dict[str, gpd.GeoDataFrame]]:
    return parse_kmz_or_kml(file_bytes, filename)

# ------------- LÓGICA PRINCIPAL -------------
if file is None:
    st.info("CARREGUE UM ARQUIVO **.KMZ** OU **.KML** NA BARRA LATERAL.")
    st.stop()

try:
    raw = file.read()
    gdf_all, layers = _cached_parse(raw, file.name)

    # CRS
    inferred_crs = detect_crs_or_default(gdf_all, force_crs.strip() or None)
    gdf_all.set_crs(inferred_crs, allow_override=True, inplace=True)
    if target_crs.strip():
        gdf_all = reproject_if_needed(gdf_all, target_crs.strip())

    # SIMPLIFICAÇÃO
    if simplify_tol > 0:
        gdf_all = simplify_geometries(gdf_all, simplify_tol)

    # DIVISÃO POR GEOMETRIA
    gdfs = split_by_geom_type(gdf_all)

    # --- CONTROLE DE CAMADAS (FOLDERS/KML) ---
    all_layers = sorted(list(gdf_all["__layer__"].dropna().unique())) if "__layer__" in gdf_all.columns else []
    selected_layers = st.multiselect(
        "SELECIONE CAMADAS/FOLDERS PARA EXIBIR", all_layers, default=all_layers
    )
    if selected_layers:
        gdf_all = gdf_all[gdf_all["__layer__"].isin(selected_layers)] if "__layer__" in gdf_all.columns else gdf_all
        gdfs = split_by_geom_type(gdf_all)

    # --- MAPA ---
    st.subheader("🗺️ MAPA")
    style = {"point_color": pt_color, "line_color": ln_color, "poly_color": pg_color, "opacity": float(opacity), "weight": int(weight)}

    if map_lib == "folium":
        fmap = build_folium_map(gdfs, style, show_popups=show_popups, show_tooltips=show_tooltips)
        from streamlit_folium import st_folium
        st_folium(fmap, width=None, height=650)
    else:
        deck = build_pydeck_map(gdfs, style, show_popups=show_popups, show_tooltips=show_tooltips)
        import pydeck as pdk
        st.pydeck_chart(deck, use_container_width=True)

    # --- TABELA / ATRIBUTOS ---
    st.subheader("🧾 ATRIBUTOS")
    if len(gdf_all) == 0:
        st.warning("SEM FEATURES PARA EXIBIR APÓS OS FILTROS.")
    else:
        df = pd.DataFrame(gdf_all.drop(columns="geometry"))
        st.dataframe(df, use_container_width=True)

        # --- DOWNLOADS ---
        col1, col2 = st.columns(2)
        with col1:
            gj_bytes = to_geojson_bytes(gdf_all)
            st.download_button(
                "⬇️ BAIXAR GEOJSON", data=gj_bytes, file_name="data.geojson", mime="application/geo+json"
            )
        with col2:
            csv_bytes = gdf_to_csv_bytes(gdf_all)
            st.download_button(
                "⬇️ BAIXAR CSV (ATRIBUTOS)", data=csv_bytes, file_name="attributes.csv", mime="text/csv"
            )

except Exception as e:
    st.error(
        "❌ ERRO AO PROCESSAR O ARQUIVO.\n\n"
        f"DETALHES: {type(e).__name__}: {e}\n\n"
        "DICAS:\n"
        "- VERIFIQUE SE O KMZ POSSUI PELO MENOS UM KML INTERNO.\n"
        "- VERIFIQUE SE O KML NÃO ESTÁ VAZIO OU CORROMPIDO.\n"
        "- TENTE DESATIVAR A SIMPLIFICAÇÃO (TOLERÂNCIA = 0)."
    )
