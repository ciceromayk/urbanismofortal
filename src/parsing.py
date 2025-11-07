from __future__ import annotations

import io
import zipfile
from typing import Dict, Iterable, List, Optional, Tuple, Any

import geopandas as gpd
import pandas as pd
from shapely.geometry import shape, Point, LineString, Polygon, MultiPolygon, MultiLineString, MultiPoint
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

# ============================================================
# IMPORTAÇÃO SEGURA DO FASTKML
# ============================================================
try:
    from fastkml import kml
except ImportError as e:
    raise ImportError(
        "⚠️ A biblioteca 'fastkml' não está instalada. "
        "Adicione 'fastkml==0.12' ao seu requirements.txt e redeploy no Streamlit Cloud."
    ) from e


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def _iter_placemarks(feature) -> Iterable:
    """Percorre recursivamente todos os Placemarks (Documents, Folders, etc)."""
    if hasattr(feature, "features"):
        feats = feature.features() if callable(feature.features) else feature.features
        for f in feats:
            yield from _iter_placemarks(f)
    else:
        yield feature


def _geom_from_fastkml(geom_obj) -> Optional[BaseGeometry]:
    """Converte geometria do fastkml (geojson-like) para shapely."""
    if geom_obj is None:
        return None
    try:
        return shape(geom_obj)
    except Exception:
        return None


def _extract_extdata(pm) -> dict:
    """Extrai ExtendedData (quando disponível) e normaliza em dict plano."""
    data = {}
    try:
        if hasattr(pm, "extended_data") and pm.extended_data:
            ed = pm.extended_data.elements if hasattr(pm.extended_data, "elements") else pm.extended_data
            if isinstance(ed, list):
                for el in ed:
                    if hasattr(el, "name") and hasattr(el, "value"):
                        data[str(el.name)] = el.value
                    elif hasattr(el, "data"):
                        for d in el.data:
                            data[str(d.name)] = d.value
            elif isinstance(ed, dict):
                for k, v in ed.items():
                    data[str(k)] = v
    except Exception:
        pass
    return data


def _locate_kml_in_kmz(kmz_bytes: bytes) -> List[Tuple[str, bytes]]:
    """Descompacta um arquivo KMZ e retorna todos os KMLs internos."""
    out = []
    with zipfile.ZipFile(io.BytesIO(kmz_bytes)) as z:
        for name in z.namelist():
            if name.lower().endswith(".kml"):
                out.append((name, z.read(name)))
    return out


# ============================================================
# PARSE DE KML
# ============================================================

def parse_kml_bytes(kml_bytes: bytes, layer_hint: Optional[str] = None) -> gpd.GeoDataFrame:
    """Lê bytes de um KML e retorna um GeoDataFrame com atributos e geometria."""
    k = kml.KML()
    k.from_string(kml_bytes)

    rows = []

    def _walk(feat, layer_path: List[str]):
        """Percorre recursivamente os nodes do KML."""
        if hasattr(feat, "features") and getattr(feat, "features"):
            new_path = layer_path + [feat.name] if getattr(feat, "name", None) else layer_path
            feats = feat.features() if callable(feat.features) else feat.features
            for f in feats:
                _walk(f, new_path)
        else:
            pm = feat
            geom = _geom_from_fastkml(getattr(pm, "geometry", None))
            if geom is None:
                return
            name = getattr(pm, "name", None)
            desc = getattr(pm, "description", None)
            ext = _extract_extdata(pm)
            rows.append(
                {
                    "__layer__": " / ".join(layer_path) if layer_path else (layer_hint or ""),
                    "name": name,
                    "description": desc,
                    **ext,
                    "geometry": geom,
                }
            )

    # Corrige o acesso à raiz (lista ou função)
    feats_root = k.features() if callable(k.features) else k.features
    for f in feats_root:
        _walk(f, [])

    if not rows:
        return gpd.GeoDataFrame(
            columns=["__layer__", "name", "description", "geometry"],
            geometry="geometry",
            crs=None,
        )

    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=None)
    return gdf


# ============================================================
# PARSE DE KMZ (AGRUPA MÚLTIPLOS KMLs)
# ============================================================

def parse_kmz_or_kml(file_bytes: bytes, filename: str) -> Tuple[gpd.GeoDataFrame, Dict[str, gpd.GeoDataFrame]]:
    """
    Lê um arquivo .kmz (descompactando internamente) ou .kml,
    retornando:
      - GeoDataFrame consolidado (todas as camadas)
      - Dicionário com GeoDataFrames por camada
    """
    layers: Dict[str, gpd.GeoDataFrame] = {}

    if filename.lower().endswith(".kmz"):
        kmls = _locate_kml_in_kmz(file_bytes)
        if not kmls:
            raise ValueError("O KMZ não contém nenhum KML interno válido.")

        gdfs = []
        for kml_name, kml_bytes in kmls:
            gdf = parse_kml_bytes(kml_bytes, layer_hint=kml_name)
            layers[kml_name] = gdf
            gdfs.append(gdf)

        gdf_all = gpd.GeoDataFrame(pd.concat(gdfs, ignore_index=True), geometry="geometry")

    elif filename.lower().endswith(".kml"):
        gdf_all = parse_kml_bytes(file_bytes, layer_hint=filename)
        layers[filename] = gdf_all

    else:
        raise ValueError("Formato não suportado. Use arquivos .KMZ ou .KML.")

    # Remove linhas sem geometria e corrige geometrias inválidas
    gdf_all = gdf_all.dropna(subset=["geometry"]).copy()
    gdf_all["geometry"] = gdf_all["geometry"].apply(lambda g: g.buffer(0) if g and not g.is_valid else g)

    # --- Normaliza tipos de geometria (explode GeometryCollection) ---
    gdf_all = gdf_all.explode(ignore_index=True)
    gdf_all = gdf_all[gdf_all.geometry.notnull()].copy()

    # --- Filtra apenas geometrias suportadas ---
    gdf_all = gdf_all[gdf_all.geometry.geom_type.isin(
        ["Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon"]
    )].copy()

    return gdf_all, layers
