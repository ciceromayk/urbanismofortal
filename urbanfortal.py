import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
import requests
from shapely.geometry import Point
from streamlit_folium import st_folium # Importação otimizada para interatividade

# --- CONFIGURAÇÕES INICIAIS ---
st.set_page_config(page_title="Zoneamento Fortaleza", layout="wide")

st.title("🏙️ Consulta Interativa – Zoneamento de Fortaleza")
st.markdown("Mapa interativo com identificação de zonas e busca por endereço (PDP Fortaleza)")

# --- CONSTANTES ---
CENTRO_FORTALEZA = [-3.730451, -38.521798]
CRS_GEO = "EPSG:4326"
CRS_METRIC = "EPSG:3857" # Para cálculos de área e perímetro em metros

# --- CARREGAR DADOS ---
@st.cache_data
def carregar_dados():
    """Carrega dados geoespaciais do CSV com cache."""
    try:
        # Nota: O arquivo zoneamento_fortaleza.csv deve estar na mesma pasta
        df = pd.read_csv("zoneamento_fortaleza.csv") 
        gdf = gpd.GeoDataFrame(
            df.drop(columns=['wkt_multipolygon']),
            geometry=gpd.GeoSeries.from_wkt(df['wkt_multipolygon']),
            crs=CRS_GEO
        )
        return gdf
    except FileNotFoundError:
        st.error("❌ Arquivo 'zoneamento_fortaleza.csv' não encontrado. Coloque-o na mesma pasta do app.")
        return None

gdf = carregar_dados()
if gdf is None:
    st.stop()

# --- SIDEBAR PARA INFORMAÇÕES E PARÂMETROS URBANÍSTICOS ---
with st.sidebar:
    st.title("Parâmetros Urbanísticos")
    sidebar_placeholder = st.empty() # Placeholder para conteúdo dinâmico da zona
    
# --- FUNÇÃO AUXILIAR: EXIBIR INFORMAÇÕES DA ZONA NO SIDEBAR ---
def exibir_info_zona(zona_encontrada):
    """Exibe as informações tabulares e formatadas da zona no placeholder do sidebar."""
    if not zona_encontrada.empty:
        z = zona_encontrada.iloc[0]
        
        # Cálculos Geográficos
        area_ha = z.geometry.to_crs(CRS_METRIC).area / 10000
        perimetro_m = z.geometry.to_crs(CRS_METRIC).length

        # Conteúdo a ser renderizado no sidebar
        with sidebar_placeholder.container():
            st.markdown("---")
            st.subheader(f"Zona: {z['nome_zona']}")
            st.write(f"**Tipo de Zona:** {z['tipo_zona']}")
            st.markdown(f"**Geometria:**<br>Área: **{area_ha:.2f} ha**<br>Perímetro: **{perimetro_m:.0f} m**", unsafe_allow_html=True)
            
            # Parâmetros Urbanísticos (Tabela)
            params = pd.DataFrame({
                'Parâmetro': ['CA Básico', 'CA Máximo', 'TO Solo', 'TO Subsolo', 'Altura Máxima', 'Permeabilidade'],
                'Valor': [z['indice_aproveitamento_basico'], z['indice_aproveitamento_maximo'], z['taxa_ocupacao_solo'], z['taxa_ocupacao_subsolo'], z['altura_maxima'], z['taxa_permeabilidade']]
            }).set_index('Parâmetro')
            st.dataframe(params)
        
        return z, z.geometry.__geo_interface__
    return None, None

# --- INTERFACE DE BUSCA ---
st.subheader("📍 Buscar Endereço")
endereco = st.text_input("Digite um endereço ou local em Fortaleza:", placeholder="Ex: Av. Beira-Mar, 2000")
coord_busca = None
zona_geojson = None
info_zona_busca = None

if st.button("🔎 Localizar Endereço") and endereco:
    # Limpa o placeholder do sidebar em nova busca
    sidebar_placeholder.empty() 
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={endereco}, Fortaleza&format=json&limit=1"
        response = requests.get(url, headers={'User-Agent': 'UrbanFortalApp/1.0'})
        data = response.json()
        
        if data:
            lat, lon = float(data[0]['lat']), float(data[0]['lon'])
            coord_busca = (lat, lon)
            ponto = gpd.GeoSeries([Point(lon, lat)], crs=CRS_GEO)
            zona_ponto = gdf[gdf.contains(ponto.iloc[0])]

            if not zona_ponto.empty:
                st.success(f"📍 Endereço encontrado.")
                # CHAMA A FUNÇÃO PARA EXIBIR INFORMAÇÕES NO SIDEBAR
                info_zona_busca, zona_geojson = exibir_info_zona(zona_ponto)
            else:
                st.warning("Endereço encontrado, mas fora de qualquer zona definida.")
        else:
            st.error("Endereço não encontrado. Verifique o texto digitado.")
            
    except Exception as e:
        st.error(f"Erro ao consultar o endereço: {e}")
        sidebar_placeholder.empty()

# --- MAPA BASE ---
m = folium.Map(location=CENTRO_FORTALEZA, zoom_start=12, tiles='CartoDB positron')

# --- ADICIONA POLÍGONOS DE ZONAS (BASE) ---
# Adiciona todos os polígonos com tooltips
for _, row in gdf.iterrows():
    if row.geometry is not None:
        tooltip_text = f"<b>{row['nome_zona']}</b><br>CA Máx: {row['indice_aproveitamento_maximo']}<br>TO: {row['taxa_ocupacao_solo']}<br>Altura Máx: {row['altura_maxima']}"
        folium.GeoJson(
            row.geometry.__geo_interface__,
            tooltip=tooltip_text,
            name=row['nome_zona'],
            style_function=lambda x: {
                'fillColor': '#A0A0A0', # Cor cinza suave para a base
                'color': '#808080',
                'weight': 1,
                'fillOpacity': 0.1
            }
        ).add_to(m)

# --- DESTAQUE DE ZONA DE BUSCA (SE HOUVER) ---
if coord_busca and zona_geojson:
    lat, lon = coord_busca
    # 1. Adiciona o destaque (highlight) da zona
    folium.GeoJson(
        zona_geojson,
        name="Zona Buscada",
        style_function=lambda x: {
            'fillColor': 'yellow',
            'color': 'red',
            'weight': 4,
            'fillOpacity': 0.15
        },
        tooltip=info_zona_busca['nome_zona']
    ).add_to(m)
    
    # 2. Adiciona o marcador (pin)
    folium.Marker([lat, lon], popup=f"Endereço Buscado:<br>{info_zona_busca['nome_zona']}", icon=folium.Icon(color='red', icon='map-marker')).add_to(m)
    # Move o centro do mapa para o marcador
    m.location = [lat, lon]
    m.zoom_start = 15

# --- RENDERIZAÇÃO INTERATIVA COM STREAMLIT-FOLIUM ---
st.subheader("Mapa Interativo")
st.markdown("**🖱️ Dica:** clique em qualquer ponto do mapa para identificar a zona correspondente.")
map_data = st_folium(m, height=700, width=None, returned_objects=["last_clicked"])

# --- TRATAMENTO DE CLIQUE NO MAPA ---
if map_data and map_data.get("last_clicked"):
    # Limpa o placeholder do sidebar ao clicar no mapa
    sidebar_placeholder.empty()
    clicked_lat = map_data["last_clicked"]["lat"]
    clicked_lon = map_data["last_clicked"]["lng"]

    # Realiza a consulta espacial para o ponto clicado
    ponto_clicado = gpd.GeoSeries([Point(clicked_lon, clicked_lat)], crs=CRS_GEO)
    zona_ponto_clicado = gdf[gdf.contains(ponto_clicado.iloc[0])]

    if not zona_ponto_clicado.empty:
        # CHAMA A FUNÇÃO PARA EXIBIR INFORMAÇÕES NO SIDEBAR
        exibir_info_zona(zona_ponto_clicado)
    else:
        with sidebar_placeholder.container():
            st.markdown("---")
            st.warning("Ponto clicado fora de uma zona definida.")

st.markdown("Desenvolvido por **Cicero Mayk** • Powered by Streamlit + Folium + OpenStreetMap")
