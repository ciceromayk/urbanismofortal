import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
import requests
from shapely.geometry import Point
from streamlit_folium import st_folium

# --- CONFIGURAÇÕES INICIAIS ---
st.set_page_config(page_title="Zoneamento Fortaleza", layout="wide")

st.title("🏙️ Consulta Interativa – Zoneamento de Fortaleza")
st.markdown("Mapa interativo com identificação de zonas e busca por endereço (PDP Fortaleza)")

# --- CONSTANTES ---
CENTRO_FORTALEZA = [-3.730451, -38.521798]
CRS_GEO = "EPSG:4326"
CRS_METRIC = "EPSG:3857" # Para cálculos de área e perímetro em metros

# Dicionário de camadas base (tiles) para o dropdown
MAP_TILES = {
    "OpenStreetMap (Padrão)": "OpenStreetMap",
    "CartoDB Positron": "CartoDB positron",
    "CartoDB Dark Matter": "CartoDB dark_matter",
    "Esri World Imagery (Satélite)": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
}

# --- CARREGAR DADOS ---
@st.cache_data
def carregar_dados():
    """Carrega dados geoespaciais do CSV com cache."""
    try:
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
    
    # Adiciona o dropdown para tipo de mapa no topo do sidebar
    st.subheader("Opções de Mapa")
    tile_selection = st.selectbox(
        "Selecione a Camada Base:",
        list(MAP_TILES.keys())
    )
    selected_tile = MAP_TILES[tile_selection]
    
    st.markdown("---")
    sidebar_placeholder = st.empty() # Placeholder para conteúdo dinâmico da zona

# --- FUNÇÃO AUXILIAR: GEOCÓDIGO REVERSO ---
def reverse_geocode(lat, lon):
    """Converte coordenadas em um endereço usando Nominatim."""
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
        response = requests.get(url, headers={'User-Agent': 'UrbanFortalApp/1.0'})
        data = response.json()
        return data.get('display_name', 'Endereço não identificado.')
    except:
        return 'Erro ao buscar o endereço.'

# --- FUNÇÃO AUXILIAR: EXIBIR INFORMAÇÕES DA ZONA NO SIDEBAR ---
def exibir_info_zona(zona_encontrada, lat=None, lon=None):
    """Exibe as informações tabulares e formatadas da zona no placeholder do sidebar."""
    if not zona_encontrada.empty:
        z = zona_encontrada.iloc[0]
        
        # Cálculos Geográficos (Corrigido o AttributeError)
        zona_proj = zona_encontrada.to_crs(CRS_METRIC)
        area_ha = zona_proj.area.iloc[0] / 10000
        perimetro_m = zona_proj.length.iloc[0]

        # Conteúdo a ser renderizado no sidebar
        with sidebar_placeholder.container():
            st.markdown("---")
            st.subheader(f"Zona: {z['nome_zona']}")
            
            # Inclui o Endereço do Local (Se fornecido)
            if lat is not None and lon is not None:
                endereco_completo = reverse_geocode(lat, lon)
                st.info(f"**Local:** {endereco_completo}")

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
                # Passa as coordenadas para exibir o endereço geocodificado no sidebar
                info_zona_busca, zona_geojson = exibir_info_zona(zona_ponto, lat=lat, lon=lon) 
            else:
                st.warning("Endereço encontrado, mas fora de qualquer zona definida.")
        else:
            st.error("Endereço não encontrado. Verifique o texto digitado.")
            
    except Exception as e:
        st.error(f"Erro ao consultar o endereço: {e}")
        sidebar_placeholder.empty()

# --- MAPA BASE ---
# Usa a camada selecionada pelo usuário
if tile_selection == "Esri World Imagery (Satélite)":
    m = folium.Map(location=CENTRO_FORTALEZA, zoom_start=12, tiles=selected_tile, attr='Esri World Imagery')
else:
    m = folium.Map(location=CENTRO_FORTALEZA, zoom_start=12, tiles=selected_tile)


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
                'fillColor': '#A0A0A0',
                'color': '#808080',
                'weight': 1,
                'fillOpacity': 0.1
            }
        ).add_to(m)

# --- DESTAQUE DE ZONA DE BUSCA (SE HOUVER) ---
if coord_busca and zona_geojson:
    lat, lon = coord_busca
    # 1. Adiciona o destaque (highlight) da zona - Corrigido para remover a linha retangular
    folium.GeoJson(
        zona_geojson,
        name="Zona Buscada",
        style_function=lambda x: {
            'fillColor': '#FFD700', # Cor amarela
            'color': 'none',        # <--- CORREÇÃO: Linha removida
            'weight': 0,            # <--- CORREÇÃO: Peso zero
            'fillOpacity': 0.4      # Aumenta a opacidade do preenchimento
        },
        tooltip=info_zona_busca['nome_zona']
    ).add_to(m)
    
    # 2. Adiciona o marcador (pin)
    folium.Marker([lat, lon], popup=f"Endereço Buscado:<br>{info_zona_busca['nome_zona']}", icon=folium.Icon(color='red', icon='map-marker')).add_to(m)
    m.location = [lat, lon]
    m.zoom_start = 15

# --- RENDERIZAÇÃO INTERATIVA COM STREAMLIT-FOLIUM ---
st.subheader("Mapa Interativo")
st.markdown("**🖱️ Dica:** clique em qualquer ponto do mapa para identificar a zona correspondente.")
map_data = st_folium(m, height=700, width=None, returned_objects=["last_clicked"])

# --- TRATAMENTO DE CLIQUE NO MAPA ---
if map_data and map_data.get("last_clicked"):
    sidebar_placeholder.empty()
    clicked_lat = map_data["last_clicked"]["lat"]
    clicked_lon = map_data["last_clicked"]["lng"]

    # Realiza a consulta espacial para o ponto clicado
    ponto_clicado = gpd.GeoSeries([Point(clicked_lon, clicked_lat)], crs=CRS_GEO)
    zona_ponto_clicado = gdf[gdf.contains(ponto_clicado.iloc[0])]

    if not zona_ponto_clicado.empty:
        # CHAMA A FUNÇÃO PARA EXIBIR INFORMAÇÕES NO SIDEBAR, passando as coordenadas do clique
        exibir_info_zona(zona_ponto_clicado, lat=clicked_lat, lon=clicked_lon)
        
        # Opcional: Adicionar um marcador no local do clique para visualização
        folium.Marker([clicked_lat, clicked_lon], popup="Local do Clique", icon=folium.Icon(color='blue', icon='info')).add_to(m)
        # Nota: O marcador não aparece instantaneamente sem a nova renderização do mapa,
        # mas pode ser útil para depuração ou se o mapa for rerenderizado por outra ação.
    else:
        with sidebar_placeholder.container():
            st.markdown("---")
            st.warning("Ponto clicado fora de uma zona definida.")

st.markdown("Desenvolvido por **Cicero Mayk** • Powered by Streamlit + Folium + OpenStreetMap")
