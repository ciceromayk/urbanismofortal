import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
import plotly.express as px
import requests
import json
from shapely.geometry import Point
import streamlit.components.v1 as components

# --- CONFIGURAÇÕES INICIAIS ---
st.set_page_config(page_title="Zoneamento Fortaleza", layout="wide")

st.title("🏙️ Consulta Interativa – Zoneamento de Fortaleza")
st.markdown("Mapa interativo com identificação de zonas e busca por endereço (PDP Fortaleza)")

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

# --- INTERFACE DE BUSCA ---
st.subheader("📍 Buscar Endereço")
endereco = st.text_input("Digite um endereço ou local em Fortaleza:", placeholder="Ex: Av. Beira-Mar, Fortaleza")
coord_busca = None
info_zona_busca = None
zona_geojson = None

if st.button("🔎 Localizar Endereço") and endereco:
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={endereco}, Fortaleza&format=json&limit=1"
        response = requests.get(url, headers={'User-Agent': 'UrbanFortalApp/1.0'})
        data = response.json()
        if data:
            lat, lon = float(data[0]['lat']), float(data[0]['lon'])
            coord_busca = (lat, lon)
            ponto = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326")
            zona_ponto = gdf[gdf.contains(ponto.iloc[0])]
            if not zona_ponto.empty:
                z = zona_ponto.iloc[0]
                info_zona_busca = z
                zona_geojson = z.geometry.__geo_interface__
                st.success(f"📍 Endereço dentro da zona: **{z['nome_zona']}** — Tipo: **{z['tipo_zona']}**")
            else:
                st.warning("Endereço encontrado, mas fora de qualquer zona definida.")
        else:
            st.error("Endereço não encontrado. Verifique o texto digitado.")
    except Exception as e:
        st.error(f"Erro ao consultar o endereço: {e}")

# --- MAPA BASE ---
centro = [-3.730451, -38.521798]
m = folium.Map(location=centro, zoom_start=12, tiles='CartoDB positron')

# --- ADICIONA POLÍGONOS DE ZONAS ---
for _, row in gdf.iterrows():
    if row.geometry is not None:
        folium.GeoJson(
            row.geometry.__geo_interface__,
            tooltip=row['nome_zona'],
            popup=folium.Popup(
                f"<b>{row['nome_zona']}</b><br>CA Máx: {row['indice_aproveitamento_maximo']}<br>TO: {row['taxa_ocupacao_solo']}<br>Altura Máx: {row['altura_maxima']}",
                max_width=300
            )
        ).add_to(m)

# --- CLIQUE NO MAPA ---
def adicionar_interatividade():
    components.html(m.get_root().render(), height=700)

# --- DESTAQUE DE ZONA E PIN ---
def destacar_zona(lat, lon, zona_geojson, info_zona_busca):
    if info_zona_busca is not None and zona_geojson:
        area_ha = info_zona_busca.geometry.to_crs(3857).area / 10000
        perimetro_m = info_zona_busca.geometry.to_crs(3857).length

        folium.GeoJson(
            zona_geojson,
            name="Zona Selecionada",
            style_function=lambda x: {
                'fillColor': 'yellow',
                'color': 'red',
                'weight': 4,
                'fillOpacity': 0.15
            },
            tooltip=f"{info_zona_busca['nome_zona']}<br>Área: {area_ha:.2f} ha | Perímetro: {perimetro_m:.0f} m | ID: {info_zona_busca.name}"
        ).add_to(m)

        popup_text = (
            f"<b>Zona:</b> {info_zona_busca['nome_zona']}<br>"
            f"<b>Tipo:</b> {info_zona_busca['tipo_zona']}<br>"
            f"<b>CA Máx:</b> {info_zona_busca['indice_aproveitamento_maximo']}<br>"
            f"<b>Área:</b> {area_ha:.2f} ha<br>"
            f"<b>Perímetro:</b> {perimetro_m:.0f} m<br>"
            f"<b>ID:</b> {info_zona_busca.name}"
        )

        folium.Marker([lat, lon], popup=popup_text, icon=folium.Icon(color='red', icon='map-marker')).add_to(m)
        m.location = [lat, lon]
        m.zoom_start = 15

# --- SE HOUVER BUSCA ---
if coord_busca and zona_geojson:
    lat, lon = coord_busca
    destacar_zona(lat, lon, zona_geojson, info_zona_busca)

# --- MAPA INTERATIVO ---
components.html(m.get_root().render(), height=700)

# --- INSTRUÇÕES DE CLIQUE ---
st.markdown("**🖱️ Dica:** clique em qualquer ponto do mapa para identificar a zona correspondente.")
st.info("O modo de clique está ativo automaticamente e o mapa é renderizado via HTML para compatibilidade total.")

st.markdown("Desenvolvido por **Cicero Mayk** • Powered by Streamlit + Folium + OpenStreetMap")
