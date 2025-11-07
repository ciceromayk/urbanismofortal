from __future__ import annotations

import io
import json
from typing import Dict, Tuple

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, LineString, Polygon, MultiPolygon, MultiLineString, MultiPoint


def detect_crs_or_default(gdf: gpd.GeoDataFrame, forced: str | None) -> str:
    if forced:
        return forced
    if gdf.crs:
        return gdf.crs.to_string()
    # KML COSTUMA ESTAR EM WGS84
    return "EPSG:4326"


def reproject_if_needed(gdf: gpd.GeoDataFrame, target: str) -> gpd.GeoDataFrame:
    try:
        if not gdf.crs or gdf.crs.to_string() != target:
            return gdf.to_crs(target)
        return gdf
    except Exception:
        # SE FALHAR, MANTÉM ORIGINAL
        return gdf


def simplify_geometries(gdf: gpd.GeoDataFrame, tol: float) -> gpd.GeoDataFrame:
    if tol <= 0:
        return gdf
    gdf2 = gdf.copy()
    gdf2["geometry"] = gdf2["geometry"].simplify(tol, preserve_topology=True)
    return gdf2


def split_by_geom_type(gdf: gpd.GeoDataFrame) -> Dict[str, gpd.GeoDataFrame]:
    pts = gdf[gdf.geometry.geom_type.isin(["Point", "MultiPoint"])].copy()
    lns = gdf[gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])].copy()
    pgs = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()

    # NORMALIZA MULTIS EM SIMPLES PARA RENDERIZAÇÃO CONSISTENTE (OPCIONAL)
    # AQUI MANTEMOS COMO ESTÁ; FOLIUM/PYDECK LIDAM COM MULTIS VIA JSON.

    return {"points": pts, "lines": lns, "polygons": pgs}


def to_geojson_bytes(gdf: gpd.GeoDataFrame) -> bytes:
    gj = gdf.to_crs(4326).to_json()
    return gj.encode("utf-8")


def gdf_to_csv_bytes(gdf: gpd.GeoDataFrame) -> bytes:
    df = pd.DataFrame(gdf.drop(columns="geometry"))
    return df.to_csv(index=False).encode("utf-8")
