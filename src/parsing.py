# src/parsing.py
from __future__ import annotations

import io
import zipfile
from typing import Dict, Iterable, List, Optional, Tuple, Any

import geopandas as gpd
import pandas as pd
from shapely.geometry import shape, Point, LineString, Polygon, MultiPolygon, MultiLineString, MultiPoint
from shapely.geometry.base import BaseGeometry

# --- IMPORT ROBUSTO DO FASTKML ---
HAVE_FASTKML = True
FASTKML_IMPORT_ERROR: Optional[BaseException] = None
try:
    from fastkml import kml as fastkml_mod
except BaseException as e:
    HAVE_FASTKML = False
    FASTKML_IMPORT_ERROR = e

# (OPCIONAL) IMPORTS PARA FALLBACK
from shapely.ops import unary_union

def _fail_fastkml_message() -> str:
    base = "DEPENDÊNCIA 'fastkml' NÃO ENCONTRADA OU FALHOU AO IMPORTAR."
    if FASTKML_IMPORT_ERROR:
        base += f" DETALHES: {type(FASTKML_IMPORT_ERROR).__name__}: {FASTKML_IMPORT_ERROR}"
    base += " → SOLUÇÃO: execute 'pip install fastkml==0.12 lxml>=4.9,<6' e faça redeploy."
    return base

def _iter_placemarks(feature) -> Iterable:
    if hasattr(feature, "features"):
        for f in feature.features():
            yield from _iter_placemarks(f)
    else:
        yield feature

def _geom_from_fastkml(geom_obj) -> Optional[BaseGeometry]:
    if geom_obj is None:
        return None
    try:
        return shape(geom_obj)
    except Exception:
        return None

def _extract_extdata(pm) -> dict:
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
    out = []
    with zipfile.ZipFile(io.BytesIO(kmz_bytes)) as z:
        for name in z.namelist():
            if name.lower().endswith(".kml"):
                out.append((name, z.read(name)))
    return out

def parse_kml_bytes(kml_bytes: bytes, layer_hint: Optional[str] = None) -> gpd.GeoDataFrame:
    """
    PREFERENCIAL: FASTKML. FALLBACK: TENTA OGR (SE DISPONÍVEL NO AMBIENTE).
    """
    if HAVE_FASTKML:
        k = fastkml_mod.KML()
        k.from_string(kml_bytes)

        rows = []
        def _walk(feat, path: List[str]):
            if hasattr(feat, "name") and getattr(feat, "features", None):
                new_path = path + [feat.name] if feat.name else path
                for f in feat.features():
                    _walk(f, new_path)
            else:
                pm = feat
                geom = _geom_from_fastkml(getattr(pm, "geometry", None))
                if geom is None:
                    return
                rows.append({
                    "__layer__": " / ".join(path) if path else (layer_hint or ""),
                    "name": getattr(pm, "name", None),
                    "description": getattr(pm, "description", None),
                    **_extract_extdata(pm),
                    "geometry": geom,
                })

        for f in k.features():
            _walk(f, [])

        if not rows:
            return gpd.GeoDataFrame(columns=["__layer__", "name", "description", "geometry"],
                                    geometry="geometry", crs=None)
        return gpd.GeoDataFrame(rows, geometry="geometry", crs=None)

    # --- FALLBACK: TENTAR OGR VIA GEOPANDAS/FIONA (SE LIBKML DISPONÍVEL) ---
    try:
        # ALGUNS AMBIENTES DO CLOUD PODEM TER DRIVER KML HABILITADO
        # OBS: O OGR LÊ CAMADAS COMO "OGRGeoJSON"/"KML". TENTAMOS O PADRÃO.
        from tempfile import NamedTemporaryFile
        with NamedTemporaryFile(suffix=".kml") as tmp:
            tmp.write(kml_bytes)
            tmp.flush()
            gdf = gpd.read_file(tmp.name)
            gdf["__layer__"] = layer_hint or ""
            return gdf
    except Exception:
        raise ImportError(_fail_fastkml_message())

def parse_kmz_or_kml(file_bytes: bytes, filename: str):
    if filename.lower().endswith(".kmz"):
        kmls = _locate_kml_in_kmz(file_bytes)
        if not kmls:
            raise ValueError("KMZ SEM KML INTERNO.")
        frames = []
        layers: Dict[str, gpd.GeoDataFrame] = {}
        for kml_name, kml_bytes in kmls:
            gdf = parse_kml_bytes(kml_bytes, layer_hint=kml_name)
            layers[kml_name] = gdf
            frames.append(gdf)
        gdf_all = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), geometry="geometry")
    elif filename.lower().endswith(".kml"):
        gdf_all = parse_kml_bytes(file_bytes, layer_hint=filename)
        layers = {filename: gdf_all}
    else:
        raise ValueError("EXTENSÃO NÃO SUPORTADA (USE .KMZ OU .KML).")

    gdf_all = gdf_all.dropna(subset=["geometry"]).copy()
    gdf_all["geometry"] = gdf_all["geometry"].apply(lambda g: g.buffer(0) if g and not g.is_valid else g)
    return gdf_all, layers
