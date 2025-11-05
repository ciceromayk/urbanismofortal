import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
import plotly.express as px
import requests
from shapely.geometry import Point
from streamlit_folium import st_folium

# --- CONFIGURAÇÕES INICIAIS ---
st.set_page_config(page_title="Zoneamento Fortaleza", layout="wide")

st.title("🏙️ Consulta Interativa – Zoneamento de Fortaleza")
st.markdown("Base construída a partir do arquivo **pdp-macrozoneamento.kmz** (PDP Fortaleza)")

# --- CARREGAR DADOS ---
@st.cache_data
def carregar_dados():
    try:
        df = pd.read_csv("zoneamento_fortaleza.csv")
        gdf = gpd.GeoDataFrame(
            df.drop(columns=['wkt_multipolygon']),
            geometry=gpd.GeoSeries.from_wkt(df['wkt_multipolygon']),
            crs="EPSG:4326"
        )
        return gdf
    except FileNotFoundError:
        st.error("❌ Arquivo 'zoneamento_fortaleza.csv' não encontrado. Coloque-o na mesma pasta do app.")
        return None

gdf = carregar_dados()
if gdf is None:
    st.stop()

# --- BARRA LATERAL ---
st.sidebar.header("Filtros de Consulta")

zona_tipo = st.sidebar.multiselect(
    "Tipo de Zona:",
    sorted(gdf['tipo_zona'].dropna().unique().tolist()),
    default=None
)

ca_min, ca_max = st.sidebar.slider(
    "Coeficiente de Aproveitamento Máximo (CA)",
    float(gdf['indice_aproveitamento_maximo'].min() or 0),
    float(gdf['indice_aproveitamento_maximo'].max() or 5),
    (0.0, 3.0),
    step=0.1
)

base_mapa = st.sidebar.selectbox(
    "Camada Base do Mapa:",
    ["CartoDB positron", "OpenStreetMap", "Stamen Terrain", "Stamen Toner", "Esri Satellite"]
)

modo_localizacao = st.sidebar.radio("Modo de Localização:", ["Buscar por Endereço", "Selecionar no Mapa"])

filtro = gdf.copy()
if zona_tipo:
    filtro = filtro[filtro['tipo_zona'].isin(zona_tipo)]
filtro = filtro[
    (filtro['indice_aproveitamento_maximo'] >= ca_min) &
    (filtro['indice_aproveitamento_maximo'] <= ca_max)
]

st.sidebar.markdown(f"**Zonas encontradas:** {len(filtro)}")

# --- MAPA BASE ---
centro = [-3.730451, -38.521798]
m = folium.Map(location=centro, zoom_start=12, tiles=base_mapa)

# Adiciona camadas base
folium.TileLayer('OpenStreetMap', name='OpenStreetMap', attr='© OpenStreetMap contributors').add_to(m)
folium.TileLayer('CartoDB positron', name='CartoDB positron', attr='© OpenStreetMap contributors & CartoDB').add_to(m)
folium.TileLayer(
    tiles='https://stamen-tiles.a.ssl.fastly.net/terrain/{z}/{x}/{y}.jpg',
    name='Stamen Terrain',
    attr='Map tiles by Stamen Design, CC BY 3.0 — Map data © OpenStreetMap contributors'
).add_to(m)
folium.TileLayer(
    tiles='https://stamen-tiles.a.ssl.fastly.net/toner/{z}/{x}/{y}.png',
    name='Stamen Toner',
    attr='Map tiles by Stamen Design, CC BY 3.0 — Map data © OpenStreetMap contributors'
).add_to(m)
folium.TileLayer(
    tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    name='Esri Satellite',
    attr='Tiles © Esri — Sources: Esri, Maxar, Earthstar Geographics, and the GIS User Community'
).add_to(m)
folium.LayerControl().add_to(m)

# --- ADICIONA POLÍGONOS ---
for _, row in filtro.iterrows():
    if row.geometry is not None:
        foliu
