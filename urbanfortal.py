import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
from shapely.geometry import Point
from streamlit_folium import st_folium
import requests

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

# --- FUNÇÃO DESTACAR ZONA ---
def destacar_zona(lat, lon, gdf):
    ponto = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326")
    zona_ponto = gdf[gdf.contains(ponto.iloc[0])]
    if not zona_ponto.empty:
        z = zona_ponto.iloc[0]
        geom_gdf = gpd.GeoDataFrame(index=[0], crs="EPSG:4326", geometry=[z.geometry])
        geom_gdf_3857 = geom_gdf.to_crs(epsg=3857)
        area_ha = geom_gdf_3857.area.iloc[0] / 10000
        perimetro_m = geom_gdf_3857.length.iloc[0]

        folium.GeoJson(
            z.geometry.__geo_interface__,
            name="Zona Selecionada",
            style_function=lambda x: {
                'fillColor': 'yellow',
                'color': 'red',
                'weight': 4,
                'fillOpacity': 0.15
            },
            tooltip=f"{z['nome_zona']}<br>Área: {area_ha:.2f} ha | Perímetro: {perimetro_m:.0f} m | ID: {z.name}"
        ).add_to(m)

        popup_text = (
            f"<b>Zona:</b> {z['nome_zona']}<br>"
            f"<b>Tipo:</b> {z['tipo_zona']}<br>"
            f"<b>CA Máx:</b> {z['indice_aproveitamento_maximo']}<br>"
            f"<b>Área:</b> {area_ha:.2f} ha<br>"
            f"<b>Perímetro:</b> {perimetro_m:.0f} m<br>"
            f"<b>ID:</b> {z.name}"
        )
        folium.Marker([lat, lon], popup=popup_text, icon=folium.Icon(color='red', icon='map-marker')).add_to(m)
        return True
    return False

# --- MAPA INTERATIVO ---
st.write("🗺️ Clique em qualquer ponto do mapa ou busque um endereço para identificar a zona.")
st_data = st_folium(m, width=1200, height=700, key="mapa_zoneamento")

# --- TRATAR CLIQUE ---
if st_data and st_data.get("last_clicked"):
    lat = st_data["last_clicked"]["lat"]
    lon = st_data["last_clicked"]["lng"]
    if destacar_zona(lat, lon, gdf):
        st.success(f"🖱️ Zona identificada no clique! Lat: {lat:.5f}, Lon: {lon:.5f}")
    else:
        st.warning("Nenhuma zona encontrada neste ponto.")

# --- SE BUSCA POR ENDEREÇO ---
if coord_busca:
    lat, lon = coord_busca
    if destacar_zona(lat, lon, gdf):
        st.info(f"📍 Endereço plotado no mapa (Lat: {lat:.5f}, Lon: {lon:.5f})")

st.markdown("Desenvolvido por **Cicero Mayk** • Powered by Streamlit + Folium + OpenStreetMap")
