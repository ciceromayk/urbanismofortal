from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

DATA_DIR = Path("data")
DATA_FILE = DATA_DIR / "lancamentos.csv"

COLUMNS = [
    "id",
    "nome",
    "bairro",
    "construtora",
    "endereco",
    "unidades_total",
    "unidades_disponiveis",
    "faixa_preco",
    "previsao_entrega",
    "descricao",
    "link_tabela_disponibilidade",
    "link_plantas",
    "link_imagens",
    "telefone_comercial",
    "disponibilidade_tipologia",
]


def ensure_storage() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        pd.DataFrame(columns=COLUMNS).to_csv(DATA_FILE, index=False)


def load_data() -> pd.DataFrame:
    ensure_storage()
    df = pd.read_csv(DATA_FILE)
    for col in ["unidades_total", "unidades_disponiveis"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    if "id" not in df.columns:
        df["id"] = range(1, len(df) + 1)
    return df


def save_data(df: pd.DataFrame) -> None:
    df = df.copy()
    df = df[COLUMNS]
    df.to_csv(DATA_FILE, index=False)


def parse_tipologias(text: str) -> list[dict[str, Any]]:
    if not text.strip():
        return []
    try:
        value = json.loads(text)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        return []
    except json.JSONDecodeError:
        return []


def render_overview(df: pd.DataFrame) -> None:
    st.subheader("Visão geral")
    c1, c2, c3 = st.columns(3)
    c1.metric("Lançamentos cadastrados", len(df))
    c2.metric("Unidades totais", int(df["unidades_total"].sum()))
    c3.metric("Unidades disponíveis", int(df["unidades_disponiveis"].sum()))


def render_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("Filtros")

    construtoras = ["Todas"] + sorted(df["construtora"].dropna().unique().tolist())
    bairros = ["Todos"] + sorted(df["bairro"].dropna().unique().tolist())

    construtora = st.sidebar.selectbox("Construtora", construtoras)
    bairro = st.sidebar.selectbox("Bairro", bairros)
    somente_com_disponibilidade = st.sidebar.checkbox("Somente com unidades disponíveis", value=True)

    filtrado = df.copy()
    if construtora != "Todas":
        filtrado = filtrado[filtrado["construtora"] == construtora]
    if bairro != "Todos":
        filtrado = filtrado[filtrado["bairro"] == bairro]
    if somente_com_disponibilidade:
        filtrado = filtrado[filtrado["unidades_disponiveis"] > 0]

    return filtrado


def render_catalog(df: pd.DataFrame) -> None:
    st.subheader("Catálogo")
    if df.empty:
        st.info("Nenhum lançamento corresponde aos filtros atuais.")
        return

    for _, row in df.sort_values(by="nome").iterrows():
        with st.expander(f"{row['nome']} • {row['bairro']} • {row['construtora']}"):
            st.markdown(f"**Endereço:** {row['endereco']}")
            st.markdown(f"**Previsão de entrega:** {row['previsao_entrega']}")
            st.markdown(f"**Faixa de preço:** {row['faixa_preco']}")
            st.markdown(
                f"**Unidades:** {int(row['unidades_disponiveis'])} disponíveis de {int(row['unidades_total'])}"
            )
            st.markdown(f"**Contato comercial:** {row['telefone_comercial']}")
            st.write(row["descricao"])

            cols = st.columns(3)
            cols[0].link_button("Tabela de disponibilidade", row["link_tabela_disponibilidade"])
            cols[1].link_button("Plantas", row["link_plantas"])
            cols[2].link_button("Imagens", row["link_imagens"])

            tipologias = parse_tipologias(str(row["disponibilidade_tipologia"]))
            if tipologias:
                st.caption("Disponibilidade por tipologia")
                st.dataframe(pd.DataFrame(tipologias), use_container_width=True)


def next_id(df: pd.DataFrame) -> int:
    if df.empty:
        return 1
    return int(df["id"].max()) + 1


def render_new_launch_form(df: pd.DataFrame) -> pd.DataFrame:
    st.subheader("Cadastrar lançamento")
    with st.form("novo_lancamento", clear_on_submit=True):
        nome = st.text_input("Nome do empreendimento*")
        bairro = st.text_input("Bairro*")
        construtora = st.text_input("Construtora*")
        endereco = st.text_input("Endereço")
        c1, c2 = st.columns(2)
        unidades_total = c1.number_input("Número total de unidades", min_value=0, value=0)
        unidades_disp = c2.number_input("Unidades disponíveis", min_value=0, value=0)
        faixa_preco = st.text_input("Faixa de preço (ex.: R$ 450 mil a R$ 650 mil)")
        previsao_entrega = st.text_input("Previsão de entrega")
        telefone = st.text_input("Telefone comercial")
        descricao = st.text_area("Descrição")
        link_tabela = st.text_input("URL da tabela de disponibilidade")
        link_plantas = st.text_input("URL das plantas")
        link_imagens = st.text_input("URL das imagens")
        tipologia_json = st.text_area(
            "Disponibilidade por tipologia (JSON)",
            value='[{"tipologia": "2 quartos", "metragem": "62 m²", "disponiveis": 12}]',
            help="Use uma lista JSON com objetos contendo tipologia, metragem e unidades disponíveis.",
        )

        submitted = st.form_submit_button("Salvar lançamento")
        if submitted:
            if not (nome and bairro and construtora):
                st.error("Preencha os campos obrigatórios: nome, bairro e construtora.")
                return df

            novo = {
                "id": next_id(df),
                "nome": nome,
                "bairro": bairro,
                "construtora": construtora,
                "endereco": endereco,
                "unidades_total": int(unidades_total),
                "unidades_disponiveis": int(unidades_disp),
                "faixa_preco": faixa_preco,
                "previsao_entrega": previsao_entrega,
                "descricao": descricao,
                "link_tabela_disponibilidade": link_tabela,
                "link_plantas": link_plantas,
                "link_imagens": link_imagens,
                "telefone_comercial": telefone,
                "disponibilidade_tipologia": json.dumps(parse_tipologias(tipologia_json), ensure_ascii=False),
            }
            atualizado = pd.concat([df, pd.DataFrame([novo])], ignore_index=True)
            save_data(atualizado)
            st.success("Lançamento salvo com sucesso!")
            return atualizado
    return df


def render_import_export(df: pd.DataFrame) -> pd.DataFrame:
    st.subheader("Importação e exportação")
    uploaded = st.file_uploader("Importar CSV de lançamentos", type=["csv"])
    if uploaded is not None:
        try:
            importado = pd.read_csv(uploaded)
            faltantes = [c for c in COLUMNS if c not in importado.columns]
            if faltantes:
                st.error(f"CSV inválido. Colunas ausentes: {', '.join(faltantes)}")
            else:
                importado = importado[COLUMNS]
                save_data(importado)
                st.success("CSV importado com sucesso.")
                df = importado
        except Exception as exc:  # noqa: BLE001
            st.error(f"Erro ao importar CSV: {exc}")

    csv_data = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Baixar catálogo (CSV)",
        data=csv_data,
        file_name="catalogo_lancamentos_fortaleza.csv",
        mime="text/csv",
    )
    return df


def main() -> None:
    st.set_page_config(page_title="Lançamentos Fortaleza", layout="wide")
    st.title("📍 Catálogo de Lançamentos Imobiliários — Fortaleza/CE")
    st.caption(
        "Centralize informações de unidades, disponibilidade, plantas, imagens e dados de construtora em um único painel."
    )

    df = load_data()

    render_overview(df)
    df_filtrado = render_filters(df)
    render_catalog(df_filtrado)

    st.divider()
    df = render_new_launch_form(df)
    st.divider()
    render_import_export(df)


if __name__ == "__main__":
    main()
