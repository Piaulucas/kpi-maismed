"""UI compartilhada pelos dashboards mensais (Streamlit).

dashboard_todas.py, dashboard_alfa_humanize.py e dashboard_sert_falcon_maismed.py
têm o mesmo layout e diferem só em título, ícone e empresas exibidas — todos
chamam render_dashboard_mensal(). Nenhuma fórmula de KPI vive aqui: todo número
de card vem de kpi_calc.calcular_kpis_empresa().
"""
import os
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import psycopg2
import streamlit as st

from kpi_calc import calcular_kpis_empresa

# Ordem aqui = ordem de exibição nos dashboards.
EMPRESAS = {
    'sert':      {'nome': 'Sert Med',           'cor': '#b8d400'},
    'maismed':   {'nome': 'Mais Med',           'cor': '#fe0000'},
    'falcon':    {'nome': 'Falcon',             'cor': '#010f72'},
    'humanize':  {'nome': 'Humanize Life Care', 'cor': '#f48031'},
    'alfa':      {'nome': 'Alfa Saúde',         'cor': '#0f9ca3'},
}

MESES = {1:"Janeiro",2:"Fevereiro",3:"Março",4:"Abril",5:"Maio",6:"Junho",
         7:"Julho",8:"Agosto",9:"Setembro",10:"Outubro",11:"Novembro",12:"Dezembro"}

CSS = """
<style>
    .main { background-color: #f4f6fb; }
    .block-container { padding-top: 1.5rem; padding-bottom: 1rem; }
    .kpi-card {
        background: white;
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 10px;
        border-left: 5px solid #ccc;
        box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    }
    .kpi-empresa { font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 10px; }
    .kpi-row { display: flex; gap: 12px; flex-wrap: wrap; }
    .kpi-item { flex: 1; min-width: 100px; }
    .kpi-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; color: #888; margin-bottom: 2px; }
    .kpi-value { font-size: 18px; font-weight: 700; color: #1a1a2e; }
    .secao { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1.5px; color: #888; margin: 20px 0 10px 0; }
</style>
"""


def _conectar():
    db = st.secrets.get("database", {})
    return psycopg2.connect(
        host=db.get("host",         os.getenv("DB_HOST",     "aws-1-us-east-1.pooler.supabase.com")),
        port=db.get("port",         os.getenv("DB_PORT",     "5432")),
        dbname=db.get("dbname",     os.getenv("DB_NAME",     "postgres")),
        user=db.get("user",         os.getenv("DB_USER",     "postgres.ltfvmvpijonkhmuhzflk")),
        password=db.get("password", os.getenv("DB_PASSWORD", "")),
        sslmode="require",
    )


@st.cache_data(ttl=300)
def carregar_dados(ano, mes, empresas):
    query = """
        SELECT * FROM kpi_historico
        WHERE EXTRACT(YEAR FROM data_corte) = %s
          AND EXTRACT(MONTH FROM data_corte) = %s
          AND empresa = ANY(%s)
        ORDER BY data_corte ASC
    """
    try:
        conn = _conectar()
        df = pd.read_sql(query, conn, params=(ano, mes, list(empresas)))
        conn.close()
        return df
    except Exception as e:
        st.error(f"Erro ao conectar: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300)
def carregar_data_corte_ref(ano, mes):
    """Maior data_corte do mês entre TODAS as empresas (sem filtro de empresa),
    para os 3 dashboards chegarem ao mesmo divisor — ver kpi_calc."""
    query = """
        SELECT MAX(data_corte) FROM kpi_historico
        WHERE EXTRACT(YEAR FROM data_corte) = %s
          AND EXTRACT(MONTH FROM data_corte) = %s
    """
    try:
        conn = _conectar()
        with conn.cursor() as cur:
            cur.execute(query, (ano, mes))
            (ref,) = cur.fetchone()
        conn.close()
        return pd.Timestamp(ref).date() if ref is not None else None
    except Exception as e:
        st.error(f"Erro ao conectar: {e}")
        return None


def brl(v):
    try: return f"R$ {float(v):,.2f}".replace(",","X").replace(".",",").replace("X",".")
    except: return "—"


def num(v, d=1):
    try: return f"{float(v):,.{d}f}".replace(",","X").replace(".",",").replace("X",".")
    except: return "—"


def card_kpi_html(info, kpis):
    """Card de uma empresa. Previsões ficam ocultas quando o mês está fechado."""
    def item(label, valor):
        return f"<div class='kpi-item'><div class='kpi-label'>{label}</div><div class='kpi-value'>{valor}</div></div>"

    mes_fechado = kpis['mes_fechado']
    kpi_items = [
        item("Valor Consolidado", brl(kpis['valor_consolidado'])),
        item("Faturamento/dia", brl(kpis['faturamento_dia'])),
    ]
    if not mes_fechado:
        kpi_items.append(item("Prev. Faturamento", brl(kpis['previsao_faturamento'])))
    kpi_items += [
        item("Adulto", kpis['remocoes_adulto']),
        item("Neonatal", kpis['remocoes_neonatal']),
    ]
    if not mes_fechado:
        kpi_items.append(item("Prev. Remoções", kpis['previsao_remocoes']))
    kpi_items += [
        item("Rem/dia", num(kpis['remocoes_dia'], 1)),
        item("Km/dia", num(kpis['km_dia'], 0)),
        item("Ticket Médio", brl(kpis['ticket_medio'])),
    ]
    return (
        f"<div class='kpi-card' style='border-left-color: {info['cor']}'>"
        f"<div class='kpi-empresa' style='color: {info['cor']}'>{info['nome']}</div>"
        f"<div class='kpi-row'>{''.join(kpi_items)}</div>"
        f"</div>"
    )


def _grafico_diario(fig, margem_esq, **yaxis_extra):
    fig.update_layout(
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(t=10, b=30, l=margem_esq, r=10), height=200,
        xaxis=dict(showgrid=False, tickfont=dict(size=10), tickangle=0),
        yaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.2)', tickfont=dict(size=11), **yaxis_extra),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_dashboard_mensal(titulo, chaves_empresas):
    """Renderiza a página mensal inteira. Chame st.set_page_config() antes.

    titulo: texto do cabeçalho (ex.: "🏥 KPI Mensal — Todas as Empresas").
    chaves_empresas: chaves de EMPRESAS a exibir.
    """
    empresas = {k: v for k, v in EMPRESAS.items() if k in chaves_empresas}

    st.markdown(CSS, unsafe_allow_html=True)

    col_title, col_sel = st.columns([4, 2])
    with col_title:
        st.markdown(f"## {titulo}")
        st.caption("Atualização automática a cada 5 minutos · Supabase PostgreSQL")

    hoje = date.today()
    with col_sel:
        c1, c2 = st.columns(2)
        with c1: ano = st.selectbox("Ano", [2025,2026], index=1 if hoje.year==2026 else 0)
        with c2: mes = st.selectbox("Mês", list(MESES.keys()), format_func=lambda x: MESES[x], index=hoje.month-1)

    df = carregar_dados(ano, mes, list(empresas.keys()))
    if df.empty:
        st.warning("Nenhum dado encontrado.")
        st.stop()

    data_corte_ref = carregar_data_corte_ref(ano, mes)
    if data_corte_ref is None:
        st.error("Não foi possível obter a data de corte de referência do mês.")
        st.stop()

    st.markdown(f"<div class='secao'>📅 {MESES[mes]}/{ano} · Corte: {data_corte_ref.strftime('%d/%m/%Y')}</div>", unsafe_allow_html=True)

    # Linhas por empresa (ordenadas) e KPIs, calculados uma única vez.
    dados = {}
    for chave, info in empresas.items():
        df_emp = df[df['empresa'] == chave].copy()
        if df_emp.empty:
            continue
        df_emp['data_corte'] = pd.to_datetime(df_emp['data_corte'])
        df_emp = df_emp.sort_values('data_corte')
        kpis = calcular_kpis_empresa(df_emp, hoje=hoje, data_corte_ref=data_corte_ref)
        dados[chave] = (info, df_emp, kpis)

    st.markdown("<div class='secao'>Indicadores por Empresa</div>", unsafe_allow_html=True)
    for info, _, kpis in dados.values():
        st.markdown(card_kpi_html(info, kpis), unsafe_allow_html=True)

    st.markdown("<div class='secao'>Evolução Diária por Empresa</div>", unsafe_allow_html=True)
    for info, df_emp, _ in dados.values():
        dias = df_emp['data_corte'].dt.strftime('%d/%m').tolist()
        with st.expander(f"📊 {info['nome']}", expanded=False):
            st.caption("Remoções/dia")
            _grafico_diario(go.Figure(go.Bar(
                x=dias, y=df_emp['remocoes_dia'],
                marker_color=info['cor'], opacity=0.7,
            )), 40)

            st.caption("Km/dia")
            _grafico_diario(go.Figure(go.Scatter(
                x=dias, y=df_emp['km_dia'],
                mode='lines+markers',
                line=dict(color=info['cor'], width=2),
                marker=dict(size=5),
            )), 50)

            st.caption("Faturamento/dia (R$)")
            _grafico_diario(go.Figure(go.Scatter(
                x=dias, y=df_emp['faturamento_dia'],
                mode='lines+markers',
                line=dict(color=info['cor'], width=2),
                marker=dict(size=5),
            )), 70, tickprefix='R$ ', tickformat=',.0f')

    st.markdown("<div class='secao'>Evolução — Faturamento Acumulado do Mês</div>", unsafe_allow_html=True)
    fig = go.Figure()
    for info, df_emp, _ in dados.values():
        fig.add_trace(go.Scatter(
            x=df_emp['data_corte'], y=df_emp['valor_consolidado'],
            name=info['nome'], mode="lines+markers",
            line=dict(color=info['cor'], width=2),
            marker=dict(size=6),
        ))
    fig.update_layout(
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(showgrid=True, gridcolor='#f0f0f0'),
        yaxis=dict(showgrid=True, gridcolor='#f0f0f0', tickprefix='R$ '),
        legend=dict(orientation="h", y=-0.25),
        margin=dict(t=10, b=40, l=10, r=10), height=340,
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("<div class='secao'>Previsão de Faturamento do Mês</div>", unsafe_allow_html=True)
    fig2 = go.Figure(go.Bar(
        x=[info['nome'] for info, _, _ in dados.values()],
        y=[kpis['previsao_faturamento'] for _, _, kpis in dados.values()],
        marker_color=[info['cor'] for info, _, _ in dados.values()],
    ))
    fig2.update_layout(
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
        yaxis=dict(showgrid=True, gridcolor='#f0f0f0', tickprefix='R$ '),
        margin=dict(t=10, b=40, l=10, r=10), height=300,
    )
    st.plotly_chart(fig2, use_container_width=True)

    with st.expander("📋 Ver todos os registros"):
        st.dataframe(df.sort_values(["empresa","data_corte"], ascending=[True,False]),
                     use_container_width=True, hide_index=True)

    st.caption(f"Dashboard gerado em {date.today().strftime('%d/%m/%Y')} · Piau Gestão em Saúde")
