import streamlit as st
import pandas as pd
import psycopg2
import plotly.graph_objects as go
from datetime import date
import os

st.set_page_config(page_title="Análise Histórica — Todas as Empresas", page_icon="📊", layout="wide")

st.markdown("""
<style>
    .main { background-color: #f4f6fb; }
    .block-container { padding-top: 1.5rem; padding-bottom: 1rem; }
    .kpi-card {
        background: white;
        border-radius: 10px;
        padding: 14px 18px;
        border: 0.5px solid #e0e0e0;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    }
    .kpi-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; color: #888; margin-bottom: 4px; }
    .kpi-value { font-size: 20px; font-weight: 700; color: #1a1a2e; }
    .kpi-sub { font-size: 12px; color: #aaa; margin-top: 2px; }
    .secao { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1.5px; color: #888; margin: 20px 0 10px 0; }
</style>
""", unsafe_allow_html=True)

EMPRESAS = {
    'sert':      {'nome': 'Sert Med',           'cor': '#b8d400'},
    'maismed':   {'nome': 'Mais Med',           'cor': '#fe0000'},
    'falcon':    {'nome': 'Falcon',             'cor': '#010f72'},
    'humanize':  {'nome': 'Humanize Life Care', 'cor': '#f48031'},
    'alfa':      {'nome': 'Alfa Saúde',         'cor': '#0f9ca3'},
}

DB_HOST     = st.secrets.get("database", {}).get("host",     os.getenv("DB_HOST",     "aws-1-us-east-1.pooler.supabase.com"))
DB_PORT     = st.secrets.get("database", {}).get("port",     os.getenv("DB_PORT",     "5432"))
DB_NAME     = st.secrets.get("database", {}).get("dbname",   os.getenv("DB_NAME",     "postgres"))
DB_USER     = st.secrets.get("database", {}).get("user",     os.getenv("DB_USER",     "postgres.ltfvmvpijonkhmuhzflk"))
DB_PASSWORD = st.secrets.get("database", {}).get("password", os.getenv("DB_PASSWORD", ""))

@st.cache_data(ttl=300)
def carregar_periodo(ano_ini, mes_ini, ano_fim, mes_fim):
    query = """
        SELECT * FROM kpi_historico
        WHERE (EXTRACT(YEAR FROM data_corte) * 100 + EXTRACT(MONTH FROM data_corte))
              BETWEEN %s AND %s
        ORDER BY data_corte ASC
    """
    ini = ano_ini * 100 + mes_ini
    fim = ano_fim * 100 + mes_fim
    try:
        conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
                                user=DB_USER, password=DB_PASSWORD, sslmode="require")
        df = pd.read_sql(query, conn, params=(ini, fim))
        conn.close()
        df['data_corte'] = pd.to_datetime(df['data_corte'])
        df['ano_mes'] = df['data_corte'].dt.to_period('M')
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
col_title, col_sel = st.columns([3, 3])
with col_title:
    st.markdown("## 📊 Análise Histórica — Todas as Empresas")
    st.caption("Comparativo por período · Supabase PostgreSQL")

meses = {1:"Janeiro",2:"Fevereiro",3:"Março",4:"Abril",5:"Maio",6:"Junho",
         7:"Julho",8:"Agosto",9:"Setembro",10:"Outubro",11:"Novembro",12:"Dezembro"}
anos  = [2025, 2026]
hoje  = date.today()

with col_sel:
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: mes_ini  = st.selectbox("De", list(meses.keys()), format_func=lambda x: meses[x], index=0)
    with c2: ano_ini  = st.selectbox("Ano", anos, index=anos.index(hoje.year), key="ano_ini")
    with c3: mes_fim  = st.selectbox("Até", list(meses.keys()), format_func=lambda x: meses[x], index=hoje.month-1)
    with c4: ano_fim  = st.selectbox("Ano", anos, index=anos.index(hoje.year), key="ano_fim")
    with c5: kpi_sel  = st.selectbox("KPI gráfico", ["Faturamento", "Remoções", "Km/dia", "Ticket Médio"])

if (ano_ini * 100 + mes_ini) > (ano_fim * 100 + mes_fim):
    st.warning("O período inicial não pode ser maior que o final.")
    st.stop()

df = carregar_periodo(ano_ini, mes_ini, ano_fim, mes_fim)
if df.empty:
    st.warning("Nenhum dado encontrado para o período selecionado.")
    st.stop()

periodo_label = f"{meses[mes_ini]}/{ano_ini} → {meses[mes_fim]}/{ano_fim}"
st.markdown(f"<div class='secao'>📅 {periodo_label}</div>", unsafe_allow_html=True)

# ── Cards de totais por empresa
st.markdown("<div class='secao'>Totais do Período por Empresa</div>", unsafe_allow_html=True)
cols = st.columns(len(EMPRESAS))

for i, (chave, info) in enumerate(EMPRESAS.items()):
    df_emp = df[df['empresa'] == chave]
    if df_emp.empty:
        cols[i].markdown(f"<div class='kpi-card'><div class='kpi-label' style='color:{info['cor']}'>{info['nome']}</div><div class='kpi-sub'>Sem dados</div></div>", unsafe_allow_html=True)
        continue
    fat_total   = df_emp['faturamento_dia'].sum()
    rem_adulto  = int(df_emp['remocoes_adulto'].sum())
    rem_neo     = int(df_emp['remocoes_neonatal'].sum())
    rem_dia     = df_emp['remocoes_dia'].mean()
    km_dia      = df_emp['km_dia'].mean()
    ticket      = df_emp['ticket_medio'].mean()
    meses_count = df_emp['ano_mes'].nunique()

    cols[i].markdown(f"""
    <div class='kpi-card' style='border-left: 4px solid {info['cor']}'>
        <div class='kpi-label' style='color:{info["cor"]}'>{info['nome']}</div>
        <div class='kpi-value'>{brl(fat_total)}</div>
        <div class='kpi-sub'>Faturamento total</div>
        <hr style='border:none;border-top:0.5px solid #eee;margin:8px 0'>
        <div style='font-size:12px;color:#555;line-height:1.8'>
            <b>{rem_adulto}</b> adulto · <b>{rem_neo}</b> neonatal<br>
            Rem/dia: <b>{num(rem_dia)}</b> · Km/dia: <b>{num(km_dia, 0)}</b><br>
            Ticket médio: <b>{brl(ticket)}</b><br>
            <span style='color:#aaa'>{meses_count} mês(es) com dados</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

# ── Gráfico de barras agrupado por mês
st.markdown("<div class='secao'>Faturamento Mensal por Empresa</div>", unsafe_allow_html=True)

df_mensal = df.groupby(['ano_mes', 'empresa'])['faturamento_dia'].sum().reset_index()
df_mensal['mes_label'] = df_mensal['ano_mes'].astype(str).apply(
    lambda x: meses[int(x.split('-')[1])][:3] + '/' + x.split('-')[0][2:]
)
periodos = sorted(df_mensal['ano_mes'].unique())
labels   = [meses[int(str(p).split('-')[1])][:3] + '/' + str(p).split('-')[0][2:] for p in periodos]

fig_bar = go.Figure()
for chave, info in EMPRESAS.items():
    df_e = df_mensal[df_mensal['empresa'] == chave]
    vals = []
    for p in periodos:
        row = df_e[df_e['ano_mes'] == p]
        vals.append(float(row['faturamento_dia'].values[0]) if not row.empty else 0)
    fig_bar.add_trace(go.Bar(name=info['nome'], x=labels, y=vals, marker_color=info['cor'], opacity=0.85))

fig_bar.update_layout(
    barmode='group',
    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
    xaxis=dict(showgrid=False),
    yaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.2)', tickprefix='R$ ', tickformat=',.0f'),
    legend=dict(orientation="h", y=-0.2),
    margin=dict(t=10, b=60, l=60, r=10), height=360,
)
st.plotly_chart(fig_bar, use_container_width=True)

# ── Gráfico de evolução mensal (linha) por KPI selecionado
kpi_map = {
    "Faturamento":  ("faturamento_dia",   "sum",  "R$ "),
    "Remoções":     ("remocoes_dia",       "sum",  ""),
    "Km/dia":       ("km_dia",             "mean", ""),
    "Ticket Médio": ("ticket_medio",       "mean", "R$ "),
}
col_kpi, agg_kpi, prefix_kpi = kpi_map[kpi_sel]
st.markdown(f"<div class='secao'>Evolução Mensal — {kpi_sel}</div>", unsafe_allow_html=True)

df_line = df.groupby(['ano_mes', 'empresa'])[col_kpi].agg(agg_kpi).reset_index()

fig_line = go.Figure()
for chave, info in EMPRESAS.items():
    df_e = df_line[df_line['empresa'] == chave]
    vals = []
    for p in periodos:
        row = df_e[df_e['ano_mes'] == p]
        vals.append(float(row[col_kpi].values[0]) if not row.empty else None)
    fig_line.add_trace(go.Scatter(
        name=info['nome'], x=labels, y=vals,
        mode='lines+markers',
        line=dict(color=info['cor'], width=2),
        marker=dict(size=7),
        connectgaps=False,
    ))

fig_line.update_layout(
    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
    xaxis=dict(showgrid=False),
    yaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.2)',
               tickprefix=prefix_kpi, tickformat=',.0f'),
    legend=dict(orientation="h", y=-0.2),
    margin=dict(t=10, b=60, l=60, r=10), height=320,
)
st.plotly_chart(fig_line, use_container_width=True)

with st.expander("📋 Ver dados brutos do período"):
    st.dataframe(
        df.sort_values(["empresa", "data_corte"], ascending=[True, False]),
        use_container_width=True, hide_index=True
    )

st.caption(f"Análise gerada em {date.today().strftime('%d/%m/%Y')} · Piau Gestão em Saúde")
