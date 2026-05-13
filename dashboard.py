import streamlit as st
import pandas as pd
import psycopg2
import plotly.graph_objects as go
from datetime import date
import os

# ── Configuração da página ──────────────────────────────────────────────────
st.set_page_config(
    page_title="KPI Dashboard — Mais Med",
    page_icon="🚑",
    layout="wide",
)

# ── Credenciais (via secrets ou env vars) ───────────────────────────────────
# Em produção: crie .streamlit/secrets.toml com [database] host=... etc.
# Para dev local: defina variáveis de ambiente ou edite os defaults abaixo.
DB_HOST     = st.secrets.get("database", {}).get("host",     os.getenv("DB_HOST",     "aws-1-us-east-1.pooler.supabase.com"))
DB_PORT     = st.secrets.get("database", {}).get("port",     os.getenv("DB_PORT",     "5432"))
DB_NAME     = st.secrets.get("database", {}).get("dbname",   os.getenv("DB_NAME",     "postgres"))
DB_USER     = st.secrets.get("database", {}).get("user",     os.getenv("DB_USER",     "postgres.ltfvmvpijonkhmuhzflk"))
DB_PASSWORD = st.secrets.get("database", {}).get("password", os.getenv("DB_PASSWORD", ""))

# ── Conexão e query ─────────────────────────────────────────────────────────
@st.cache_data(ttl=300)  # cache de 5 min; recarrega automaticamente
def carregar_dados(ano: int, mes: int) -> pd.DataFrame:
    query = """
        SELECT
            data_registro,
            data_corte,
            valor_consolidado,
            km_dia,
            remocoes_dia,
            remocoes_adulto,
            remocoes_neonatal,
            faturamento_dia,
            ticket_medio,
            previsao_remocoes,
            previsao_faturamento
        FROM kpi_historico
        WHERE EXTRACT(YEAR  FROM data_registro) = %s
          AND EXTRACT(MONTH FROM data_registro) = %s
        ORDER BY data_registro ASC
    """
    try:
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
            user=DB_USER, password=DB_PASSWORD,
            sslmode="require", connect_timeout=10,
        )
        df = pd.read_sql(query, conn, params=(ano, mes))
        conn.close()
        return df
    except Exception as e:
        st.error(f"Erro ao conectar ao banco: {e}")
        return pd.DataFrame()


def ultimo_registro(df: pd.DataFrame) -> pd.Series | None:
    if df.empty:
        return None
    return df.sort_values("data_registro").iloc[-1]


def formatar_brl(valor) -> str:
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "—"


def formatar_num(valor, decimais=1) -> str:
    try:
        return f"{float(valor):,.{decimais}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "—"


# ── Header ──────────────────────────────────────────────────────────────────
col_logo, col_titulo = st.columns([1, 8])
with col_titulo:
    st.markdown("## 🚑 Dashboard KPI — Mais Med UTI Móvel")
    st.caption("Atualização automática a cada 5 minutos · Fonte: banco PostgreSQL Supabase")

st.divider()

# ── Seletor de mês/ano ───────────────────────────────────────────────────────
hoje = date.today()
col_ano, col_mes, _ = st.columns([1, 1, 6])
with col_ano:
    ano = st.selectbox("Ano", options=[2025, 2026], index=1 if hoje.year == 2026 else 0)
with col_mes:
    meses = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
        5: "Maio",    6: "Junho",     7: "Julho", 8: "Agosto",
        9: "Setembro",10: "Outubro", 11: "Novembro", 12: "Dezembro",
    }
    mes = st.selectbox(
        "Mês",
        options=list(meses.keys()),
        format_func=lambda x: meses[x],
        index=hoje.month - 1,
    )

# ── Carrega dados ────────────────────────────────────────────────────────────
df = carregar_dados(ano, mes)
ultimo = ultimo_registro(df)

if ultimo is None:
    st.warning(f"Nenhum registro encontrado para {meses[mes]}/{ano}.")
    st.stop()

periodo = f"{meses[mes]}/{ano} · Corte: {pd.to_datetime(ultimo['data_corte']).strftime('%d/%m/%Y')}"
st.markdown(f"**{periodo}**")

# ── Cards de KPI ─────────────────────────────────────────────────────────────
st.markdown("### 📊 KPIs do Período")
c1, c2, c3, c4, c5 = st.columns(5)

c1.metric(
    label="💰 Valor Consolidado",
    value=formatar_brl(ultimo["valor_consolidado"]),
)
c2.metric(
    label="🏥 Remoções Adulto",
    value=formatar_num(ultimo["remocoes_adulto"], 0),
    delta=f"{formatar_num(ultimo['remocoes_neonatal'], 0)} neonatal",
    delta_color="off",
)
c3.metric(
    label="🚑 Remoções/dia",
    value=formatar_num(ultimo["remocoes_dia"]),
)
c4.metric(
    label="🛣️ Km/dia",
    value=formatar_num(ultimo["km_dia"]),
)
c5.metric(
    label="💵 Ticket Médio",
    value=formatar_brl(ultimo["ticket_medio"]),
)

st.divider()

# ── Cards de previsão ────────────────────────────────────────────────────────
st.markdown("### 🔮 Previsão do Mês")
p1, p2, p3 = st.columns(3)

p1.metric(
    label="📦 Previsão Remoções",
    value=formatar_num(ultimo["previsao_remocoes"], 0),
)
p2.metric(
    label="💳 Faturamento/dia",
    value=formatar_brl(ultimo["faturamento_dia"]),
)
p3.metric(
    label="📈 Previsão Faturamento",
    value=formatar_brl(ultimo["previsao_faturamento"]),
)

st.divider()

# ── Gráfico de evolução ───────────────────────────────────────────────────────
st.markdown("### 📅 Evolução Diária do Mês")

if len(df) < 2:
    st.info("Registros insuficientes para gerar gráfico de evolução (mínimo 2 dias).")
else:
    df_plot = df.sort_values("data_registro").copy()
    df_plot["data_label"] = pd.to_datetime(df_plot["data_registro"]).dt.strftime("%d/%m")

    tab1, tab2, tab3 = st.tabs(["Remoções", "Faturamento/dia", "Km/dia"])

    with tab1:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_plot["data_label"], y=df_plot["remocoes_adulto"],
            name="Adulto", mode="lines+markers",
            line=dict(color="#1f77b4", width=2),
        ))
        fig.add_trace(go.Scatter(
            x=df_plot["data_label"], y=df_plot["remocoes_neonatal"],
            name="Neonatal", mode="lines+markers",
            line=dict(color="#ff7f0e", width=2),
        ))
        fig.add_trace(go.Scatter(
            x=df_plot["data_label"], y=df_plot["remocoes_dia"],
            name="Total/dia", mode="lines+markers",
            line=dict(color="#2ca02c", width=2, dash="dot"),
        ))
        fig.update_layout(
            xaxis_title="Data", yaxis_title="Remoções",
            legend=dict(orientation="h", y=-0.2),
            margin=dict(t=20, b=40),
            height=340,
        )
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            x=df_plot["data_label"], y=df_plot["faturamento_dia"],
            name="Faturamento/dia",
            marker_color="#17a2b8",
        ))
        fig2.update_layout(
            xaxis_title="Data", yaxis_title="R$",
            margin=dict(t=20, b=40),
            height=340,
        )
        st.plotly_chart(fig2, use_container_width=True)

    with tab3:
        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(
            x=df_plot["data_label"], y=df_plot["km_dia"],
            name="Km/dia", mode="lines+markers",
            fill="tozeroy", fillcolor="rgba(148,103,189,0.15)",
            line=dict(color="#9467bd", width=2),
        ))
        fig3.update_layout(
            xaxis_title="Data", yaxis_title="Km",
            margin=dict(t=20, b=40),
            height=340,
        )
        st.plotly_chart(fig3, use_container_width=True)

# ── Tabela detalhada ─────────────────────────────────────────────────────────
with st.expander("📋 Ver todos os registros do mês"):
    st.dataframe(
        df.sort_values("data_registro", ascending=False),
        use_container_width=True,
        hide_index=True,
    )

# ── Rodapé ───────────────────────────────────────────────────────────────────
st.caption(f"Dashboard gerado em {date.today().strftime('%d/%m/%Y')} · Mais Med UTI Móvel")
