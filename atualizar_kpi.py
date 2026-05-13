import pandas as pd
from datetime import date
import calendar
import sys
import psycopg2
import glob
import os

# CONFIGURAÇÃO — busca automática da planilha do mês atual
pasta = '/Users/lucaspiau/Library/CloudStorage/OneDrive-Pessoal/EXCEL COMPARTILHADO/MAIS MED/2026'
mes_atual = date.today().strftime('%m')
arquivos = glob.glob(f'{pasta}/{mes_atual}_Planilha_de_Faturamento_Mais_Med_*.xlsx')

if not arquivos:
    print(f'❌ Nenhuma planilha encontrada para o mês {mes_atual}')
    sys.exit(1)

PLANILHA = arquivos[0]
print(f'📂 Usando: {os.path.basename(PLANILHA)}')

DB_HOST = 'aws-1-us-east-1.pooler.supabase.com'
DB_PORT = '5432'
DB_NAME = 'postgres'
DB_USER = 'postgres.ltfvmvpijonkhmuhzflk'
DB_PASS = 'REDACTED'

# LEITURA DE DADOS
def ler_aba(planilha, aba):
    df = pd.read_excel(planilha, sheet_name=aba, skiprows=14, usecols='B:T')
    df = df[df['PACIENTE'].notna()]
    df = df[df['PACIENTE'].str.strip() != '']
    df['DATA'] = pd.to_datetime(df['DATA'])
    return df

df_adulto = ler_aba(PLANILHA, 'Remoção ADULTO-PED')
df_neo = ler_aba(PLANILHA, 'Remoção NEONATAL')
df_total = pd.concat([df_adulto, df_neo], ignore_index=True)

# CALCULAR KPIs
data_corte = df_total['DATA'].max()
dias_uteis = df_total['DATA'].nunique()
dias_no_mes = calendar.monthrange(data_corte.year, data_corte.month)[1]

valor_consolidado = float(df_total['VALOR TOTAL'].sum())
km_dia = float(df_total['KM TOTAL '].sum() / dias_uteis)
remocoes_dia = float(len(df_total) / dias_uteis)
faturamento_dia = float(valor_consolidado / dias_uteis)
ticket_medio = float(valor_consolidado / len(df_total))
previsao_remocoes = int(round(remocoes_dia * dias_no_mes))
previsao_faturamento = float(round(faturamento_dia * dias_no_mes))

# SALVAR NO BANCO DE DADOS
conn = psycopg2.connect(
    host=DB_HOST, port=DB_PORT,
    dbname=DB_NAME, user=DB_USER, password=DB_PASS
)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS kpi_historico (
        data_registro DATE,
        data_corte DATE,
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

cursor.execute('SELECT COUNT(*) FROM kpi_historico WHERE data_corte = %s', (str(data_corte)[:10],))
contagem = cursor.fetchone()[0]

if contagem == 0:
    cursor.execute('''INSERT INTO kpi_historico VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''', (
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
        previsao_faturamento
    ))
    conn.commit()
    print("✅ KPI registrado!")
else:
    print(f"⚠️ Data {str(data_corte)[:10]} já existe no banco. Nada inserido.")

conn.close()

print(f'KPI atualizado até: {str(data_corte)[:10]}')
print(f'Valor Consolidado: R$ {valor_consolidado:,.2f}')
print(f'Remoções: {len(df_adulto)} adulto(s) + {len(df_neo)} neonatal(is) = {len(df_total)} total')
print(f'Média Km/dia: {km_dia:.2f}')
print(f'Média Remoções/dia: {remocoes_dia:.2f}')
print(f'Média Faturamento/dia: R$ {faturamento_dia:,.2f}')
print(f'Ticket Médio: R$ {ticket_medio:,.2f}')
print(f'Previsão de Remoções para o mês: {previsao_remocoes} remoções')
print(f'Previsão de Faturamento para o mês: R$ {previsao_faturamento:,.2f}')