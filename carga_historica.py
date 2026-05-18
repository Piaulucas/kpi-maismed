import pandas as pd
from datetime import date
import calendar
import psycopg2
import glob
import os

# ── CONFIGURAÇÃO ─────────────────────────────────────────────────────────────
EMPRESAS = {
    'maismed': {
        'nome': 'Mais Med',
        'pasta': '/Users/lucaspiau/Library/CloudStorage/OneDrive-Pessoal/EXCEL COMPARTILHADO/MAIS MED/planilhas_de_faturamento',
    },
    'alfa': {
        'nome': 'Alfa Saúde',
        'pasta': '/Users/lucaspiau/Library/CloudStorage/OneDrive-Pessoal/EXCEL COMPARTILHADO/ALFA SAÚDE/Planilhas_de_faturamento',
    },
    'humanize': {
        'nome': 'Humanize Life Care',
        'pasta': '/Users/lucaspiau/Library/CloudStorage/OneDrive-Pessoal/EXCEL COMPARTILHADO/HUMANIZE LIFE CARE/planilhas_de_faturamento',
    },
    'sert': {
        'nome': 'Sert Med',
        'pasta': '/Users/lucaspiau/Library/CloudStorage/OneDrive-Pessoal/EXCEL COMPARTILHADO/SERT MED/planilhas_de_faturamento',
    },
    'falcon': {
        'nome': 'Falcon',
        'pasta': '/Users/lucaspiau/Library/CloudStorage/OneDrive-Pessoal/EXCEL COMPARTILHADO/FALCON/planilhas_de_faturamento',
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
    return None

def ler_aba(planilha, aba):
    try:
        df = pd.read_excel(planilha, sheet_name=aba, skiprows=14, usecols='B:T')
        if 'PACIENTE' not in df.columns:
            return pd.DataFrame()
        df = df[df['PACIENTE'].notna()]
        df = df[df['PACIENTE'].astype(str).str.strip() != '']
        if df.empty:
            return pd.DataFrame()
        df['DATA'] = pd.to_datetime(df['DATA'], errors='coerce')
        df = df[df['DATA'].notna()]
        return df
    except Exception as e:
        print(f"    ⚠️  Erro ao ler aba '{aba}': {e}")
        return pd.DataFrame()

def ler_planilha(planilha):
    try:
        xl = pd.ExcelFile(planilha)
        abas = xl.sheet_names
        abas_adulto = [a for a in abas if 'ADULTO' in a.upper()]
        abas_neo    = [a for a in abas if 'NEONATAL' in a.upper()]
        frames_adulto = [ler_aba(planilha, a) for a in abas_adulto]
        frames_neo    = [ler_aba(planilha, a) for a in abas_neo]
        df_adulto = pd.concat([f for f in frames_adulto if not f.empty], ignore_index=True) if frames_adulto else pd.DataFrame()
        df_neo    = pd.concat([f for f in frames_neo    if not f.empty], ignore_index=True) if frames_neo    else pd.DataFrame()
        return df_adulto, df_neo
    except Exception as e:
        print(f"    ❌ Erro ao abrir planilha: {e}")
        return pd.DataFrame(), pd.DataFrame()

# ── CONEXÃO ───────────────────────────────────────────────────────────────────
conn = psycopg2.connect(
    host=DB_HOST, port=DB_PORT,
    dbname=DB_NAME, user=DB_USER, password=DB_PASS
)
cursor = conn.cursor()

# Busca todas as datas já existentes no banco
cursor.execute('SELECT empresa, data_corte FROM kpi_historico')
datas_existentes = {(r[0], str(r[1])) for r in cursor.fetchall()}
print(f"📊 Registros já no banco: {len(datas_existentes)}\n")

# ── PROCESSAR CADA EMPRESA ────────────────────────────────────────────────────
total_inseridos = 0
total_ignorados = 0
total_erros = 0

for chave, empresa in EMPRESAS.items():
    pasta = empresa['pasta']
    if not os.path.exists(pasta):
        print(f"❌ [{empresa['nome']}] Pasta não encontrada: {pasta}")
        continue

    arquivos = sorted(glob.glob(f"{pasta}/**/*.xlsx", recursive=True) + glob.glob(f"{pasta}/**/*.xls", recursive=True))
    if not arquivos:
        print(f"⚠️  [{empresa['nome']}] Nenhum arquivo encontrado em {pasta}")
        continue

    print(f"\n🏥 [{empresa['nome']}] {len(arquivos)} arquivo(s) encontrado(s)")

    for planilha in arquivos:
        nome_arquivo = os.path.basename(planilha)
        print(f"  📂 {nome_arquivo}")

        df_adulto, df_neo = ler_planilha(planilha)
        df_total = pd.concat([df_adulto, df_neo], ignore_index=True)

        if df_total.empty:
            print(f"    ⚠️  Sem dados válidos")
            continue

        col_km = coluna_km(df_total)
        if col_km is None:
            print(f"    ⚠️  Coluna KM não encontrada — usando 0")

        dias = sorted(df_total['DATA'].dt.date.unique())

        for dia in dias:
            dia_str = str(dia)
            if (chave, dia_str) in datas_existentes:
                total_ignorados += 1
                continue

            try:
                df_dia_adulto = df_adulto[df_adulto['DATA'].dt.date == dia] if not df_adulto.empty else pd.DataFrame()
                df_dia_neo    = df_neo[df_neo['DATA'].dt.date == dia]    if not df_neo.empty    else pd.DataFrame()
                df_dia        = pd.concat([df_dia_adulto, df_dia_neo], ignore_index=True)

                # Acumulado até esse dia (para previsão)
                df_ate_dia   = df_total[df_total['DATA'].dt.date <= dia]
                dias_uteis   = df_ate_dia['DATA'].dt.date.nunique()
                dias_no_mes  = calendar.monthrange(dia.year, dia.month)[1]

                valor_consolidado  = float(df_ate_dia['VALOR TOTAL'].sum())
                faturamento_dia    = float(df_dia['VALOR TOTAL'].sum())
                km_dia             = float(df_dia[col_km].sum()) if col_km else 0.0
                remocoes_dia       = float(len(df_dia))
                ticket_medio       = float(df_dia['VALOR TOTAL'].mean()) if len(df_dia) > 0 else 0.0
                media_rem_dia      = float(len(df_ate_dia) / dias_uteis)
                media_fat_dia      = float(df_ate_dia['VALOR TOTAL'].sum() / dias_uteis)
                previsao_remocoes  = int(round(media_rem_dia * dias_no_mes))
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
                datas_existentes.add((chave, dia_str))
                total_inseridos += 1

            except Exception as e:
                print(f"    ❌ Erro no dia {dia_str}: {e}")
                total_erros += 1

conn.commit()
conn.close()

print(f"\n{'='*50}")
print(f"✅ Inseridos:  {total_inseridos}")
print(f"⏭️  Ignorados:  {total_ignorados} (já existiam)")
print(f"❌ Erros:      {total_erros}")
