"""Camada de persistência do catálogo.

Backends:
- SupabaseBackend: usado quando SUPABASE_URL e SUPABASE_KEY estão em st.secrets ou no ambiente.
- CSVBackend: fallback local (data/lancamentos.csv). Não persiste em deploys efêmeros (ex.: Streamlit Cloud).
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

COLUMNS = [
    "id",
    "nome",
    "bairro",
    "construtora",
    "endereco",
    "latitude",
    "longitude",
    "unidades_total",
    "unidades_disponiveis",
    "area_media_m2",
    "preco_medio",
    "faixa_preco",
    "previsao_entrega",
    "descricao",
    "link_tabela_disponibilidade",
    "link_plantas",
    "link_imagens",
    "telefone_comercial",
    "disponibilidade_tipologia",
]

INT_COLUMNS = ["id", "unidades_total", "unidades_disponiveis"]
FLOAT_COLUMNS = ["latitude", "longitude", "area_media_m2", "preco_medio"]
TEXT_COLUMNS = [c for c in COLUMNS if c not in INT_COLUMNS + FLOAT_COLUMNS]

TABLE_NAME = "lancamentos"


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Garante colunas e tipos padronizados."""
    df = df.copy()
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = None
    for col in INT_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    for col in FLOAT_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in TEXT_COLUMNS:
        df[col] = df[col].fillna("").astype(str)
    return df[COLUMNS].reset_index(drop=True)


def _clean_record(record: dict[str, Any]) -> dict[str, Any]:
    """Converte NaN em None e tipos numpy em nativos (necessário para JSON/Supabase)."""
    out: dict[str, Any] = {}
    for key in COLUMNS:
        value = record.get(key)
        if hasattr(value, "item"):
            value = value.item()
        if isinstance(value, float) and math.isnan(value):
            value = None
        out[key] = value
    return out


class Backend(Protocol):
    name: str

    def load(self) -> pd.DataFrame: ...
    def insert(self, record: dict[str, Any]) -> None: ...
    def update(self, record_id: int, record: dict[str, Any]) -> None: ...
    def delete(self, record_id: int) -> None: ...
    def replace_all(self, df: pd.DataFrame) -> None: ...


class CSVBackend:
    name = "CSV local"

    def __init__(self, path: Path = Path("data") / "lancamentos.csv") -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            pd.DataFrame(columns=COLUMNS).to_csv(self.path, index=False)

    def load(self) -> pd.DataFrame:
        return normalize(pd.read_csv(self.path, dtype=str, keep_default_na=False))

    def _write(self, df: pd.DataFrame) -> None:
        normalize(df).to_csv(self.path, index=False)

    def insert(self, record: dict[str, Any]) -> None:
        df = self.load()
        self._write(pd.concat([df, pd.DataFrame([_clean_record(record)])], ignore_index=True))

    def update(self, record_id: int, record: dict[str, Any]) -> None:
        df = self.load()
        mask = df["id"] == int(record_id)
        if not mask.any():
            raise KeyError(f"Lançamento {record_id} não encontrado")
        clean = _clean_record({**record, "id": int(record_id)})
        idx = df.index[mask][0]
        for key, value in clean.items():
            df.at[idx, key] = value
        self._write(df)

    def delete(self, record_id: int) -> None:
        df = self.load()
        self._write(df[df["id"] != int(record_id)])

    def replace_all(self, df: pd.DataFrame) -> None:
        self._write(df)


class SupabaseBackend:
    name = "Supabase"

    def __init__(self, url: str, key: str) -> None:
        from supabase import create_client

        self.client = create_client(url, key)

    def load(self) -> pd.DataFrame:
        res = self.client.table(TABLE_NAME).select("*").order("id").execute()
        return normalize(pd.DataFrame(res.data or [], columns=COLUMNS))

    def insert(self, record: dict[str, Any]) -> None:
        payload = _clean_record(record)
        payload.pop("id", None)  # id gerado pelo banco (identity)
        self.client.table(TABLE_NAME).insert(payload).execute()

    def update(self, record_id: int, record: dict[str, Any]) -> None:
        payload = _clean_record(record)
        payload.pop("id", None)
        self.client.table(TABLE_NAME).update(payload).eq("id", int(record_id)).execute()

    def delete(self, record_id: int) -> None:
        self.client.table(TABLE_NAME).delete().eq("id", int(record_id)).execute()

    def replace_all(self, df: pd.DataFrame) -> None:
        rows = [_clean_record(r) for r in normalize(df).to_dict("records")]
        self.client.table(TABLE_NAME).delete().gte("id", 0).execute()
        if rows:
            for r in rows:
                r.pop("id", None)
            self.client.table(TABLE_NAME).insert(rows).execute()


def _get_setting(key: str) -> str | None:
    try:
        import streamlit as st

        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:  # noqa: BLE001 - secrets.toml ausente
        pass
    return os.getenv(key)


def get_backend() -> Backend:
    url, key = _get_setting("SUPABASE_URL"), _get_setting("SUPABASE_KEY")
    if url and key:
        return SupabaseBackend(url, key)
    return CSVBackend()
