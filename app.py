from __future__ import annotations

import hmac
import json
import os
from typing import Any

import altair as alt
import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from analytics import by_bairro, enrich, price_color
from storage import COLUMNS, Backend, get_backend, normalize

FORTALEZA_CENTER = (-3.7319, -38.5267)


# --------------------------------------------------------------------------- utilidades


def brl(value: float | None, decimals: int = 2) -> str:
    if value is None or pd.isna(value):
        return "N/D"
    txt = f"{float(value):,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {txt}"


def num(value: float | None, decimals: int = 0) -> str:
    if value is None or pd.isna(value):
        return "N/D"
    return f"{float(value):,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct_abs(part: float, total: float) -> str:
    """Percentual sempre acompanhado do número absoluto."""
    if not total:
        return f"{num(part)} (N/D)"
    return f"{num(part)} de {num(total)} ({num(part / total * 100, 1)}%)"


def parse_tipologias(text: str) -> list[dict[str, Any]]:
    if not str(text).strip():
        return []
    try:
        value = json.loads(text)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    except json.JSONDecodeError:
        pass
    return []


def setting(key: str) -> str | None:
    try:
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:  # noqa: BLE001
        pass
    return os.getenv(key)


# --------------------------------------------------------------------------- dados


@st.cache_resource
def backend() -> Backend:
    return get_backend()


@st.cache_data(ttl=60, show_spinner=False)
def load_data(_backend_name: str) -> pd.DataFrame:
    return backend().load()


def refresh() -> None:
    load_data.clear()


# --------------------------------------------------------------------------- acesso ADM


def check_admin_login(username: str, password: str) -> bool:
    expected_user = setting("ADM_USERNAME") or "admin"
    expected_pwd = setting("ADM_PASSWORD")
    if not expected_pwd:
        return False
    return hmac.compare_digest(username, expected_user) and hmac.compare_digest(password, expected_pwd)


def render_admin_access() -> bool:
    st.sidebar.subheader("Acesso ADM")
    st.session_state.setdefault("is_admin", False)

    if not setting("ADM_PASSWORD"):
        st.sidebar.warning("ADM desativado: defina ADM_PASSWORD em secrets ou variável de ambiente.")
        return False

    if st.session_state.is_admin:
        st.sidebar.success("Sessão ADM ativa")
        if st.sidebar.button("Sair do modo ADM"):
            st.session_state.is_admin = False
            st.rerun()
        return True

    with st.sidebar.form("admin_login"):
        user = st.text_input("Usuário")
        pwd = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar como ADM"):
            if check_admin_login(user, pwd):
                st.session_state.is_admin = True
                st.rerun()
            else:
                st.error("Credenciais inválidas")
    return False


# --------------------------------------------------------------------------- visão pública


def render_overview(df: pd.DataFrame) -> None:
    e = enrich(df)
    total = int(e["unidades_total"].sum())
    disp = int(e["unidades_disponiveis"].sum())
    vend = int(e["unidades_vendidas"].sum())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Lançamentos", len(df))
    c2.metric("Unidades totais", num(total))
    c3.metric("Disponíveis", num(disp), help=pct_abs(disp, total))
    c4.metric("Vendidas (VSO acumulado)", f"{num(vend / total * 100, 1)}%" if total else "N/D", help=pct_abs(vend, total))


def render_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("Filtros")
    construtoras = ["Todas"] + sorted(x for x in df["construtora"].unique() if x)
    bairros = ["Todos"] + sorted(x for x in df["bairro"].unique() if x)

    construtora = st.sidebar.selectbox("Construtora", construtoras)
    bairro = st.sidebar.selectbox("Bairro", bairros)
    somente_disp = st.sidebar.checkbox("Somente com unidades disponíveis", value=True)

    f = df
    if construtora != "Todas":
        f = f[f["construtora"] == construtora]
    if bairro != "Todos":
        f = f[f["bairro"] == bairro]
    if somente_disp:
        f = f[f["unidades_disponiveis"] > 0]
    return f


def build_map(df: pd.DataFrame, color_by_price: bool = False) -> folium.Map:
    e = enrich(df).dropna(subset=["latitude", "longitude"])
    center = FORTALEZA_CENTER
    if not e.empty:
        center = (float(e["latitude"].mean()), float(e["longitude"].mean()))
    fmap = folium.Map(location=center, zoom_start=12, tiles="OpenStreetMap")

    pm2 = e["preco_m2"].dropna()
    low, high = (float(pm2.min()), float(pm2.max())) if not pm2.empty else (0.0, 0.0)

    for _, row in e.iterrows():
        area = "N/D" if pd.isna(row["area_media_m2"]) or not row["area_media_m2"] else f"{num(row['area_media_m2'], 1)} m²"
        popup = (
            f"<b>{row['nome']}</b><br>Bairro: {row['bairro']}<br>Construtora: {row['construtora']}<br>"
            f"Área média: {area}<br>Preço médio: {brl(row['preco_medio'] or None)}<br>"
            f"R$/m²: {brl(row['preco_m2'], 0)}<br>"
            f"Disponíveis: {int(row['unidades_disponiveis'])} de {int(row['unidades_total'])}"
        )
        color = price_color(row["preco_m2"], low, high) if color_by_price else "red"
        folium.Marker(
            location=[float(row["latitude"]), float(row["longitude"])],
            popup=folium.Popup(popup, max_width=280),
            tooltip=f"{row['nome']} | {row['construtora']} | R$/m²: {brl(row['preco_m2'], 0)}",
            icon=folium.Icon(color=color, icon="map-pin", prefix="fa"),
        ).add_to(fmap)
    return fmap


def render_catalog(df: pd.DataFrame) -> None:
    st.subheader("Catálogo")
    if df.empty:
        st.info("Nenhum lançamento corresponde aos filtros atuais.")
        return

    for _, row in enrich(df).sort_values(by="nome").iterrows():
        with st.expander(f"{row['nome']} • {row['bairro']} • {row['construtora']}"):
            c1, c2 = st.columns(2)
            c1.markdown(f"**Endereço:** {row['endereco'] or 'N/D'}")
            c1.markdown(f"**Previsão de entrega:** {row['previsao_entrega'] or 'N/D'}")
            c1.markdown(f"**Faixa de preço:** {row['faixa_preco'] or 'N/D'}")
            c1.markdown(f"**Contato comercial:** {row['telefone_comercial'] or 'N/D'}")
            c2.markdown(f"**Unidades disponíveis:** {pct_abs(row['unidades_disponiveis'], row['unidades_total'])}")
            c2.markdown(f"**Área média:** {num(row['area_media_m2'], 1)} m²")
            c2.markdown(f"**Preço médio:** {brl(row['preco_medio'] or None)}")
            c2.markdown(f"**Preço/m²:** {brl(row['preco_m2'], 0)}")
            if row["descricao"]:
                st.write(row["descricao"])

            cols = st.columns(3)
            for col, label, field in zip(
                cols,
                ["Tabela de disponibilidade", "Plantas", "Imagens"],
                ["link_tabela_disponibilidade", "link_plantas", "link_imagens"],
            ):
                url = str(row[field] or "").strip()
                if url.startswith(("http://", "https://")):
                    col.link_button(label, url, width="stretch")
                else:
                    col.button(label, disabled=True, width="stretch", key=f"nolink_{row['id']}_{field}")

            tipologias = parse_tipologias(row["disponibilidade_tipologia"])
            if tipologias:
                st.caption("Disponibilidade por tipologia")
                st.dataframe(pd.DataFrame(tipologias), width="stretch", hide_index=True)


# --------------------------------------------------------------------------- análise de mercado


def render_market(df: pd.DataFrame) -> None:
    st.subheader("Análise de mercado")
    st.caption(
        "Estimativas calculadas a partir dos dados cadastrados (preço médio ÷ área média). "
        "VSO aqui é acumulado desde o lançamento. Exigem conferência com tabelas oficiais das construtoras."
    )
    if df.empty:
        st.info("Sem dados para os filtros atuais.")
        return

    e = enrich(df)
    pm2 = e["preco_m2"].dropna()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("R$/m² mediano", brl(pm2.median(), 0) if not pm2.empty else "N/D")
    c2.metric("R$/m² mín – máx", f"{brl(pm2.min(), 0)} – {brl(pm2.max(), 0)}" if not pm2.empty else "N/D")
    c3.metric("VGV em estoque (estim.)", brl(e["vgv_estoque"].sum(), 0))
    c4.metric("Lançamentos com R$/m²", pct_abs(len(pm2), len(e)))

    st.markdown("##### Mapa por preço/m²")
    st.caption("🟢 terço mais barato · 🟠 intermediário · 🔴 terço mais caro · ⚪ sem dado")
    st_folium(build_map(df, color_by_price=True), use_container_width=True, height=400, key="market_map")

    st.markdown("##### Oferta por bairro")
    b = by_bairro(df)
    chart_df = b.melt(
        id_vars="bairro", value_vars=["unidades_disponiveis", "unidades_vendidas"], var_name="status", value_name="unidades"
    )
    chart_df["status"] = chart_df["status"].map({"unidades_disponiveis": "Disponíveis", "unidades_vendidas": "Vendidas"})
    st.altair_chart(
        alt.Chart(chart_df)
        .mark_bar()
        .encode(
            y=alt.Y("bairro:N", sort="-x", title=None),
            x=alt.X("unidades:Q", title="Unidades"),
            color=alt.Color("status:N", title=None),
            tooltip=["bairro", "status", "unidades"],
        ),
        width="stretch",
    )

    tabela = b.rename(
        columns={
            "bairro": "Bairro",
            "lancamentos": "Lançamentos",
            "unidades_total": "Unid. totais",
            "unidades_disponiveis": "Disponíveis",
            "unidades_vendidas": "Vendidas",
            "preco_m2_medio": "R$/m² médio (pond.)",
            "vso_pct": "VSO %",
            "vgv_estoque": "VGV estoque (R$)",
        }
    )
    st.dataframe(
        tabela,
        width="stretch",
        hide_index=True,
        column_config={
            "R$/m² médio (pond.)": st.column_config.NumberColumn(format="R$ %.0f"),
            "VSO %": st.column_config.NumberColumn(format="%.1f%%"),
            "VGV estoque (R$)": st.column_config.NumberColumn(format="R$ %.0f"),
        },
    )

    sc = e.dropna(subset=["preco_m2"])
    if not sc.empty:
        st.markdown("##### Área média × preço/m²")
        st.altair_chart(
            alt.Chart(sc)
            .mark_circle(opacity=0.8)
            .encode(
                x=alt.X("area_media_m2:Q", title="Área média (m²)"),
                y=alt.Y("preco_m2:Q", title="R$/m²"),
                size=alt.Size("unidades_total:Q", title="Unid. totais"),
                color=alt.Color("bairro:N", title="Bairro"),
                tooltip=["nome", "construtora", "bairro", "area_media_m2", alt.Tooltip("preco_m2:Q", format=",.0f"), "vso_pct"],
            ),
            width="stretch",
        )


# --------------------------------------------------------------------------- ADM


def launch_form_fields(prefix: str, rec: dict[str, Any], lat: float, lon: float) -> dict[str, Any]:
    """Campos comuns aos formulários de cadastro e edição (deve ser chamado dentro de st.form)."""
    k = lambda name: f"{prefix}_{name}"  # noqa: E731
    out: dict[str, Any] = {}
    out["nome"] = st.text_input("Nome do empreendimento*", rec.get("nome", ""), key=k("nome"))
    c0a, c0b = st.columns(2)
    out["bairro"] = c0a.text_input("Bairro*", rec.get("bairro", ""), key=k("bairro"))
    out["construtora"] = c0b.text_input("Construtora*", rec.get("construtora", ""), key=k("construtora"))
    out["endereco"] = st.text_input("Endereço", rec.get("endereco", ""), key=k("endereco"))
    g1, g2 = st.columns(2)
    out["latitude"] = g1.number_input("Latitude*", value=float(lat), format="%.6f", key=k("lat"))
    out["longitude"] = g2.number_input("Longitude*", value=float(lon), format="%.6f", key=k("lon"))
    c1, c2 = st.columns(2)
    out["unidades_total"] = c1.number_input("Total de unidades", min_value=0, value=int(rec.get("unidades_total", 0) or 0), key=k("ut"))
    out["unidades_disponiveis"] = c2.number_input(
        "Unidades disponíveis", min_value=0, value=int(rec.get("unidades_disponiveis", 0) or 0), key=k("ud")
    )
    c3, c4 = st.columns(2)
    area = rec.get("area_media_m2")
    preco = rec.get("preco_medio")
    out["area_media_m2"] = c3.number_input(
        "Área média (m²)", min_value=0.0, value=0.0 if area is None or pd.isna(area) else float(area), format="%.2f", key=k("area")
    )
    out["preco_medio"] = c4.number_input(
        "Preço médio (R$)", min_value=0.0, value=0.0 if preco is None or pd.isna(preco) else float(preco), format="%.2f", key=k("preco")
    )
    out["faixa_preco"] = st.text_input("Faixa de preço (ex.: R$ 450 mil a R$ 650 mil)", rec.get("faixa_preco", ""), key=k("faixa"))
    c5, c6 = st.columns(2)
    out["previsao_entrega"] = c5.text_input("Previsão de entrega", rec.get("previsao_entrega", ""), key=k("entrega"))
    out["telefone_comercial"] = c6.text_input("Telefone comercial", rec.get("telefone_comercial", ""), key=k("tel"))
    out["descricao"] = st.text_area("Descrição", rec.get("descricao", ""), key=k("desc"))
    out["link_tabela_disponibilidade"] = st.text_input(
        "URL da tabela de disponibilidade", rec.get("link_tabela_disponibilidade", ""), key=k("l1")
    )
    out["link_plantas"] = st.text_input("URL das plantas", rec.get("link_plantas", ""), key=k("l2"))
    out["link_imagens"] = st.text_input("URL das imagens", rec.get("link_imagens", ""), key=k("l3"))
    out["disponibilidade_tipologia"] = st.text_area(
        "Disponibilidade por tipologia (JSON)",
        rec.get("disponibilidade_tipologia") or '[{"tipologia": "2 quartos", "metragem": "62 m²", "disponiveis": 12}]',
        help="Lista JSON de objetos: tipologia, metragem, disponiveis.",
        key=k("tip"),
    )
    return out


def validate(data: dict[str, Any]) -> list[str]:
    erros = []
    if not (data["nome"].strip() and data["bairro"].strip() and data["construtora"].strip()):
        erros.append("Preencha os campos obrigatórios: nome, bairro e construtora.")
    if data["unidades_disponiveis"] > data["unidades_total"]:
        erros.append(
            f"Unidades disponíveis ({data['unidades_disponiveis']}) maiores que o total ({data['unidades_total']})."
        )
    tip = data["disponibilidade_tipologia"].strip()
    if tip and not parse_tipologias(tip):
        erros.append("JSON de tipologias inválido (esperada uma lista de objetos).")
    return erros


def finalize(data: dict[str, Any]) -> dict[str, Any]:
    data = {k: v.strip() if isinstance(v, str) else v for k, v in data.items()}
    data["area_media_m2"] = data["area_media_m2"] or None
    data["preco_medio"] = data["preco_medio"] or None
    data["disponibilidade_tipologia"] = json.dumps(parse_tipologias(data["disponibilidade_tipologia"]), ensure_ascii=False)
    return data


def render_new_launch(df: pd.DataFrame) -> None:
    st.caption("Clique no mapa para preencher latitude e longitude.")
    st.session_state.setdefault("new_lat", FORTALEZA_CENTER[0])
    st.session_state.setdefault("new_lon", FORTALEZA_CENTER[1])
    click = st_folium(build_map(df), use_container_width=True, height=340, key="admin_pick_map")
    clicked = click.get("last_clicked") if click else None
    if clicked:
        st.session_state.new_lat, st.session_state.new_lon = float(clicked["lat"]), float(clicked["lng"])

    with st.form("novo_lancamento", clear_on_submit=True):
        data = launch_form_fields(
            f"new_{st.session_state.new_lat:.6f}_{st.session_state.new_lon:.6f}", {}, st.session_state.new_lat, st.session_state.new_lon
        )
        if st.form_submit_button("Salvar lançamento", type="primary"):
            erros = validate(data)
            if erros:
                for e in erros:
                    st.error(e)
                return
            rec = finalize(data)
            rec["id"] = int(df["id"].max()) + 1 if not df.empty else 1
            backend().insert(rec)
            refresh()
            st.success(f"Lançamento “{rec['nome']}” salvo.")
            st.rerun()


def render_edit_launch(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("Nenhum lançamento cadastrado.")
        return
    opcoes = {f"#{r.id} — {r.nome} ({r.bairro})": int(r.id) for r in df.sort_values("nome").itertuples()}
    escolha = st.selectbox("Lançamento", list(opcoes))
    rid = opcoes[escolha]
    rec = df[df["id"] == rid].iloc[0].to_dict()

    lat = rec["latitude"] if not pd.isna(rec["latitude"]) else FORTALEZA_CENTER[0]
    lon = rec["longitude"] if not pd.isna(rec["longitude"]) else FORTALEZA_CENTER[1]
    with st.form(f"editar_{rid}"):
        data = launch_form_fields(f"edit_{rid}", rec, lat, lon)
        if st.form_submit_button("Salvar alterações", type="primary"):
            erros = validate(data)
            if erros:
                for e in erros:
                    st.error(e)
            else:
                backend().update(rid, finalize(data))
                refresh()
                st.success("Alterações salvas.")
                st.rerun()

    with st.expander("🗑️ Excluir lançamento"):
        confirm = st.text_input(f"Digite o nome “{rec['nome']}” para confirmar", key=f"del_confirm_{rid}")
        if st.button("Excluir definitivamente", type="secondary", disabled=confirm.strip() != rec["nome"], key=f"del_{rid}"):
            backend().delete(rid)
            refresh()
            st.success("Lançamento excluído.")
            st.rerun()


def render_import_export(df: pd.DataFrame) -> None:
    st.download_button(
        "Baixar catálogo (CSV)",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="catalogo_lancamentos_fortaleza.csv",
        mime="text/csv",
    )
    st.divider()
    st.warning("A importação **substitui todo o catálogo** pelo conteúdo do CSV.")
    uploaded = st.file_uploader("Importar CSV de lançamentos", type=["csv"])
    if uploaded is not None:
        try:
            importado = pd.read_csv(uploaded, dtype=str, keep_default_na=False)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Erro ao ler CSV: {exc}")
            return
        obrigatorias = ["nome", "bairro", "construtora"]
        faltantes = [c for c in obrigatorias if c not in importado.columns]
        if faltantes:
            st.error(f"CSV inválido. Colunas obrigatórias ausentes: {', '.join(faltantes)}")
            return
        ausentes = [c for c in COLUMNS if c not in importado.columns]
        if ausentes:
            st.info(f"Colunas ausentes serão preenchidas vazias: {', '.join(ausentes)}")
        importado = normalize(importado)
        if (importado["id"] == 0).all():
            importado["id"] = range(1, len(importado) + 1)
        st.dataframe(importado.head(10), width="stretch", hide_index=True)
        st.caption(f"{len(importado)} linhas lidas.")
        if st.button("Confirmar importação", type="primary"):
            backend().replace_all(importado)
            refresh()
            st.success("CSV importado.")
            st.rerun()


def render_admin(df: pd.DataFrame) -> None:
    st.caption(f"Armazenamento: **{backend().name}**")
    if backend().name == "CSV local":
        st.warning("Modo CSV local: em deploy na nuvem os dados se perdem a cada reinício. Configure o Supabase (ver README).")
    t1, t2, t3 = st.tabs(["➕ Cadastrar", "✏️ Editar / excluir", "⇅ Importar / exportar"])
    with t1:
        render_new_launch(df)
    with t2:
        render_edit_launch(df)
    with t3:
        render_import_export(df)


# --------------------------------------------------------------------------- main


def main() -> None:
    st.set_page_config(page_title="Lançamentos Fortaleza", page_icon="📍", layout="wide")
    st.title("📍 Catálogo de Lançamentos Imobiliários — Fortaleza/CE")

    try:
        df = load_data(backend().name)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Falha ao carregar dados ({backend().name}): {exc}")
        df = normalize(pd.DataFrame(columns=COLUMNS))

    is_admin = render_admin_access()
    df_f = render_filters(df)
    render_overview(df_f)

    abas = ["🗺️ Mapa e catálogo", "📊 Análise de mercado"] + (["🔐 ADM"] if is_admin else [])
    tabs = st.tabs(abas)
    with tabs[0]:
        st_folium(build_map(df_f), use_container_width=True, height=430, key="public_map")
        render_catalog(df_f)
    with tabs[1]:
        render_market(df_f)
    if is_admin:
        with tabs[2]:
            render_admin(df)


if __name__ == "__main__":
    main()
