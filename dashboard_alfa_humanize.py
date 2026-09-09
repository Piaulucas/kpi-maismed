import streamlit as st
import pandas as pd
import psycopg2
import plotly.graph_objects as go
from datetime import date
import os

from kpi_calc import calcular_kpis_empresa

st.set_page_config(page_title="KPI — Alfa + Humanize", page_icon="🏥", layout="wide")

st.markdown("""
<style>
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
</style>
""", unsafe_allow_html=True)

EMPRESAS = {
    'alfa':     {'nome': 'Alfa Saúde',         'cor': '#ff7f0e'},
    'humanize': {'nome': 'Humanize Life Care',  'cor': '#2ca02c'},
}

DB_HOST     = st.secrets.get("database", {}).get("host",     os.getenv("DB_HOST",     "aws-1-us-east-1.pooler.supabase.com"))
DB_PORT     = st.secrets.get("database", {}).get("port",     os.getenv("DB_PORT",     "5432"))
DB_NAME     = st.secrets.get("database", {}).get("dbname",   os.getenv("DB_NAME",     "postgres"))
DB_USER     = st.secrets.get("database", {}).get("user",     os.getenv("DB_USER",     "postgres.ltfvmvpijonkhmuhzflk"))
DB_PASSWORD = st.secrets.get("database", {}).get("password", os.getenv("DB_PASSWORD", ""))

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
        conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
                                user=DB_USER, password=DB_PASSWORD, sslmode="require")
        df = pd.read_sql(query, conn, params=(ano, mes, list(empresas)))
        conn.close()
        return df
    except Exception as e:
        st.error(f"Erro ao conectar: {e}")
        return pd.DataFrame()

def brl(v):
    try: return f"R$ {float(v):,.2f}".replace(",","X").replace(".",",").replace("X",".")
    except: return "—"

def num(v, d=1):
    try: return f"{float(v):,.{d}f}".replace(",","X").replace(".",",").replace("X",".")
    except: return "—"

st.markdown("## 🏥 Dashboard KPI — Alfa Saúde · Humanize Life Care")
st.caption("Atualização automática a cada 5 minutos · Fonte: banco PostgreSQL Supabase")
st.divider()

hoje = date.today()
meses = {1:"Janeiro",2:"Fevereiro",3:"Março",4:"Abril",5:"Maio",6:"Junho",
         7:"Julho",8:"Agosto",9:"Setembro",10:"Outubro",11:"Novembro",12:"Dezembro"}
c1, c2, _ = st.columns([1,1,6])
with c1: ano = st.selectbox("Ano", [2025,2026], index=1 if hoje.year==2026 else 0)
with c2: mes = st.selectbox("Mês", list(meses.keys()), format_func=lambda x: meses[x], index=hoje.month-1)

df = carregar_dados(ano, mes, list(EMPRESAS.keys()))

if df.empty:
    st.warning("Nenhum dado encontrado.")
    st.stop()

st.markdown(f"**{meses[mes]}/{ano}**")
st.divider()

st.markdown("### 📊 KPIs por Empresa")

for chave, info in EMPRESAS.items():
    df_emp = df[df['empresa'] == chave]
    if df_emp.empty:
        st.warning(f"{info['nome']}\nSem dados")
        continue

    kpis = calcular_kpis_empresa(df_emp, hoje=hoje)
    mes_fechado = kpis['mes_fechado']

    kpi_items = [
        f"<div class='kpi-item'><div class='kpi-label'>Valor Consolidado</div><div class='kpi-value'>{brl(kpis['valor_consolidado'])}</div></div>",
        f"<div class='kpi-item'><div class='kpi-label'>Faturamento/dia</div><div class='kpi-value'>{brl(kpis['faturamento_dia'])}</div></div>",
    ]
    if not mes_fechado:
        kpi_items.append(f"<div class='kpi-item'><div class='kpi-label'>Prev. Faturamento</div><div class='kpi-value'>{brl(kpis['previsao_faturamento'])}</div></div>")
    kpi_items += [
        f"<div class='kpi-item'><div class='kpi-label'>Adulto</div><div class='kpi-value'>{kpis['remocoes_adulto']}</div></div>",
        f"<div class='kpi-item'><div class='kpi-label'>Neonatal</div><div class='kpi-value'>{kpis['remocoes_neonatal']}</div></div>",
    ]
    if not mes_fechado:
        kpi_items.append(f"<div class='kpi-item'><div class='kpi-label'>Prev. Remoções</div><div class='kpi-value'>{kpis['previsao_remocoes']}</div></div>")
    kpi_items += [
        f"<div class='kpi-item'><div class='kpi-label'>Rem/dia</div><div class='kpi-value'>{num(kpis['remocoes_dia'], 1)}</div></div>",
        f"<div class='kpi-item'><div class='kpi-label'>Km/dia</div><div class='kpi-value'>{num(kpis['km_dia'], 0)}</div></div>",
        f"<div class='kpi-item'><div class='kpi-label'>Ticket Médio</div><div class='kpi-value'>{brl(kpis['ticket_medio'])}</div></div>",
    ]

    card_html = (
        f"<div class='kpi-card' style='border-left-color: {info['cor']}'>"
        f"<div class='kpi-empresa' style='color: {info['cor']}'>{info['nome']}</div>"
        f"<div class='kpi-row'>{''.join(kpi_items)}</div>"
        f"</div>"
    )
    st.markdown(card_html, unsafe_allow_html=True)

st.divider()

st.markdown("### 📅 Evolução — Faturamento Acumulado do Mês")
fig = go.Figure()
for chave, info in EMPRESAS.items():
    df_emp = df[df['empresa'] == chave].copy()
    df_emp['data_corte'] = pd.to_datetime(df_emp['data_corte'])
    df_emp = df_emp.sort_values('data_corte')
    if df_emp.empty: continue
    df_emp['data_corte'] = pd.to_datetime(df_emp['data_corte'])
    df_emp = df_emp.sort_values('data_corte')
    df_emp['data_label'] = df_emp['data_corte'].dt.strftime('%d/%m')
    fig.add_trace(go.Scatter(
        x=df_emp['data_label'], y=df_emp['valor_consolidado'],
        name=info['nome'], mode="lines+markers",
        line=dict(color=info['cor'], width=2),
    ))
fig.update_layout(xaxis_title="Data", yaxis_title="R$",
                  legend=dict(orientation="h", y=-0.2),
                  margin=dict(t=20, b=40), height=340)
st.plotly_chart(fig, use_container_width=True)

st.markdown("### 🔮 Previsão de Faturamento do Mês")
empresas_nomes, previsoes, cores = [], [], []
for chave, info in EMPRESAS.items():
    df_emp = df[df['empresa'] == chave]
    if df_emp.empty: continue
    ultimo = df_emp.sort_values("data_corte").iloc[-1]
    empresas_nomes.append(info['nome'])
    previsoes.append(float(ultimo['previsao_faturamento']))
    cores.append(info['cor'])

fig2 = go.Figure(go.Bar(x=empresas_nomes, y=previsoes, marker_color=cores))
fig2.update_layout(yaxis_title="R$", margin=dict(t=20, b=40), height=300)
st.plotly_chart(fig2, use_container_width=True)

with st.expander("📋 Ver todos os registros"):
    st.dataframe(df.sort_values(["empresa","data_registro"], ascending=[True,False]),
                 use_container_width=True, hide_index=True)

st.caption(f"Dashboard gerado em {date.today().strftime('%d/%m/%Y')}")
