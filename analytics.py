"""Indicadores de mercado calculados a partir do catálogo."""

from __future__ import annotations

import pandas as pd


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Adiciona preço/m², unidades vendidas e VSO acumulado por lançamento."""
    out = df.copy()
    area = out["area_media_m2"].where(out["area_media_m2"] > 0)
    preco = out["preco_medio"].where(out["preco_medio"] > 0)
    out["preco_m2"] = preco / area
    out["unidades_vendidas"] = (out["unidades_total"] - out["unidades_disponiveis"]).clip(lower=0)
    total = out["unidades_total"].where(out["unidades_total"] > 0)
    out["vso_pct"] = out["unidades_vendidas"] / total * 100
    out["vgv_estoque"] = out["unidades_disponiveis"] * preco
    return out


def by_bairro(df: pd.DataFrame) -> pd.DataFrame:
    """Oferta e preço por bairro. Preço/m² ponderado pela oferta total de unidades."""
    e = enrich(df)
    e["_peso"] = e["unidades_total"].where(e["preco_m2"].notna(), 0)
    e["_pm2_x_peso"] = e["preco_m2"].fillna(0) * e["_peso"]
    g = e.groupby("bairro", dropna=False).agg(
        lancamentos=("id", "count"),
        unidades_total=("unidades_total", "sum"),
        unidades_disponiveis=("unidades_disponiveis", "sum"),
        unidades_vendidas=("unidades_vendidas", "sum"),
        _peso=("_peso", "sum"),
        _pm2=("_pm2_x_peso", "sum"),
        vgv_estoque=("vgv_estoque", "sum"),
    )
    g["preco_m2_medio"] = (g["_pm2"] / g["_peso"]).where(g["_peso"] > 0)
    g["vso_pct"] = (g["unidades_vendidas"] / g["unidades_total"] * 100).where(g["unidades_total"] > 0)
    g = g.drop(columns=["_peso", "_pm2"]).reset_index()
    return g.sort_values("unidades_disponiveis", ascending=False)


def price_color(value: float | None, low: float, high: float) -> str:
    """Cor do marcador pelo preço/m² (verde = barato, vermelho = caro, cinza = sem dado)."""
    if value is None or pd.isna(value) or high <= low:
        return "gray" if value is None or pd.isna(value) else "orange"
    pos = (value - low) / (high - low)
    if pos < 0.33:
        return "green"
    if pos < 0.66:
        return "orange"
    return "red"
