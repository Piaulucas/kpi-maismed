"""ETL planilha de faturamento → kpi_historico.

A cada execução, para a empresa e o mês processados, recalcula TODOS os dias
presentes na planilha e substitui as linhas daquele mês/empresa numa única
transação (DELETE do mês + INSERT de todos os dias). Assim, editar um dia
passado na planilha nunca deixa linha velha no banco: valor_consolidado e
previsões de todos os dias seguintes são recalculados juntos.
"""
import pandas as pd
from datetime import date, datetime
import calendar
import sys
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

# Diferença máxima aceita entre SUM(faturamento_dia) do mês e o
# valor_consolidado da última linha antes do COMMIT.
TOLERANCIA_CONSOLIDADO = 0.05

# rodar_kpis.sh usa este código para distinguir "planilha ainda não existe"
# (esperado no dia 1 do mês corrente) de uma falha de verdade.
EXIT_PLANILHA_NAO_ENCONTRADA = 2

# ── LEITURA ───────────────────────────────────────────────────────────────────
def coluna_km(df):
    for col in df.columns:
        if 'KM TOTAL' in col.upper().strip():
            return col
    raise ValueError(f"Coluna KM TOTAL não encontrada. Colunas: {list(df.columns)}")

def ler_aba(planilha, aba):
    df = pd.read_excel(planilha, sheet_name=aba, skiprows=14, usecols='B:T')
    df['PACIENTE'] = df['PACIENTE'].astype(str).str.strip()
    df = df[df['PACIENTE'].notna() & (df['PACIENTE'].astype(str).str.strip() != '')]
    if df.empty:
        return pd.DataFrame()
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

# ── LOCALIZAÇÃO DA PLANILHA (puro, sem banco) ─────────────────────────────────
def padrao_planilha(pasta_base, ano, mes):
    """Padrão de glob da planilha de `mes`/`ano`: a pasta base da empresa não
    tem ano — ele entra como subpasta e também no sufixo do nome do arquivo."""
    return f"{pasta_base}/{ano}/{mes:02d}_*{ano % 100:02d}.xlsx"

def encontrar_planilha(pasta_base, ano, mes):
    """Procura a planilha de `mes`/`ano`. Retorna o caminho ou None se não
    existir. Levanta RuntimeError se achar mais de um arquivo (ambíguo) —
    antes, o primeiro arquivo do glob era usado silenciosamente."""
    padrao = padrao_planilha(pasta_base, ano, mes)
    arquivos = sorted(glob.glob(padrao))
    if len(arquivos) > 1:
        raise RuntimeError(
            f"Mais de uma planilha encontrada para o padrão '{padrao}': {arquivos}. "
            f"Deixe só uma e rode de novo."
        )
    return arquivos[0] if arquivos else None

def mes_anterior(ano, mes):
    """(ano, mes) do mês anterior a (ano, mes). Em janeiro, o anterior é
    dezembro do ano anterior."""
    if mes == 1:
        return ano - 1, 12
    return ano, mes - 1

# ── VALIDAÇÃO (puro, sem banco) ───────────────────────────────────────────────
def validar_mes_planilha(df_total, ano, mes):
    """Levanta ValueError se a planilha tiver linha com data fora de
    (ano, mes). Compara ano e mês — não só o mês — para não misturar meses
    de anos diferentes (ex.: planilha de setembro/2026 com linha de
    setembro/2027)."""
    fora = df_total[(df_total['DATA'].dt.year != ano) | (df_total['DATA'].dt.month != mes)]
    if not fora.empty:
        datas = sorted({str(d) for d in fora['DATA'].dt.date})
        raise ValueError(
            f"A planilha de {mes:02d}/{ano} tem {len(fora)} linha(s) com data fora do "
            f"período: {datas}. Corrija a planilha."
        )

# ── CÁLCULO (puro, sem banco) ─────────────────────────────────────────────────
def montar_linhas(df_adulto, df_neo):
    """Uma linha de kpi_historico (sem empresa/data_registro) por dia presente
    na planilha, em ordem de data. Não acessa banco nem relógio.
    """
    df_total = pd.concat([df_adulto, df_neo], ignore_index=True)
    if df_total.empty:
        return []

    col_km = coluna_km(df_total)
    dias_no_mes = calendar.monthrange(df_total['DATA'].max().year, df_total['DATA'].max().month)[1]

    linhas = []
    for dia in sorted(df_total['DATA'].dt.date.unique()):
        df_dia_adulto = df_adulto[df_adulto['DATA'].dt.date == dia] if not df_adulto.empty else pd.DataFrame()
        df_dia_neo    = df_neo[df_neo['DATA'].dt.date == dia] if not df_neo.empty else pd.DataFrame()
        df_dia        = pd.concat([df_dia_adulto, df_dia_neo], ignore_index=True)

        df_ate_dia = df_total[df_total['DATA'].dt.date <= dia]

        # Dias corridos desde o dia 1 do mês até o dia de corte (inclusive)
        # Garante que previsão == consolidado quando o mês fecha
        primeiro_dia_mes = date(dia.year, dia.month, 1)
        dias_corridos = (dia - primeiro_dia_mes).days + 1

        valor_consolidado    = float(df_ate_dia['VALOR TOTAL'].sum())
        km_dia               = float(df_dia[col_km].sum())
        remocoes_dia         = float(len(df_dia))
        faturamento_dia      = float(df_dia['VALOR TOTAL'].sum())
        ticket_medio         = float(df_dia['VALOR TOTAL'].mean()) if len(df_dia) > 0 else 0.0
        media_rem_dia        = float(df_ate_dia['VALOR TOTAL'].count() / dias_corridos)
        media_fat_dia        = float(df_ate_dia['VALOR TOTAL'].sum() / dias_corridos)
        previsao_remocoes    = int(round(media_rem_dia * dias_no_mes))
        previsao_faturamento = float(media_fat_dia * dias_no_mes)

        linhas.append({
            'data_corte': dia,
            'valor_consolidado': valor_consolidado,
            'km_dia': km_dia,
            'remocoes_dia': remocoes_dia,
            'remocoes_adulto': len(df_dia_adulto),
            'remocoes_neonatal': len(df_dia_neo),
            'faturamento_dia': faturamento_dia,
            'ticket_medio': ticket_medio,
            'previsao_remocoes': previsao_remocoes,
            'previsao_faturamento': previsao_faturamento,
        })
    return linhas

# ── CARGA ─────────────────────────────────────────────────────────────────────
def substituir_mes(conn, chave, ano, mes, linhas):
    """DELETE do mês da empresa + INSERT de todas as linhas, numa transação.
    Antes do COMMIT confere SUM(faturamento_dia) == valor_consolidado da última
    linha; qualquer falha faz rollback e o banco fica como estava.
    """
    inicio = date(ano, mes, 1)
    fim    = date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1)
    hoje   = date.today().isoformat()

    with conn:  # psycopg2: commit ao sair sem erro, rollback se houver exceção
        with conn.cursor() as cursor:
            cursor.execute(
                'DELETE FROM kpi_historico WHERE empresa = %s AND data_corte >= %s AND data_corte < %s',
                (chave, inicio, fim)
            )
            removidas = cursor.rowcount

            for l in linhas:
                cursor.execute('''
                    INSERT INTO kpi_historico
                        (data_registro, data_corte, valor_consolidado, km_dia, remocoes_dia,
                         remocoes_adulto, remocoes_neonatal, faturamento_dia, ticket_medio,
                         previsao_remocoes, previsao_faturamento, empresa)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    hoje,
                    str(l['data_corte']),
                    l['valor_consolidado'],
                    l['km_dia'],
                    l['remocoes_dia'],
                    l['remocoes_adulto'],
                    l['remocoes_neonatal'],
                    l['faturamento_dia'],
                    l['ticket_medio'],
                    l['previsao_remocoes'],
                    l['previsao_faturamento'],
                    chave,
                ))

            cursor.execute(
                'SELECT COALESCE(SUM(faturamento_dia), 0) FROM kpi_historico '
                'WHERE empresa = %s AND data_corte >= %s AND data_corte < %s',
                (chave, inicio, fim)
            )
            soma_dias = float(cursor.fetchone()[0])
            cursor.execute(
                'SELECT valor_consolidado FROM kpi_historico '
                'WHERE empresa = %s AND data_corte >= %s AND data_corte < %s '
                'ORDER BY data_corte DESC LIMIT 1',
                (chave, inicio, fim)
            )
            consolidado = float(cursor.fetchone()[0])
            if abs(soma_dias - consolidado) > TOLERANCIA_CONSOLIDADO:
                raise RuntimeError(
                    f"SUM(faturamento_dia) = {soma_dias:,.2f} difere do valor_consolidado "
                    f"da última linha = {consolidado:,.2f} — rollback, banco inalterado."
                )
    return removidas

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main(argv):
    import psycopg2
    from dotenv import load_dotenv

    load_dotenv()

    DB_HOST = os.getenv('DB_HOST')
    DB_PORT = os.getenv('DB_PORT', '5432')
    DB_NAME = os.getenv('DB_NAME')
    DB_USER = os.getenv('DB_USER')
    DB_PASS = os.getenv('DB_PASS')

    if not all([DB_HOST, DB_NAME, DB_USER, DB_PASS]):
        print("❌ Variáveis de ambiente do banco não configuradas. Verifique o arquivo .env")
        sys.exit(1)

    if len(argv) < 2:
        print("Uso: python3 atualizar_kpi_multi.py <empresa> [--mes M] [--ano AAAA] [--reprocessar YYYY-MM-DD]")
        print(f"Empresas disponíveis: {', '.join(EMPRESAS.keys())}")
        sys.exit(1)

    chave = argv[1].lower()
    if chave not in EMPRESAS:
        print(f"❌ Empresa '{chave}' não encontrada.")
        sys.exit(1)

    # --reprocessar YYYY-MM-DD: mantido por compatibilidade. Como toda execução
    # já recalcula o mês inteiro, ele só escolhe o mês daquela data e confere
    # que o dia existe na planilha.
    reprocessar_dia = None
    if '--reprocessar' in argv:
        idx = argv.index('--reprocessar')
        if idx + 1 >= len(argv):
            print("❌ Informe a data após --reprocessar. Ex: --reprocessar 2026-05-15")
            sys.exit(1)
        reprocessar_dia = argv[idx + 1]
        try:
            datetime.strptime(reprocessar_dia, '%Y-%m-%d')
        except ValueError:
            print(f"❌ Data inválida: {reprocessar_dia}. Use o formato YYYY-MM-DD")
            sys.exit(1)
        print(f"🔄 Modo reprocessamento: {reprocessar_dia} (o mês inteiro será recalculado)")

    empresa = EMPRESAS[chave]

    # --mes: aceita 1 ou 2 dígitos. Sem --mes: usa o mês de hoje, ou o mês da
    # data em --reprocessar.
    if '--mes' in argv:
        idx = argv.index('--mes')
        if idx + 1 >= len(argv):
            print("❌ Informe o mês após --mes. Ex: --mes 9 ou --mes 09")
            sys.exit(1)
        try:
            mes = int(argv[idx + 1])
        except ValueError:
            print(f"❌ Mês inválido: '{argv[idx + 1]}'")
            sys.exit(1)
        if not 1 <= mes <= 12:
            print(f"❌ Mês inválido: '{argv[idx + 1]}'")
            sys.exit(1)
    elif reprocessar_dia:
        mes = int(reprocessar_dia[5:7])
    else:
        mes = date.today().month

    # --ano: sem --ano usa o ano de hoje, ou o ano da data em --reprocessar.
    if '--ano' in argv:
        idx = argv.index('--ano')
        if idx + 1 >= len(argv):
            print("❌ Informe o ano após --ano. Ex: --ano 2026")
            sys.exit(1)
        try:
            ano = int(argv[idx + 1])
        except ValueError:
            print(f"❌ Ano inválido: '{argv[idx + 1]}'")
            sys.exit(1)
    elif reprocessar_dia:
        ano = int(reprocessar_dia[0:4])
    else:
        ano = date.today().year

    try:
        PLANILHA = encontrar_planilha(empresa['pasta'], ano, mes)
    except RuntimeError as e:
        print(f"❌ [{empresa['nome']}] {e}")
        sys.exit(1)

    if PLANILHA is None:
        print(f"⚠️  Nenhuma planilha encontrada para {empresa['nome']} em {mes:02d}/{ano}")
        sys.exit(EXIT_PLANILHA_NAO_ENCONTRADA)

    print(f"📂 [{empresa['nome']}] Usando: {os.path.basename(PLANILHA)}")

    df_adulto, df_neo = ler_planilha(PLANILHA)
    df_total = pd.concat([df_adulto, df_neo], ignore_index=True)

    if df_total.empty:
        print(f"❌ Nenhum dado encontrado na planilha.")
        sys.exit(1)

    # Verifica datas inválidas
    nulos = df_total[df_total['DATA'].isna()]
    if not nulos.empty:
        print(f"❌ {len(nulos)} linha(s) com data inválida na planilha:")
        print(nulos[['PACIENTE', 'DATA']].to_string())
        sys.exit(1)

    # O DELETE é por mês: uma data de outro mês/ano na planilha seria
    # inserida fora do intervalo apagado e duplicaria/contaminaria aquele mês.
    try:
        validar_mes_planilha(df_total, ano, mes)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)

    linhas = montar_linhas(df_adulto, df_neo)

    if reprocessar_dia and reprocessar_dia not in {str(l['data_corte']) for l in linhas}:
        print(f"❌ Data {reprocessar_dia} não encontrada na planilha.")
        sys.exit(1)

    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT,
        dbname=DB_NAME, user=DB_USER, password=DB_PASS
    )
    try:
        removidas = substituir_mes(conn, chave, ano, mes, linhas)
    except Exception as e:
        print(f"❌ [{empresa['nome']}] Falha — nada foi gravado: {e}")
        sys.exit(1)
    finally:
        conn.close()

    for l in linhas:
        print(f"  ✅ {l['data_corte']} — {int(l['remocoes_dia'])} remoções · R$ {l['faturamento_dia']:,.2f}")

    total_faturado = sum(l['faturamento_dia'] for l in linhas)
    total_remocoes = sum(l['remocoes_adulto'] + l['remocoes_neonatal'] for l in linhas)
    print(f"\n📊 [{empresa['nome']}] {mes:02d}/{ano}: {len(linhas)} dia(s) inserido(s) "
          f"({removidas} linha(s) anterior(es) substituída(s)) · "
          f"total faturado R$ {total_faturado:,.2f} · {total_remocoes} remoções")


if __name__ == '__main__':
    main(sys.argv)
