from __future__ import annotations

import io
import json
from typing import Dict

import geopandas as gpd
import pandas as pd


# ============================================================
# CRS E REPROJEÇÃO
# ============================================================

def detect_crs_or_default(gdf: gpd.GeoDataFrame, forced: str | None) -> str:
    """Detecta o CRS do GeoDataFrame ou assume WGS84."""
    if forced:
        return forced
    if gdf.crs:
        return gdf.crs.to_string()
    return "EPSG:4326"


def reproject_if_needed(gdf: gpd.GeoDataFrame, target: str) -> gpd.GeoDataFrame:
    """Reprojeta o GeoDataFrame se necessário."""
    try:
        if not gdf.crs or gdf.crs.to_string() != target:
            return gdf.to_crs(target)
        return gdf
    except Exception:
        return gdf


# ============================================================
# SIMPLIFICAÇÃO E DIVISÃO POR TIPO DE GEOMETRIA
# ============================================================

def simplify_geometries(gdf: gpd.GeoDataFrame, tol: float) -> gpd.GeoDataFrame:
    """Simplifica as geometrias com a tolerância informada."""
    if tol <= 0:
        return gdf
    gdf2 = gdf.copy()
    gdf2["geometry"] = gdf2["geometry"].simplify(tol, preserve_topology=True)
    return gdf2


def split_by_geom_type(gdf: gpd.GeoDataFrame) -> Dict[str, gpd.GeoDataFrame]:
    """Separa GeoDataFrame em pontos, linhas e polígonos."""
    if gdf is None or gdf.empty:
        return {"points": gpd.GeoDataFrame(), "lines": gpd.GeoDataFrame(), "polygons": gpd.GeoDataFrame()}

    gdf = gdf[gdf.geometry.notnull()].copy()

    pts = gdf[gdf.geometry.geom_type.isin(["Point", "MultiPoint"])].copy()
    lns = gdf[gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])].copy()
    pgs = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()

    return {"points": pts, "lines": lns, "polygons": pgs}


# ============================================================
# EXPORTAÇÕES
# ============================================================

def to_geojson_bytes(gdf: gpd.GeoDataFrame) -> bytes:
    """Exporta o GeoDataFrame como GeoJSON (bytes)."""
    gj = gdf.to_crs(4326).to_json()
    return gj.encode("utf-8")


def gdf_to_csv_bytes(gdf: gpd.GeoDataFrame) -> bytes:
    """Exporta atributos (sem geometria) em CSV."""
    df = pd.DataFrame(gdf.drop(columns="geometry"))
    return df.to_csv(index=False).encode("utf-8")
