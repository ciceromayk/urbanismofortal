from typing import Optional, Tuple

import folium
import geopandas as gpd
import pandas as pd
import requests
import streamlit as st
from folium.features import GeoJsonPopup, GeoJsonTooltip
from shapely.geometry import Point
from streamlit_folium import st_folium

# --- CONFIGURAÇÕES INICIAIS ---
st.set_page_config(page_title="Zoneamento Fortaleza", layout="wide")

st.title("🏙️ Consulta Interativa – Zoneamento de Fortaleza")
st.markdown("Mapa interativo com identificação de zonas e busca por endereço (PDP Fortaleza)")


@st.cache_data
def carregar_dados() -> Optional[gpd.GeoDataFrame]:
    """Carrega o CSV de zoneamento e calcula métricas geométricas auxiliares."""

    try:
        df = pd.read_csv("zoneamento_fortaleza.csv")
        gdf = gpd.GeoDataFrame(
            df.drop(columns=["wkt_multipolygon"]),
            geometry=gpd.GeoSeries.from_wkt(df["wkt_multipolygon"]),
            crs="EPSG:4326",
        )

        gdf_3857 = gdf.to_crs(epsg=3857)
        gdf["area_hectares"] = gdf_3857.geometry.area / 10_000
        gdf["perimetro_metros"] = gdf_3857.geometry.length
        return gdf
    except FileNotFoundError:
        st.error(
            "❌ Arquivo 'zoneamento_fortaleza.csv' não encontrado. Coloque-o na mesma pasta do app."
        )
        return None
    except Exception as err:  # pylint: disable=broad-except
        st.error(f"Erro ao carregar dados de zoneamento: {err}")
        return None


def solicitar_rerun() -> None:
    """Aciona nova execução do app, compatível com diferentes versões do Streamlit."""

    try:
        st.rerun()
    except AttributeError:
        st.experimental_rerun()


def geocodificar_endereco(endereco: str) -> Optional[Tuple[float, float]]:
    """Consulta o Nominatim e retorna latitude/longitude se o endereço for encontrado."""

    params = {
        "q": f"{endereco}, Fortaleza, Brasil",
        "format": "json",
        "limit": 1,
    }
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params=params,
            headers={"User-Agent": "UrbanFortalApp/1.0"},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as exc:
        st.session_state["feedback"] = (
            "error",
            f"Erro ao consultar o serviço de geocodificação: {exc}",
        )
        return None

    if not data:
        st.session_state["feedback"] = (
            "error",
            "Endereço não encontrado. Verifique o texto digitado.",
        )
        return None

    return float(data[0]["lat"]), float(data[0]["lon"])


def buscar_zona_por_ponto(lat: float, lon: float, gdf: gpd.GeoDataFrame) -> Optional[pd.Series]:
    """Retorna a linha do GeoDataFrame correspondente à zona do ponto informado."""

    ponto = Point(lon, lat)
    zona = gdf[gdf.contains(ponto)]
    if zona.empty:
        return None
    return zona.iloc[0]


def criar_mapa(gdf: gpd.GeoDataFrame, location: Tuple[float, float]) -> folium.Map:
    """Cria o mapa base com todas as zonas carregadas."""

    mapa = folium.Map(location=location, zoom_start=12, tiles="CartoDB positron")

    folium.GeoJson(
        gdf,
        name="Todas as zonas",
        style_function=lambda _: {
            "fillColor": "#3498db",
            "color": "#2c3e50",
            "weight": 1,
            "fillOpacity": 0.1,
        },
        tooltip=GeoJsonTooltip(
            fields=["nome_zona", "tipo_zona"],
            aliases=["Zona", "Tipo"],
            labels=True,
            sticky=False,
        ),
        popup=GeoJsonPopup(
            fields=[
                "nome_zona",
                "indice_aproveitamento_maximo",
                "taxa_ocupacao_solo",
                "altura_maxima",
            ],
            aliases=["Zona", "CA Máx", "Taxa Ocupação", "Altura Máx"],
            localize=True,
        ),
    ).add_to(mapa)

    folium.LayerControl(collapsed=False).add_to(mapa)
    return mapa


def destacar_zona(
    lat: float, lon: float, gdf: gpd.GeoDataFrame, mapa: folium.Map
) -> Optional[pd.Series]:
    """Destaca a zona correspondente ao ponto informado no mapa."""

    zona = buscar_zona_por_ponto(lat, lon, gdf)
    if zona is None:
        return None

    folium.GeoJson(
        zona.geometry.__geo_interface__,
        name="Zona selecionada",
        style_function=lambda _: {
            "fillColor": "yellow",
            "color": "red",
            "weight": 4,
            "fillOpacity": 0.2,
        },
        tooltip=(
            f"{zona['nome_zona']}<br>Área: {zona['area_hectares']:.2f} ha | "
            f"Perímetro: {zona['perimetro_metros']:.0f} m"
        ),
    ).add_to(mapa)

    popup_text = (
        f"<b>Zona:</b> {zona['nome_zona']}<br>"
        f"<b>Tipo:</b> {zona['tipo_zona']}<br>"
        f"<b>CA Máx:</b> {zona['indice_aproveitamento_maximo']}<br>"
        f"<b>Área:</b> {zona['area_hectares']:.2f} ha<br>"
        f"<b>Perímetro:</b> {zona['perimetro_metros']:.0f} m"
    )
    folium.Marker(
        [lat, lon],
        popup=popup_text,
        icon=folium.Icon(color="red", icon="map-marker"),
    ).add_to(mapa)

    return zona


# --- CARREGAR DADOS ---
gdf = carregar_dados()
if gdf is None:
    st.stop()

if "selected_point" not in st.session_state:
    st.session_state["selected_point"] = None
if "feedback" not in st.session_state:
    st.session_state["feedback"] = None

# --- INTERFACE DE BUSCA ---
st.subheader("📍 Buscar Endereço")
endereco_input = st.text_input(
    "Digite um endereço ou local em Fortaleza:",
    placeholder="Ex: Av. Beira-Mar, Fortaleza",
)
endereco = endereco_input.strip()

if st.button("🔎 Localizar Endereço"):
    if len(endereco) < 3:
        st.warning("Digite pelo menos 3 caracteres para realizar a busca.")
    else:
        with st.spinner("Consultando serviço de geocodificação..."):
            coordenadas = geocodificar_endereco(endereco)
        if coordenadas:
            lat, lon = coordenadas
            zona = buscar_zona_por_ponto(lat, lon, gdf)
            st.session_state["selected_point"] = (lat, lon)
            if zona is not None:
                st.session_state["feedback"] = (
                    "success",
                    f"📍 Endereço dentro da zona: **{zona['nome_zona']}** — Tipo: **{zona['tipo_zona']}**",
                )
            else:
                st.session_state["feedback"] = (
                    "warning",
                    "Endereço encontrado, mas fora de qualquer zona definida.",
                )
            solicitar_rerun()

# --- MAPA BASE ---
centro = (-3.730451, -38.521798)
map_location = st.session_state.get("selected_point") or centro
mapa = criar_mapa(gdf, map_location)

info_zona_atual = None
selected_point = st.session_state.get("selected_point")
if selected_point:
    info_zona_atual = destacar_zona(selected_point[0], selected_point[1], gdf, mapa)

if st.session_state.get("feedback"):
    nivel, mensagem = st.session_state["feedback"]
    if nivel == "success":
        st.success(mensagem)
    elif nivel == "warning":
        st.warning(mensagem)
    elif nivel == "error":
        st.error(mensagem)
    st.session_state["feedback"] = None

# --- MAPA INTERATIVO ---
st.write("🗺️ Clique em qualquer ponto do mapa ou busque um endereço para identificar a zona.")
st_data = st_folium(mapa, width=1200, height=700, key="mapa_zoneamento")

if st_data and st_data.get("last_clicked"):
    lat = st_data["last_clicked"]["lat"]
    lon = st_data["last_clicked"]["lng"]
    zona = buscar_zona_por_ponto(lat, lon, gdf)
    st.session_state["selected_point"] = (lat, lon)
    if zona is not None:
        st.session_state["feedback"] = (
            "success",
            f"🖱️ Zona identificada no clique! Lat: {lat:.5f}, Lon: {lon:.5f}",
        )
    else:
        st.session_state["feedback"] = (
            "warning",
            "Nenhuma zona encontrada neste ponto.",
        )
    solicitar_rerun()

if info_zona_atual is not None:
    with st.sidebar:
        st.header("📌 Zona Selecionada")
        st.markdown(f"**{info_zona_atual['nome_zona']}** ({info_zona_atual['tipo_zona']})")
        st.markdown(
            "\n".join(
                [
                    f"• CA Máx: {info_zona_atual['indice_aproveitamento_maximo']}",
                    f"• Taxa de ocupação: {info_zona_atual['taxa_ocupacao_solo']}",
                    f"• Altura Máx: {info_zona_atual['altura_maxima']}",
                    f"• Área: {info_zona_atual['area_hectares']:.2f} ha",
                    f"• Perímetro: {info_zona_atual['perimetro_metros']:.0f} m",
                ]
            )
        )

st.markdown("Desenvolvido por **Cicero Mayk** • Powered by Streamlit + Folium + OpenStreetMap")
