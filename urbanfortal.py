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

# --- GERENCIAMENTO DE ESTADO (Para manter a seleção consistente) ---
if 'last_selection_coords' not in st.session_state:
    st.session_state.last_selection_coords = None
    st.session_state.last_selection_geojson = None
    st.session_state.last_selection_info = None

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
    """
    Exibe as informações tabulares e formatadas da zona no placeholder do sidebar.
    Retorna o objeto Serie (z) e a GeoJSON interface.
    """
    if not zona_encontrada.empty:
        z = zona_encontrada.iloc[0]
        
        # CÁLCULOS GEOGRÁFICOS: (Correção do AttributeError mantida)
        zona_proj = zona_encontrada.to_crs(CRS_METRIC)
        area_ha = zona_proj.area.iloc[0] / 10000
        perimetro_m = zona_proj.length.iloc[0]

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

# --- INTERFACE DE BUSCA (ATUALIZADA PARA USAR O ESTADO) ---
st.subheader("📍 Buscar Endereço")
endereco = st.text_input("Digite um endereço ou local em Fortaleza:", placeholder="Ex: Av. Beira-Mar, 2000")

if st.button("🔎 Localizar Endereço") and endereco:
    # 1. Resetar o estado da seleção anterior
    st.session_state.last_selection_coords = None
    st.session_state.last_selection_geojson = None
    st.session_state.last_selection_info = None
    sidebar_placeholder.empty() 
    
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={endereco}, Fortaleza&format=json&limit=1"
        response = requests.get(url, headers={'User-Agent': 'UrbanFortalApp/1.0'})
        data = response.json()
        
        if data:
            lat, lon = float(data[0]['lat']), float(data[0]['lon'])
            ponto = gpd.GeoSeries([Point(lon, lat)], crs=CRS_GEO)
            zona_ponto = gdf[gdf.contains(ponto.iloc[0])]

            if not zona_ponto.empty:
                st.success(f"📍 Endereço encontrado.")
                
                # 2. CHAMA A FUNÇÃO E ATUALIZA O ESTADO (SUCESSO)
                info_zona_busca, zona_geojson = exibir_info_zona(zona_ponto)
                st.session_state.last_selection_coords = (lat, lon)
                st.session_state.last_selection_geojson = zona_geojson
                st.session_state.last_selection_info = info_zona_busca
                
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

# --- DESTAQUE DA ZONA SELECIONADA (UNIFICADO) ---
# Esta seção agora verifica o st.session_state, garantindo o mesmo visual para Busca e Clique
if st.session_state.last_selection_coords and st.session_state.last_selection_geojson:
    lat, lon = st.session_state.last_selection_coords
    info_zona = st.session_state.last_selection_info
    geojson = st.session_state.last_selection_geojson
    
    # 1. Adiciona o destaque (highlight) da zona
    folium.GeoJson(
        geojson,
        name="Zona Selecionada",
        style_function=lambda x: {
            'fillColor': 'yellow',
            'color': 'red',
            'weight': 4,
            'fillOpacity': 0.15
        },
        tooltip=info_zona['nome_zona']
    ).add_to(m)
    
    # 2. Adiciona o marcador (pin)
    folium.Marker([lat, lon], popup=f"Ponto Selecionado:<br>{info_zona['nome_zona']}", icon=folium.Icon(color='red', icon='map-marker')).add_to(m)
    
    # Se a seleção foi recente, centraliza o mapa (opcional, pode ser removido)
    m.location = [lat, lon]
    m.zoom_start = 15

# --- RENDERIZAÇÃO INTERATIVA COM STREAMLIT-FOLIUM ---
st.subheader("Mapa Interativo")
st.markdown("**🖱️ Dica:** clique em qualquer ponto do mapa para identificar a zona correspondente e colocar um pin.")
# O mapa é renderizado e retorna o objeto de clique
map_data = st_folium(m, height=700, width=None, returned_objects=["last_clicked"])

# --- TRATAMENTO DE CLIQUE NO MAPA (ATUALIZADO PARA USAR O ESTADO) ---
if map_data and map_data.get("last_clicked"):
    # 1. Resetar o estado da seleção anterior (se for um novo clique)
    st.session_state.last_selection_coords = None
    st.session_state.last_selection_geojson = None
    st.session_state.last_selection_info = None
    sidebar_placeholder.empty()

    clicked_lat = map_data["last_clicked"]["lat"]
    clicked_lon = map_data["last_clicked"]["lng"]

    # Realiza a consulta espacial para o ponto clicado
    ponto_clicado = gpd.GeoSeries([Point(clicked_lon, clicked_lat)], crs=CRS_GEO)
    zona_ponto_clicado = gdf[gdf.contains(ponto_clicado.iloc[0])]

    if not zona_ponto_clicado.empty:
        # 2. CHAMA A FUNÇÃO E ATUALIZA O ESTADO (SUCESSO)
        info_zona_clicada, zona_geojson_clicada = exibir_info_zona(zona_ponto_clicado)
        st.session_state.last_selection_coords = (clicked_lat, clicked_lon)
        st.session_state.last_selection_geojson = zona_geojson_clicada
        st.session_state.last_selection_info = info_zona_clicada
        # Força o Streamlit a rodar novamente para desenhar o Pin e o Destaque
        st.rerun() 
    else:
        with sidebar_placeholder.container():
            st.markdown("---")
            st.warning("Ponto clicado fora de uma zona definida.")

st.markdown("Desenvolvido por **Cicero Mayk** • Powered by Streamlit + Folium + OpenStreetMap")
