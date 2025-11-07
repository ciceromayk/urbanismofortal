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
    else:
        center = [-3.730451, -38.521798]  # Fortaleza
        zoom_start = 12

    m = folium.Map(location=center, zoom_start=zoom_start, control_scale=True)

    # Pontos
    if "points" in gdfs_by_type and len(gdfs_by_type["points"]) > 0:
        fg = FeatureGroup(name="Pontos", show=True)
        for _, row in gdfs_by_type["points"].to_crs(4326).iterrows():
            geom = row.geometry
            if isinstance(geom, Point):
                marker = folium.CircleMarker(
                    location=[geom.y, geom.x],
                    radius=6,
                    color=style["point_color"],
                    fill=True,
                    fill_color=style["point_color"],
                    fill_opacity=style["opacity"],
                    weight=style["weight"],
                )
                if show_popups:
                    marker.add_child(Popup(_popup_html(row), max_width=350))
                if show_tooltips and row.get("name"):
                    marker.add_child(Tooltip(str(row.get("name"))))
                marker.add_to(fg)
        fg.add_to(m)

    # Linhas
    if "lines" in gdfs_by_type and len(gdfs_by_type["lines"]) > 0:
        def _ls_style(_):
            return {
                "color": style["line_color"],
                "weight": style["weight"],
                "opacity": style["opacity"],
            }

        gj = GeoJson(
            data=gdfs_by_type["lines"].to_crs(4326).to_json(),
            name="Linhas",
            style_function=_ls_style,
        )
        gj.add_to(m)

    # Polígonos
    if "polygons" in gdfs_by_type and len(gdfs_by_type["polygons"]) > 0:
        def _pg_style(_):
            return {
                "color": style["poly_color"],
                "weight": style["weight"],
                "fillColor": style["poly_color"],
                "fillOpacity": style["opacity"],
            }

        poly_gdf = gdfs_by_type["polygons"].to_crs(4326).copy()
        poly_gdf["__popup__"] = poly_gdf.apply(_popup_html, axis=1)
        gj = GeoJson(
            data=poly_gdf.to_json(),
            name="Polígonos",
            style_function=_pg_style,
            tooltip=folium.GeoJsonTooltip(
                fields=["name"] if show_tooltips and "name" in poly_gdf.columns else None
            ),
        )
        if show_popups:
            gj.add_child(folium.features.GeoJsonPopup(fields=["__popup__"], labels=False))
        gj.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    return m


def build_pydeck_map(
    gdfs_by_type: Dict[str, gpd.GeoDataFrame],
    style: Dict,
    show_popups: bool,
    show_tooltips: bool,
):
    """Constrói o mapa com PyDeck (Deck.gl)."""
    import pydeck as pdk

    layers = []
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
        init_view = pdk.ViewState(latitude=center[0], longitude=center[1], zoom=11)
    else:
        init_view = pdk.ViewState(latitude=-3.73, longitude=-38.52, zoom=12)

    tooltip = (
        {"html": "<b>{name}</b><br/>{description}", "style": {"color": "black"}}
        if (show_popups or show_tooltips)
        else None
    )

    return pdk.Deck(layers=layers, initial_view_state=init_view, tooltip=tooltip)
