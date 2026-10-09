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
import warnings

# Aviso inofensivo do openpyxl em planilhas com área de impressão por fórmula;
# só poluía o log. Os demais warnings continuam aparecendo.
warnings.filterwarnings('ignore', message='Print area cannot be set to Defined name',
                        category=UserWarning)

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
# Linha com data fora do mês/ano da planilha: a carga da empresa é bloqueada.
EXIT_DATA_FORA_DO_MES = 3
# Planilha existe mas não tem nenhum lançamento (e o banco também não tem o mês).
EXIT_PLANILHA_VAZIA = 4
# Lançamento com DATA preenchida mas sem PACIENTE: a carga da empresa é bloqueada.
EXIT_LANCAMENTO_SEM_PACIENTE = 5
# Lançamento com PACIENTE mas DATA vazia ou que não é data.
EXIT_DATA_INVALIDA = 6

# Linhas que o rodar_kpis.py extrai e mostra no resumo, sem parsear texto livre.
PREFIXO_DETALHE = 'DETALHE: '

# Linhas acima do cabeçalho da tabela em cada aba.
LINHAS_ANTES_DO_CABECALHO = 14

# ── LEITURA ───────────────────────────────────────────────────────────────────
def coluna_km(df):
    for col in df.columns:
        if 'KM TOTAL' in col.upper().strip():
            return col
    raise ValueError(f"Coluna KM TOTAL não encontrada. Colunas: {list(df.columns)}")

def ler_aba(planilha, aba):
    """Lê uma aba. Guarda em _ABA e _LINHA a aba e o número da linha no Excel
    de cada lançamento, para as mensagens de erro apontarem onde corrigir."""
    df = pd.read_excel(planilha, sheet_name=aba, skiprows=LINHAS_ANTES_DO_CABECALHO, usecols='B:T')
    df['_ABA'] = aba
    # índice 0 = primeira linha após as puladas e o cabeçalho (ambos 1-based no Excel)
    df['_LINHA'] = df.index + LINHAS_ANTES_DO_CABECALHO + 2
    # Filtra ANTES de qualquer conversão para string: astype(str) transformava
    # paciente vazio no texto "nan", e linhas de total passavam pelo filtro.
    sem_paciente = vazio(df['PACIENTE'])
    sem_data     = vazio(df['DATA'])
    # Sem paciente e sem data: linha de total ou em branco — descartada.
    manter = ~(sem_paciente & sem_data)
    df, sem_paciente = df[manter].copy(), sem_paciente[manter]
    if df.empty:
        return pd.DataFrame()
    # Paciente vazio vira '' (nunca "nan"); detalhes_sem_paciente bloqueia a carga.
    df['PACIENTE'] = [('' if s else str(v).strip()) for v, s in zip(df['PACIENTE'], sem_paciente)]
    # Data vazia ou que não é data vira NaT; detalhes_data_invalida bloqueia a carga.
    df['DATA'] = pd.to_datetime(df['DATA'], errors='coerce')
    return df

def vazio(serie):
    """True onde o valor é NaN, só espaços ou o texto "nan"."""
    return serie.map(lambda v: pd.isna(v) or (isinstance(v, str) and v.strip().lower() in ('', 'nan')))

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
def formatar_brl(valor):
    """8057.35 -> 'R$ 8.057,35'."""
    if pd.isna(valor):
        return 'R$ —'
    return 'R$ ' + f"{float(valor):,.2f}".replace(',', '_').replace('.', ',').replace('_', '.')

def _detalhe(r, paciente=None):
    """'aba ADULTO-PED, linha 32: 07/10/2023 · MAV*** · R$ 8.057,35'.
    O paciente vai abreviado (3 letras) porque a linha acaba em log e janela."""
    data = f"{r['DATA']:%d/%m/%Y}" if pd.notna(r['DATA']) else 'data vazia ou inválida'
    if paciente is None:
        paciente = str(r['PACIENTE']).strip()[:3] + '***'
    return (f"aba {r.get('_ABA', '?')}, linha {r.get('_LINHA', '?')}: "
            f"{data} · {paciente} · {formatar_brl(r.get('VALOR TOTAL'))}")

def detalhes_sem_paciente(df_total):
    """Lançamentos com data (ou algo na coluna DATA) mas sem paciente."""
    return [_detalhe(r, 'sem paciente') for _, r in df_total[df_total['PACIENTE'] == ''].iterrows()]

def detalhes_data_invalida(df_total):
    """Lançamentos com paciente mas DATA vazia ou que não é data."""
    return [_detalhe(r) for _, r in df_total[df_total['DATA'].isna()].iterrows()]

def detalhes_fora_do_mes(df_total, ano, mes):
    """Uma linha legível por lançamento com data fora de (ano, mes)."""
    datas = df_total['DATA']
    fora = df_total[datas.notna() & ((datas.dt.year != ano) | (datas.dt.month != mes))]
    return [_detalhe(r) for _, r in fora.iterrows()]

def checar_planilha_vazia(conectar, chave, ano, mes):
    """Planilha sem lançamentos: (código de saída, mensagem). Só faz SELECT —
    nada é apagado. Se o banco já tem dias do mês, a planilha vazia é suspeita
    (arquivo trocado/apagado) e vira falha em vez de aviso."""
    inicio = date(ano, mes, 1)
    fim    = date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1)
    conn = conectar()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT COUNT(*) FROM kpi_historico '
                'WHERE empresa = %s AND data_corte >= %s AND data_corte < %s',
                (chave, inicio, fim)
            )
            dias = int(cursor.fetchone()[0])
    finally:
        conn.close()
    if dias:
        return 1, f"planilha vazia, mas o banco tem {dias} dias deste mês — verifique o arquivo"
    return EXIT_PLANILHA_VAZIA, "planilha sem lançamentos"

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

    # Caminho explícito: quando rodado pelo launchd (WorkingDirectory != cwd
    # de quem chama), load_dotenv() sem argumento não acharia o .env.
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

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

    def conectar():
        return psycopg2.connect(
            host=DB_HOST, port=DB_PORT,
            dbname=DB_NAME, user=DB_USER, password=DB_PASS
        )

    if df_total.empty:
        try:
            codigo, msg = checar_planilha_vazia(conectar, chave, ano, mes)
        except Exception as e:
            print(f"❌ [{empresa['nome']}] planilha sem lançamentos e falha ao consultar o banco: {e}")
            sys.exit(1)
        print(f"{'⚠️ ' if codigo == EXIT_PLANILHA_VAZIA else '❌'} [{empresa['nome']}] {msg}")
        sys.exit(codigo)

    # Cada problema bloqueia a empresa inteira em vez de pular a linha: pular
    # esconderia faturamento. O DELETE é por mês: uma data de outro mês/ano
    # seria inserida fora do intervalo apagado e contaminaria aquele mês.
    verificacoes = [
        (detalhes_sem_paciente(df_total), EXIT_LANCAMENTO_SEM_PACIENTE,
         "lançamento(s) com data mas sem paciente"),
        (detalhes_data_invalida(df_total), EXIT_DATA_INVALIDA,
         "lançamento(s) com data vazia ou inválida"),
        (detalhes_fora_do_mes(df_total, ano, mes), EXIT_DATA_FORA_DO_MES,
         f"linha(s) com data fora de {mes:02d}/{ano}"),
    ]
    for detalhes, codigo, descricao in verificacoes:
        if detalhes:
            print(f"❌ [{empresa['nome']}] A planilha tem {len(detalhes)} {descricao}. Corrija a planilha.")
            for d in detalhes:
                print(f"{PREFIXO_DETALHE}{d}")
            sys.exit(codigo)

    linhas = montar_linhas(df_adulto, df_neo)

    if reprocessar_dia and reprocessar_dia not in {str(l['data_corte']) for l in linhas}:
        print(f"❌ Data {reprocessar_dia} não encontrada na planilha.")
        sys.exit(1)

    conn = conectar()
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
