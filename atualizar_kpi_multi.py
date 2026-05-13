import pandas as pd
from datetime import date
import calendar
import sys
import psycopg2
import glob
import os

# ── CONFIGURAÇÃO ─────────────────────────────────────────────────────────────
# Passa o nome da empresa como argumento: python3 atualizar_kpi_multi.py maismed
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
    """Encontra a coluna KM independente de espaços extras."""
    for col in df.columns:
        if 'KM TOTAL' in col.upper().strip():
            return col
    raise ValueError(f"Coluna KM TOTAL não encontrada. Colunas disponíveis: {list(df.columns)}")

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
    print(f"❌ Empresa '{chave}' não encontrada. Disponíveis: {', '.join(EMPRESAS.keys())}")
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

# ── KPIs ──────────────────────────────────────────────────────────────────────
data_corte  = df_total['DATA'].max()
dias_uteis  = df_total['DATA'].nunique()
dias_no_mes = calendar.monthrange(data_corte.year, data_corte.month)[1]
col_km      = coluna_km(df_total)

valor_consolidado  = float(df_total['VALOR TOTAL'].sum())
km_dia             = float(df_total[col_km].sum() / dias_uteis)
remocoes_dia       = float(len(df_total) / dias_uteis)
faturamento_dia    = float(valor_consolidado / dias_uteis)
ticket_medio       = float(valor_consolidado / len(df_total))
previsao_remocoes  = int(round(remocoes_dia * dias_no_mes))
previsao_faturamento = float(round(faturamento_dia * dias_no_mes))

# ── BANCO ─────────────────────────────────────────────────────────────────────
conn = psycopg2.connect(
    host=DB_HOST, port=DB_PORT,
    dbname=DB_NAME, user=DB_USER, password=DB_PASS
)
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS kpi_historico (
        data_registro DATE,
        data_corte DATE,
        empresa VARCHAR(50),
        valor_consolidado REAL,
        km_dia REAL,
        remocoes_dia REAL,
        remocoes_adulto INTEGER,
        remocoes_neonatal INTEGER,
        faturamento_dia REAL,
        ticket_medio REAL,
        previsao_remocoes INTEGER,
        previsao_faturamento REAL
    )
''')

cursor.execute(
    'SELECT COUNT(*) FROM kpi_historico WHERE data_corte = %s AND empresa = %s',
    (str(data_corte)[:10], chave)
)
contagem = cursor.fetchone()[0]

if contagem == 0:
    cursor.execute('''
        INSERT INTO kpi_historico 
            (data_registro, data_corte, valor_consolidado, km_dia, remocoes_dia,
             remocoes_adulto, remocoes_neonatal, faturamento_dia, ticket_medio,
             previsao_remocoes, previsao_faturamento, empresa)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (
        date.today().isoformat(),
        str(data_corte)[:10],
        valor_consolidado,
        km_dia,
        remocoes_dia,
        len(df_adulto),
        len(df_neo),
        faturamento_dia,
        ticket_medio,
        previsao_remocoes,
        previsao_faturamento,
        chave,
    ))
    conn.commit()
    print(f"✅ KPI registrado para {empresa['nome']}!")
else:
    print(f"⚠️  Data {str(data_corte)[:10]} já existe para {empresa['nome']}. Nada inserido.")

conn.close()

print(f"KPI atualizado até: {str(data_corte)[:10]}")
print(f"Valor Consolidado: R$ {valor_consolidado:,.2f}")
print(f"Remoções: {len(df_adulto)} adulto(s) + {len(df_neo)} neonatal(is) = {len(df_total)} total")
print(f"Km/dia: {km_dia:.2f}")
print(f"Remoções/dia: {remocoes_dia:.2f}")
print(f"Faturamento/dia: R$ {faturamento_dia:,.2f}")
print(f"Ticket Médio: R$ {ticket_medio:,.2f}")
print(f"Previsão Remoções: {previsao_remocoes}")
print(f"Previsão Faturamento: R$ {previsao_faturamento:,.2f}")
