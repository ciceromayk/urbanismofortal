from __future__ import annotations
from typing import Dict
import geopandas as gpd
import pandas as pd


def _popup_html(row) -> str:
    """Gera o HTML do popup com nome, descrição e demais atributos."""
    parts = []
    if "name" in row and row["name"]:
        parts.append(f"<b>Nome:</b> {row['name']}")
    if "description" in row and row["description"]:
        parts.append(f"<b>Descrição:</b> {row['description']}")
    for k, v in row.items():
        if k in ("name", "description", "geometry", "__layer__"):
            continue
        if v not in (None, ""):
            parts.append(f"<b>{k}:</b> {v}")
    return "<br>".join(parts) if parts else "<i>Sem atributos</i>"


def build_folium_map(
    gdfs_by_type: Dict[str, gpd.GeoDataFrame],
    style: Dict,
    show_popups: bool,
    show_tooltips: bool,
):
    """Constrói o mapa interativo usando Folium."""
    import folium
    from folium import FeatureGroup, GeoJson, Popup, Tooltip
    from shapely.geometry import Point

    # Centro inicial
    all_nonempty = [g for g in gdfs_by_type.values() if len(g) > 0]
    if all_nonempty:
        bounds = (
            gpd.GeoDataFrame(
                pd.concat(all_nonempty), geometry="geometry", crs=all_nonempty[0].crs
            )
            .to_crs(4326)
            .total_bounds
        )
        center = [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2]
        zoom_start = 11
    el
