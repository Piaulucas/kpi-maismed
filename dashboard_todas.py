import streamlit as st
import pandas as pd
import psycopg2
import plotly.graph_objects as go
from datetime import date
import os

st.set_page_config(page_title="KPI Mensal — Todas as Empresas", page_icon="🏥", layout="wide")

st.markdown("""
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
""", unsafe_allow_html=True)

EMPRESAS = {
    'sert':      {'nome': 'Empresa 1',           'cor': '#b8d400'},
    'maismed':   {'nome': 'Empresa 2',           'cor': '#fe0000'},
    'falcon':    {'nome': 'Empresa 3',             'cor': '#010f72'},
    'humanize':  {'nome': 'Empresa 4', 'cor': '#f48031'},
    'alfa':      {'nome': 'Empresa 5',         'cor': '#0f9ca3'},
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

col_title, col_sel = st.columns([4, 2])
with col_title:
    st.markdown("## 🏥 KPI Mensal — Todas as Empresas")
    st.caption("Atualização automática a cada 5 minutos · Supabase PostgreSQL")

hoje = date.today()
meses = {1:"Janeiro",2:"Fevereiro",3:"Março",4:"Abril",5:"Maio",6:"Junho",
         7:"Julho",8:"Agosto",9:"Setembro",10:"Outubro",11:"Novembro",12:"Dezembro"}
with col_sel:
    c1, c2 = st.columns(2)
    with c1: ano = st.selectbox("Ano", [2025,2026], index=1 if hoje.year==2026 else 0)
    with c2: mes = st.selectbox("Mês", list(meses.keys()), format_func=lambda x: meses[x], index=hoje.month-1)

df = carregar_dados(ano, mes, list(EMPRESAS.keys()))
if df.empty:
    st.warning("Nenhum dado encontrado.")
    st.stop()

corte_max = pd.to_datetime(df['data_corte']).max().strftime('%d/%m/%Y')
st.markdown(f"<div class='secao'>📅 {meses[mes]}/{ano} · Corte: {corte_max}</div>", unsafe_allow_html=True)

st.markdown("<div class='secao'>Indicadores por Empresa</div>", unsafe_allow_html=True)

for chave, info in EMPRESAS.items():
    df_emp = df[df['empresa'] == chave]
    if df_emp.empty:
        continue
    # Somas e médias do mês todo
    valor_consolidado  = df_emp['faturamento_dia'].sum()
    faturamento_dia    = df_emp['faturamento_dia'].mean()
    remocoes_adulto    = int(df_emp['remocoes_adulto'].sum())
    remocoes_neonatal  = int(df_emp['remocoes_neonatal'].sum())
    remocoes_dia       = df_emp['remocoes_dia'].mean()
    km_dia             = df_emp['km_dia'].mean()
    ticket_medio       = df_emp['ticket_medio'].mean()
    ultimo = df_emp.sort_values("data_corte").iloc[-1]
    previsao_remocoes    = int(ultimo['previsao_remocoes'])
    previsao_faturamento = float(ultimo['previsao_faturamento'])

    st.markdown(f"""
    <div class='kpi-card' style='border-left-color: {info['cor']}'>
        <div class='kpi-empresa' style='color: {info['cor']}'>{info['nome']}</div>
        <div class='kpi-row'>
            <div class='kpi-item'><div class='kpi-label'>Valor Consolidado</div><div class='kpi-value'>{brl(valor_consolidado)}</div></div>
            <div class='kpi-item'><div class='kpi-label'>Faturamento/dia</div><div class='kpi-value'>{brl(faturamento_dia)}</div></div>
            <div class='kpi-item'><div class='kpi-label'>Prev. Faturamento</div><div class='kpi-value'>{brl(previsao_faturamento)}</div></div>
            <div class='kpi-item'><div class='kpi-label'>Adulto</div><div class='kpi-value'>{remocoes_adulto}</div></div>
            <div class='kpi-item'><div class='kpi-label'>Neonatal</div><div class='kpi-value'>{remocoes_neonatal}</div></div>
            <div class='kpi-item'><div class='kpi-label'>Prev. Remoções</div><div class='kpi-value'>{previsao_remocoes}</div></div>
            <div class='kpi-item'><div class='kpi-label'>Rem/dia</div><div class='kpi-value'>{num(remocoes_dia, 1)}</div></div>
            <div class='kpi-item'><div class='kpi-label'>Km/dia</div><div class='kpi-value'>{num(km_dia, 0)}</div></div>
            <div class='kpi-item'><div class='kpi-label'>Ticket Médio</div><div class='kpi-value'>{brl(ticket_medio)}</div></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<div class='secao'>Evolução — Faturamento Acumulado do Mês</div>", unsafe_allow_html=True)
fig = go.Figure()
for chave, info in EMPRESAS.items():
    df_emp = df[df['empresa'] == chave].copy()
    if df_emp.empty: continue
    df_emp['data_corte'] = pd.to_datetime(df_emp['data_corte'])
    df_emp = df_emp.sort_values('data_corte')
    fig.add_trace(go.Scatter(
        x=df_emp['data_corte'], y=df_emp['valor_consolidado'],
        name=info['nome'], mode="lines+markers",
        line=dict(color=info['cor'], width=2),
        marker=dict(size=6),
    ))
fig.update_layout(
    plot_bgcolor='white', paper_bgcolor='white',
    xaxis=dict(showgrid=True, gridcolor='#f0f0f0'),
    yaxis=dict(showgrid=True, gridcolor='#f0f0f0', tickprefix='R$ '),
    legend=dict(orientation="h", y=-0.25),
    margin=dict(t=10, b=40, l=10, r=10), height=340,
)
st.plotly_chart(fig, use_container_width=True)

st.markdown("<div class='secao'>Previsão de Faturamento do Mês</div>", unsafe_allow_html=True)
empresas_nomes, previsoes, cores = [], [], []
for chave, info in EMPRESAS.items():
    df_emp = df[df['empresa'] == chave]
    if df_emp.empty: continue
    u = df_emp.sort_values("data_corte").iloc[-1]
    empresas_nomes.append(info['nome'])
    previsoes.append(float(u['previsao_faturamento']))
    cores.append(info['cor'])
fig2 = go.Figure(go.Bar(x=empresas_nomes, y=previsoes, marker_color=cores))
fig2.update_layout(
    plot_bgcolor='white', paper_bgcolor='white',
    yaxis=dict(showgrid=True, gridcolor='#f0f0f0', tickprefix='R$ '),
    margin=dict(t=10, b=40, l=10, r=10), height=300,
)
st.plotly_chart(fig2, use_container_width=True)

with st.expander("📋 Ver todos os registros"):
    st.dataframe(df.sort_values(["empresa","data_corte"], ascending=[True,False]),
                 use_container_width=True, hide_index=True)

st.caption(f"Dashboard gerado em {date.today().strftime('%d/%m/%Y')} · Piau Gestão em Saúde")
