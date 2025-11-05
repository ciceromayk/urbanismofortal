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

modo_localizacao = st.sidebar.radio("Modo de Localização:", ["Buscar por Endereço", "Selecionar no Mapa"])

filtro = gdf.copy()
if zona_tipo:
    filtro = filtro[filtro['tipo_zona'].isin(zona_tipo)]
filtro = filtro[(filtro['indice_aproveitamento_maximo'] >= ca_min) & (filtro['indice_aproveitamento_maximo'] <= ca_max)]

st.sidebar.markdown(f"**Zonas encontradas:** {len(filtro)}")

# --- MAPA INTERATIVO ---
centro = [-3.730451, -38.521798]  # Fortaleza
m = folium.Map(location=centro, zoom_start=12, tiles=base_mapa)

# Adiciona camadas base com atribuições oficiais
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

# Adicionar zonas filtradas
for _, row in filtro.iterrows():
    if row.geometry is not None:
        geo_json = folium.GeoJson(
            row.geometry.__geo_interface__,
            tooltip=row['nome_zona'],
            popup=folium.Popup(f"<b>{row['nome_zona']}</b><br>CA Máx: {row['indice_aproveitamento_maximo']}<br>TO: {row['taxa_ocupacao_solo']}<br>Altura Máx: {row['altura_maxima']}", max_width=300)
        )
        geo_json.add_to(m)

coord_busca = None
info_zona_busca = None

# --- LOCALIZAÇÃO ---
st.subheader("📍 Localização")
if modo_localizacao == "Buscar por Endereço":
    endereco = st.text_input("Digite um endereço ou local em Fortaleza:", placeholder="Ex: Av. Beira-Mar, Fortaleza")
    if st.button("🔎 Localizar Endereço") and endereco:
        try:
            url = f"https://nominatim.openstreetmap.org/search?q={endereco}, Fortaleza&format=json&limit=1"
            response = requests.get(url, headers={'User-Agent': 'UrbanFortalApp/1.0'})
            data = response.json()
            if data:
                lat, lon = float(data[0]['lat']), float(data[0]['lon'])
                coord_busca = (lat, lon)
                st.success(f"📍 Endereço encontrado: ({lat:.5f}, {lon:.5f})")
                ponto = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326")
                zona_ponto = gdf[gdf.contains(ponto.iloc[0])]
                if not zona_ponto.empty:
                    z = zona_ponto.iloc[0]
                    info_zona_busca = z
                    st.info(f"O endereço está na zona **{z['nome_zona']}** — Tipo: **{z['tipo_zona']}**")
                    st.json(z.to_dict())
                else:
                    st.warning("Nenhuma zona encontrada para esse ponto.")
            else:
                st.error("Endereço não encontrado. Verifique o texto digitado.")
        except Exception as e:
            st.error(f"Erro ao consultar o endereço: {e}")

# Renderiza mapa e captura clique
st_data = st_folium(m, width=1200, height=700)

if modo_localizacao == "Selecionar no Mapa" and st_data and st_data.get("last_clicked"):
    lat = st_data["last_clicked"]["lat"]
    lon = st_data["last_clicked"]["lng"]
    coord_busca = (lat, lon)
    ponto = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326")
    zona_ponto = gdf[gdf.contains(ponto.iloc[0])]
    if not zona_ponto.empty:
        z = zona_ponto.iloc[0]
        info_zona_busca = z
        st.success(f"📍 Ponto selecionado dentro da zona: **{z['nome_zona']}** — Tipo: **{z['tipo_zona']}**")
        st.json(z.to_dict())
    else:
        st.warning("Nenhuma zona encontrada nesse ponto.")

# --- MARCADOR DO PONTO ---
if coord_busca:
    lat, lon = coord_busca
    m.location = [lat, lon]
    m.zoom_start = 15
    popup_text = f"<b>Ponto Selecionado</b><br>Lat: {lat:.5f}, Lon: {lon:.5f}"
    if info_zona_busca is not None:
        popup_text += f"<br><b>Zona:</b> {info_zona_busca['nome_zona']}<br><b>Tipo:</b> {info_zona_busca['tipo_zona']}<br><b>CA Máx:</b> {info_zona_busca['indice_aproveitamento_maximo']}"
    folium.Marker([lat, lon], popup=popup_text, icon=folium.Icon(color='red', icon='map-marker')).add_to(m)

# Re-renderiza mapa com marcador
st_data = st_folium(m, width=1200, height=700)

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

# --- PAINEL DE INDICADORES URBANÍSTICOS ---
st.subheader("📈 Painel de Indicadores Urbanísticos")
if not filtro.empty:
    col1, col2 = st.columns(2)

    with col1:
        fig1 = px.bar(estat, x='tipo_zona', y='indice_aproveitamento_maximo', title='CA Máximo Médio por Tipo de Zona', color='tipo_zona')
        st.plotly_chart(fig1, use_container_width=True)

    with col2:
        fig2 = px.scatter(filtro, x='indice_aproveitamento_maximo', y='altura_maxima', color='tipo_zona', title='Relação entre CA Máximo e Altura Máxima')
        st.plotly_chart(fig2, use_container_width=True)

    st.markdown("### 🌿 Zonas com Maior Permeabilidade Média")
    fig3 = px.bar(estat.sort_values('taxa_permeabilidade', ascending=False), x='tipo_zona', y='taxa_permeabilidade', color='tipo_zona')
    st.plotly_chart(fig3, use_container_width=True)
else:
    st.info("Nenhuma zona filtrada para gerar gráficos.")

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

st.markdown("Desenvolvido por Cicero Mayk • Powered by Streamlit + PostGIS + Folium + Plotly + OpenStreetMap")
