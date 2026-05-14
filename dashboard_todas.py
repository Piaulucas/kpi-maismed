import streamlit as st
import pandas as pd
import psycopg2
import plotly.graph_objects as go
from datetime import date
import os

st.set_page_config(page_title="KPI Dashboard — Todas as Empresas", page_icon="🏥", layout="wide")

EMPRESAS = {
    'maismed':   {'nome': 'Mais Med',           'cor': '#1f77b4'},
    'alfa':      {'nome': 'Alfa Saúde',          'cor': '#ff7f0e'},
    'humanize':  {'nome': 'Humanize Life Care',  'cor': '#2ca02c'},
    'sert':      {'nome': 'Sert Med',            'cor': '#d62728'},
    'falcon':    {'nome': 'Falcon',              'cor': '#9467bd'},
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

# ── Header
st.markdown("## 🏥 Dashboard KPI — Todas as Empresas")
st.caption("Atualização automática a cada 5 minutos · Fonte: banco PostgreSQL Supabase")
st.divider()

# ── Seletor
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

# ── Cards por empresa
st.markdown("### 📊 KPIs por Empresa")
cols = st.columns(len(EMPRESAS))

for i, (chave, info) in enumerate(EMPRESAS.items()):
    df_emp = df[df['empresa'] == chave]
    if df_emp.empty:
        cols[i].warning(f"{info['nome']}\nSem dados")
        continue
    ultimo = df_emp.sort_values("data_corte").iloc[-1]
    with cols[i]:
        st.markdown(f"**{info['nome']}**")
        st.metric("💰 Valor Consolidado", brl(ultimo['valor_consolidado']))
        st.metric("💵 Faturamento/dia", brl(ultimo['faturamento_dia']))
        st.metric("📈 Prev. Faturamento", brl(ultimo['previsao_faturamento']))
        st.metric("🚑 Adulto", int(ultimo['remocoes_adulto']))
        st.metric("👶 Neonatal", int(ultimo['remocoes_neonatal']))
        st.metric("📦 Prev. Remoções", int(ultimo['previsao_remocoes']))
        st.metric("📊 Rem/dia", num(ultimo['remocoes_dia']))
        st.metric("🛣️ Km/dia", num(ultimo['km_dia']))
        st.metric("🎫 Ticket Médio", brl(ultimo['ticket_medio']))

st.divider()

# ── Gráfico comparativo
st.markdown("### 📅 Evolução — Faturamento Acumulado do Mês")
fig = go.Figure()
for chave, info in EMPRESAS.items():
    df_emp = df[df['empresa'] == chave].sort_values("data_corte")
    if df_emp.empty: continue
    df_emp = df_emp.copy()
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

# ── Comparativo de faturamento previsto
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
