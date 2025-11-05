import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
from shapely.geometry import Point
from streamlit_folium import st_folium

# --- CONFIGURAÇÕES INICIAIS ---
st.set_page_config(page_title="Zoneamento Fortaleza", layout="wide")

st.title("🏙️ Consulta Interativa – Zoneamento de Fortaleza")
st.markdown("Base construída a partir do arquivo **pdp-macrozoneamento.kmz** (PDP Fortaleza)")

# --- CARREGAR DADOS ---
@st.cache_data
def carregar_dados():
    df = pd.read_csv("zoneamento_fortaleza.csv")
    gdf = gpd.GeoDataFrame(
        df.drop(columns=['wkt_multipolygon']),
        geometry=gpd.GeoSeries.from_wkt(df['wkt_multipolygon']),
        crs="EPSG:4326"
    )
    return gdf

gdf = carregar_dados()

# --- BARRA LATERAL DE FILTROS ---
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

filtro = gdf.copy()
if zona_tipo:
    filtro = filtro[filtro['tipo_zona'].isin(zona_tipo)]
filtro = filtro[(filtro['indice_aproveitamento_maximo'] >= ca_min) & (filtro['indice_aproveitamento_maximo'] <= ca_max)]

st.sidebar.markdown(f"**Zonas encontradas:** {len(filtro)}")

# --- MAPA INTERATIVO ---
centro = [-3.730451, -38.521798]  # Fortaleza
m = folium.Map(location=centro, zoom_start=12, tiles=base_mapa)

# Adiciona outras camadas base alternáveis
folium.TileLayer('OpenStreetMap').add_to(m)
folium.TileLayer('Stamen Terrain').add_to(m)
folium.TileLayer('Stamen Toner').add_to(m)
folium.TileLayer('CartoDB positron').add_to(m)
folium.TileLayer('Esri.WorldImagery', name='Esri Satellite').add_to(m)
folium.LayerControl().add_to(m)

for _, row in filtro.iterrows():
    if row.geometry is not None:
        geo_json = folium.GeoJson(
            row.geometry.__geo_interface__,
            tooltip=row['nome_zona'],
            popup=folium.Popup(f"<b>{row['nome_zona']}</b><br>CA Máx: {row['indice_aproveitamento_maximo']}<br>TO: {row['taxa_ocupacao_solo']}<br>Altura Máx: {row['altura_maxima']}", max_width=300)
        )
        geo_json.add_to(m)

st_data = st_folium(m, width=1200, height=700)

# --- BUSCA POR COORDENADA ---
st.subheader("📍 Consulta por Coordenada")
lat = st.number_input("Latitude:", value=-3.73, format="%.6f")
lon = st.number_input("Longitude:", value=-38.52, format="%.6f")

if st.button("Buscar Zona"):
    ponto = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326")
    zona_ponto = gdf[gdf.contains(ponto.iloc[0])]
    if not zona_ponto.empty:
        st.success(f"O ponto está dentro da zona: **{zona_ponto.iloc[0]['nome_zona']}**")
        st.json(zona_ponto.iloc[0].to_dict())
    else:
        st.warning("Nenhuma zona encontrada para as coordenadas informadas.")

# --- ESTATÍSTICAS GERAIS ---
st.subheader("📊 Estatísticas por Tipo de Zona")
if not filtro.empty:
    estat = filtro.groupby('tipo_zona').agg({
        'indice_aproveitamento_maximo': 'mean',
        'taxa_ocupacao_solo': 'mean',
        'taxa_permeabilidade': 'mean',
        'altura_maxima': 'mean'
    }).round(2).reset_index()
    st.dataframe(estat, use_container_width=True)
else:
    st.info("Ajuste os filtros para visualizar estatísticas.")

# --- EXPORTAÇÃO DE RESULTADOS ---
st.subheader("💾 Exportar Resultados Filtrados")
col1, col2 = st.columns(2)

csv_data = filtro.drop(columns='geometry').to_csv(index=False, encoding='utf-8-sig')
geojson_data = filtro.to_json()

with col1:
    st.download_button("⬇️ Baixar CSV", data=csv_data, file_name="zonas_filtradas.csv", mime="text/csv")

with col2:
    st.download_button("🌐 Baixar GeoJSON", data=geojson_data, file_name="zonas_filtradas.geojson", mime="application/geo+json")

# --- TABELA DE RESULTADOS ---
st.subheader("📋 Tabela de Zonas Filtradas")
st.dataframe(filtro[[
    'nome_zona', 'tipo_zona', 'indice_aproveitamento_basico', 'indice_aproveitamento_maximo',
    'taxa_ocupacao_solo', 'taxa_permeabilidade', 'altura_maxima'
]].reset_index(drop=True))

st.markdown("Desenvolvido por Cicero Mayk • Powered by Streamlit + PostGIS + Folium")
