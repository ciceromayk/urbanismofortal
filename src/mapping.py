from __future__ import annotations

from typing import Dict

import geopandas as gpd


def _popup_html(row) -> str:
    # POPUP COM NOME, DESCRIÇÃO E DEMAIS ATRIBUTOS
    parts = []
    if "name" in row and row["name"]:
        parts.append(f"<b>Nome:</b> {row['name']}")
    if "description" in row and row["description"]:
        parts.append(f"<b>Descrição:</b> {row['description']}")
    for k, v in row.items():
        if k in ("name", "description", "geometry", "__layer__"):
            continue
        if v is not None and v != "":
            parts.append(f"<b>{k}:</b> {v}")
    return "<br>".join(parts) if parts else "<i>Sem atributos</i>"


def build_folium_map(gdfs_by_type: Dict[str, gpd.GeoDataFrame], style: Dict, show_popups: bool, show_tooltips: bool):
    import folium
    from folium import FeatureGroup, GeoJson, Popup, Tooltip
    from shapely.geometry import Point

    # EXTENT
    all_nonempty = [g for g in gdfs_by_type.values() if len(g) > 0]
    if all_nonempty:
        bounds = gpd.GeoDataFrame(pd.concat(all_nonempty), geometry="geometry", crs=all_nonempty[0].crs).to_crs(4326).total_bounds
        center = [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2]
        zoom_start = 11
    else:
        center = [-3.730451, -38.521798]  # FORTALEZA COMO DEFAULT
        zoom_start = 12

    m = folium.Map(location=center, zoom_start=zoom_start, control_scale=True, tiles="OpenStreetMap")

    # CAMADAS
    if "points" in gdfs_by_type and len(gdfs_by_type["points"]) > 0:
        fg = FeatureGroup(name="Pontos", show=True)
        for idx, row in gdfs_by_type["points"].to_crs(4326).iterrows():
            geom = row.geometry
            if isinstance(geom, Point):
                marker = folium.CircleMarker(
                    location=[geom.y, geom.x],
                    radius=6,
                    color=style["point_color"],
                    fill=True,
                    fill_color=style["point_color"],
                    fill_opacity=style["opacity"],
                    stroke=True,
                    weight=style["weight"],
                )
                if show_popups:
                    marker.add_child(Popup(_popup_html(row), max_width=350, parse_html=False))
                if show_tooltips and row.get("name"):
                    marker.add_child(Tooltip(str(row.get("name"))))
                marker.add_to(fg)
        fg.add_to(m)

    if "lines" in gdfs_by_type and len(gdfs_by_type["lines"]) > 0:
        def _ls_style(_):
            return {"color": style["line_color"], "weight": style["weight"], "opacity": style["opacity"]}

        gj = GeoJson(
            data=gdfs_by_type["lines"].to_crs(4326).to_json(),
            name="Linhas",
            style_function=_ls_style,
            tooltip=folium.GeoJsonTooltip(fields=["name"] if show_tooltips and "name" in gdfs_by_type["lines"].columns else None),
            popup=folium.GeoJsonPopup(fields=[], labels=False) if show_popups else None,
        )
        if show_popups:
            gj.add_child(folium.features.GeoJsonPopup(fields=[], labels=False))
            # POPUP POR FEATURE VIA HACK (BIND NA PROPRIEDADE 'popup')
            # MAS JÁ QUE CONVERTERMOS PARA JSON, PODEMOS SIMPLESMENTE NÃO BINDAR AQUI.
        gj.add_to(m)

    if "polygons" in gdfs_by_type and len(gdfs_by_type["polygons"]) > 0:
        def _pg_style(_):
            return {
                "color": style["poly_color"],
                "weight": style["weight"],
                "fillColor": style["poly_color"],
                "fillOpacity": style["opacity"],
            }

        # PARA POPUP RICO, USAREMOS customize via 'feature.properties'
        poly_gdf = gdfs_by_type["polygons"].to_crs(4326).copy()
        # EMBUTIR HTML DO POPUP COMO CAMPO
        poly_gdf["__popup__"] = poly_gdf.apply(_popup_html, axis=1)
        gj = GeoJson(
            data=poly_gdf.to_json(),
            name="Polígonos",
            style_function=_pg_style,
            tooltip=folium.GeoJsonTooltip(fields=["name"] if show_tooltips and "name" in poly_gdf.columns else None),
        )
        if show_popups:
            gj.add_child(folium.features.GeoJsonPopup(fields=["__popup__"], labels=False))
        gj.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    return m


def build_pydeck_map(gdfs_by_type: Dict[str, gpd.GeoDataFrame], style: Dict, show_popups: bool, show_tooltips: bool):
    import pydeck as pdk
    import pandas as pd
    import numpy as np

    layers = []

    # CENTRO / EXTENT
    all_nonempty = [g for g in gdfs_by_type.values() if len(g) > 0]
    if all_nonempty:
        bounds = gpd.GeoDataFrame(pd.concat(all_nonempty), geometry="geometry", crs=all_nonempty[0].crs).to_crs(4326).total_bounds
        center = [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2]
        init_view = pdk.ViewState(latitude=center[0], longitude=center[1], zoom=11)
    else:
        init_view = pdk.ViewState(latitude=-3.730451, longitude=-38.521798, zoom=12)

    if "polygons" in gdfs_by_type and len(gdfs_by_type["polygons"]) > 0:
        pg = gdfs_by_type["polygons"].to_crs(4326).copy()
        pg["coordinates"] = pg.geometry.apply(lambda geom: [list(map(list, ring.coords)) for ring in geom.exterior, *[i for i in []]] if geom.geom_type == "Polygon" else [list(map(list, poly.exterior.coords)) for poly in geom.geoms])
        # OBS: SHAPELY->DECK PRECISA DE LISTAS NÍVEIS; TRATAMENTO SIMPLIFICADO:
        def poly_coords(g):
            if g.geom_type == "Polygon":
                return [list(map(list, g.exterior.coords))]
            elif g.geom_type == "MultiPolygon":
                return [list(map(list, poly.exterior.coords)) for poly in g.geoms]
            return []
        pg["coordinates"] = pg.geometry.apply(poly_coords)
        layers.append(
            pdk.Layer(
                "PolygonLayer",
                data=pg,
                get_polygon="coordinates",
                get_fill_color=[20, 180, 90, int(255 * style["opacity"])],
                get_line_color=[20, 180, 90],
                stroked=True,
                extruded=False,
                pickable=True,
                get_line_width=style["weight"],
            )
        )

    if "lines" in gdfs_by_type and len(gdfs_by_type["lines"]) > 0:
        ln = gdfs_by_type["lines"].to_crs(4326).copy()
        def line_coords(g):
            if g.geom_type == "LineString":
                return list(map(list, g.coords))
            elif g.geom_type == "MultiLineString":
                # escolhe a primeira para visual rápido
                return list(map(list, list(ln.geometry.iloc[0].geoms)[0].coords)) if len(g.geoms) else []
            return []
        ln["path"] = ln.geometry.apply(line_coords)
        layers.append(
            pdk.Layer(
                "PathLayer",
                data=ln,
                get_path="path",
                get_width=style["weight"],
                get_color=[255, 127, 14],
                pickable=True,
            )
        )

    if "points" in gdfs_by_type and len(gdfs_by_type["points"]) > 0:
        pt = gdfs_by_type["points"].to_crs(4326).copy()
        pt["lon"] = pt.geometry.x
        pt["lat"] = pt.geometry.y
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=pt,
                get_position="[lon, lat]",
                get_radius=20,
                get_fill_color=[31, 119, 180],
                pickable=True,
            )
        )

    tooltip = {"html": "<b>{name}</b><br/>{description}", "style": {"backgroundColor": "white", "color": "black"}} if (show_popups or show_tooltips) else None

    return pdk.Deck(layers=layers, initial_view_state=init_view, tooltip=tooltip, map_style=None)
