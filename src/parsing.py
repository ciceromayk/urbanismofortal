from __future__ import annotations

import io
import zipfile
from typing import Dict, Iterable, List, Optional, Tuple, Any

import geopandas as gpd
import pandas as pd
from shapely.geometry import shape, Point, LineString, Polygon, MultiPolygon, MultiLineString, MultiPoint
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from fastkml import kml


def _iter_placemarks(feature) -> Iterable:
    """Percorre recursivamente `Document`/`Folder`/`Placemark`."""
    if hasattr(feature, "features"):
        for f in feature.features():
            yield from _iter_placemarks(f)
    else:
        # Placemark
        yield feature


def _geom_from_fastkml(geom_obj) -> Optional[BaseGeometry]:
    """Converte geometria do fastkml (geojson-like) para shapely."""
    if geom_obj is None:
        return None
    try:
        # fastkml já expõe .geometry em formato geo-interface
        return shape(geom_obj)
    except Exception:
        return None


def _extract_extdata(pm) -> dict:
    """Extrai ExtendedData (se houver) e normaliza em dict plano."""
    data = {}
    try:
        if hasattr(pm, "extended_data") and pm.extended_data:
            # fastkml: extended_data == {name: value} ou data[]
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
    """Retorna lista (nome_arquivo, bytes) dos KMLs dentro do KMZ."""
    out = []
    with zipfile.ZipFile(io.BytesIO(kmz_bytes)) as z:
        for name in z.namelist():
            if name.lower().endswith(".kml"):
                out.append((name, z.read(name)))
    return out


def parse_kml_bytes(kml_bytes: bytes, layer_hint: Optional[str] = None) -> gpd.GeoDataFrame:
    """Lê bytes de KML e retorna GeoDataFrame com atributos normalizados."""
    k = kml.KML()
    k.from_string(kml_bytes)

    rows = []
    layer_stack = []

    def _walk(feat, layer_path: List[str]):
        if hasattr(feat, "name") and getattr(feat, "features", None):
            # Document/Folder
            new_path = layer_path + [feat.name] if feat.name else layer_path
            for f in feat.features():
                _walk(f, new_path)
        else:
            # Placemark
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

    # Nível raiz pode ter múltiplos Documents
    for f in k.features():
        _walk(f, [])

    if not rows:
        return gpd.GeoDataFrame(columns=["__layer__", "name", "description", "geometry"], geometry="geometry", crs=None)

    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=None)
    return gdf


def parse_kmz_or_kml(file_bytes: bytes, filename: str) -> Tuple[gpd.GeoDataFrame, Dict[str, gpd.GeoDataFrame]]:
    """
    Lê .kmz (descompacta e concatena todos os KMLs) ou .kml.
    Retorna:
      - GeoDataFrame único com coluna __layer__ (folder path / nome do arquivo)
      - Dict opcional de GDFs por arquivo/camada (informativo)
    """
    layers: Dict[str, gpd.GeoDataFrame] = {}

    if filename.lower().endswith(".kmz"):
        kmls = _locate_kml_in_kmz(file_bytes)
        if not kmls:
            raise ValueError("KMZ SEM KML INTERNO.")
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
        raise ValueError("EXTENSÃO NÃO SUPORTADA (USE .KMZ OU .KML).")

    # LIMPEZA BÁSICA (FIX GEOMETRIES)
    gdf_all = gdf_all.dropna(subset=["geometry"]).copy()
    # CORRIGIR GEOMETRIAS INVÁLIDAS (BUFFER(0) QUANDO POSSÍVEL)
    gdf_all["geometry"] = gdf_all["geometry"].apply(lambda g: g.buffer(0) if g and not g.is_valid else g)

    return gdf_all, layers
