import pandas as pd
from datetime import date
import calendar
import sys
import psycopg2
import glob
import os

# ── CONFIGURAÇÃO ─────────────────────────────────────────────────────────────
EMPRESAS = {
    'maismed': {
        'nome': 'Mais Med',
        'pasta': '/Users/lucaspiau/Library/CloudStorage/OneDrive-Pessoal/EXCEL COMPARTILHADO/MAIS MED/2026',
    },
    'alfa': {
        'nome': 'Alfa Saúde',
        'pasta': '/Users/lucaspiau/Library/CloudStorage/OneDrive-Pessoal/EXCEL COMPARTILHADO/ALFA SAÚDE/2026',
    },
    'humanize': {
        'nome': 'Humanize Life Care',
        'pasta': '/Users/lucaspiau/Library/CloudStorage/OneDrive-Pessoal/EXCEL COMPARTILHADO/HUMANIZE LIFE CARE/2026',
    },
    'sert': {
        'nome': 'Sert Med',
        'pasta': '/Users/lucaspiau/Library/CloudStorage/OneDrive-Pessoal/EXCEL COMPARTILHADO/SERT MED/2026',
    },
    'falcon': {
        'nome': 'Falcon',
        'pasta': '/Users/lucaspiau/Library/CloudStorage/OneDrive-Pessoal/EXCEL COMPARTILHADO/FALCON/2026',
    },
}

DB_HOST = 'aws-1-us-east-1.pooler.supabase.com'
DB_PORT = '5432'
DB_NAME = 'postgres'
DB_USER = 'postgres.ltfvmvpijonkhmuhzflk'
DB_PASS = 'REDACTED'

# ── LEITURA ───────────────────────────────────────────────────────────────────
def coluna_km(df):
    for col in df.columns:
        if 'KM TOTAL' in col.upper().strip():
            return col
    raise ValueError(f"Coluna KM TOTAL não encontrada. Colunas: {list(df.columns)}")

def ler_aba(planilha, aba):
    df = pd.read_excel(planilha, sheet_name=aba, skiprows=14, usecols='B:T')
    df = df[df['PACIENTE'].notna()]
    df = df[df['PACIENTE'].str.strip() != '']
    df['DATA'] = pd.to_datetime(df['DATA'])
    return df

def ler_planilha(planilha):
    xl = pd.ExcelFile(planilha)
    abas = xl.sheet_names
    abas_adulto = [a for a in abas if 'ADULTO' in a.upper()]
    abas_neo    = [a for a in abas if 'NEONATAL' in a.upper()]
    frames_adulto = [ler_aba(planilha, a) for a in abas_adulto]
    frames_neo    = [ler_aba(planilha, a) for a in abas_neo]
    df_adulto = pd.concat(frames_adulto, ignore_index=True) if frames_adulto else pd.DataFrame()
    df_neo    = pd.concat(frames_neo,    ignore_index=True) if frames_neo    else pd.DataFrame()
    return df_adulto, df_neo

# ── MAIN ──────────────────────────────────────────────────────────────────────
if len(sys.argv) < 2:
    print("Uso: python3 atualizar_kpi_multi.py <empresa>")
    print(f"Empresas disponíveis: {', '.join(EMPRESAS.keys())}")
    sys.exit(1)

chave = sys.argv[1].lower()
if chave not in EMPRESAS:
    print(f"❌ Empresa '{chave}' não encontrada.")
    sys.exit(1)

empresa = EMPRESAS[chave]
mes_atual = date.today().strftime('%m')
arquivos = glob.glob(f"{empresa['pasta']}/{mes_atual}_*26.xlsx")

if not arquivos:
    print(f"❌ Nenhuma planilha encontrada para {empresa['nome']} no mês {mes_atual}")
    sys.exit(1)

PLANILHA = arquivos[0]
print(f"📂 [{empresa['nome']}] Usando: {os.path.basename(PLANILHA)}")

df_adulto, df_neo = ler_planilha(PLANILHA)
df_total = pd.concat([df_adulto, df_neo], ignore_index=True)

if df_total.empty:
    print(f"❌ Nenhum dado encontrado na planilha.")
    sys.exit(1)

col_km = coluna_km(df_total)
dias_no_mes = calendar.monthrange(df_total['DATA'].max().year, df_total['DATA'].max().month)[1]

# ── CONECTAR AO BANCO ────────────────────────────────────────────────────────
conn = psycopg2.connect(
    host=DB_HOST, port=DB_PORT,
    dbname=DB_NAME, user=DB_USER, password=DB_PASS
)
cursor = conn.cursor()

# Busca datas já existentes no banco para essa empresa
cursor.execute(
    'SELECT data_corte FROM kpi_historico WHERE empresa = %s', (chave,)
)
datas_existentes = {str(r[0]) for r in cursor.fetchall()}

# ── PROCESSAR DIA A DIA ───────────────────────────────────────────────────────
dias_planilha = sorted(df_total['DATA'].dt.date.unique())
inseridos = 0
ignorados = 0

for dia in dias_planilha:
    dia_str = str(dia)
    if dia_str in datas_existentes:
        ignorados += 1
        continue

    # Dados do dia específico
    df_dia_adulto = df_adulto[df_adulto['DATA'].dt.date == dia]
    df_dia_neo    = df_neo[df_neo['DATA'].dt.date == dia]
    df_dia        = pd.concat([df_dia_adulto, df_dia_neo], ignore_index=True)

    # KPIs acumulados até esse dia (para previsão)
    df_ate_dia = df_total[df_total['DATA'].dt.date <= dia]
    dias_uteis_ate = df_ate_dia['DATA'].dt.date.nunique()

    valor_consolidado  = float(df_ate_dia['VALOR TOTAL'].sum())
    km_dia             = float(df_dia[col_km].sum())
    remocoes_dia       = float(len(df_dia))
    faturamento_dia    = float(df_dia['VALOR TOTAL'].sum())
    ticket_medio       = float(df_dia['VALOR TOTAL'].mean()) if len(df_dia) > 0 else 0.0

    # Previsão baseada na média acumulada até o dia
    media_rem_dia  = float(df_ate_dia['VALOR TOTAL'].count() / dias_uteis_ate)
    media_fat_dia  = float(df_ate_dia['VALOR TOTAL'].sum() / dias_uteis_ate)
    previsao_remocoes    = int(round(media_rem_dia * dias_no_mes))
    previsao_faturamento = float(round(media_fat_dia * dias_no_mes))

    cursor.execute('''
        INSERT INTO kpi_historico
            (data_registro, data_corte, valor_consolidado, km_dia, remocoes_dia,
             remocoes_adulto, remocoes_neonatal, faturamento_dia, ticket_medio,
             previsao_remocoes, previsao_faturamento, empresa)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (
        date.today().isoformat(),
        dia_str,
        valor_consolidado,
        km_dia,
        remocoes_dia,
        len(df_dia_adulto),
        len(df_dia_neo),
        faturamento_dia,
        ticket_medio,
        previsao_remocoes,
        previsao_faturamento,
        chave,
    ))
    inseridos += 1
    print(f"  ✅ {dia_str} — {len(df_dia)} remoções · R$ {faturamento_dia:,.2f}")

conn.commit()
conn.close()

print(f"\n📊 [{empresa['nome']}] {inseridos} dia(s) inserido(s), {ignorados} já existia(m).")
