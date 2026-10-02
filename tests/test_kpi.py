"""Testes sem banco e sem Streamlit rodando: kpi_calc, montar_linhas do ETL e
inspeção do fonte dos dashboards."""
import ast
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from kpi_calc import (
    calcular_kpis_empresa,
    datas_corte_ref_por_mes,
    dias_corridos_periodo,
)
from atualizar_kpi_multi import (
    EMPRESAS,
    encontrar_planilha,
    mes_anterior,
    montar_linhas,
    padrao_planilha,
    substituir_mes,
    validar_mes_planilha,
)

RAIZ = Path(__file__).resolve().parent.parent


def linhas_kpi(empresa, dias):
    """df no formato de kpi_historico. dias: [(data, faturamento, adulto, neo, km)]."""
    registros = []
    acumulado = 0.0
    for d, fat, adulto, neo, km in dias:
        acumulado += fat
        registros.append({
            'empresa': empresa,
            'data_corte': d,
            'valor_consolidado': acumulado,
            'faturamento_dia': fat,
            'remocoes_adulto': adulto,
            'remocoes_neonatal': neo,
            'remocoes_dia': adulto + neo,
            'km_dia': km,
            'ticket_medio': fat / (adulto + neo),
            'previsao_faturamento': 999.0,
            'previsao_remocoes': 9,
        })
    return pd.DataFrame(registros)


# 1. mês fechado com dias sem linha → divisor = dias do mês
def test_mes_fechado_divide_pelos_dias_do_mes():
    df = linhas_kpi('maismed', [
        (date(2026, 8, 3), 3100.0, 2, 0, 100.0),
        (date(2026, 8, 10), 3100.0, 1, 1, 200.0),
        (date(2026, 8, 20), 3100.0, 2, 0, 320.0),  # só 3 dias com linha
    ])
    kpis = calcular_kpis_empresa(df, hoje=date(2026, 10, 2))

    assert kpis['mes_fechado'] is True
    assert kpis['dias_corridos'] == 31
    assert kpis['faturamento_dia'] == pytest.approx(9300.0 / 31)
    assert kpis['remocoes_dia'] == pytest.approx(6 / 31)
    assert kpis['km_dia'] == pytest.approx(620.0 / 31)


def test_mes_fechado_ignora_data_corte_ref():
    df = linhas_kpi('alfa', [(date(2026, 2, 5), 100.0, 1, 0, 10.0)])
    kpis = calcular_kpis_empresa(df, hoje=date(2026, 10, 2), data_corte_ref=date(2026, 2, 5))
    assert kpis['dias_corridos'] == 28


# 2. mês corrente, empresa com carga atrasada → mesmo divisor das demais
def test_mes_corrente_empresa_atrasada_usa_divisor_comum():
    hoje = date(2026, 10, 20)
    df_mes = pd.concat([
        linhas_kpi('sert', [(date(2026, 10, d), 1000.0, 1, 0, 50.0) for d in (1, 9, 18)]),
        linhas_kpi('falcon', [(date(2026, 10, d), 1000.0, 1, 0, 50.0) for d in (2, 17)]),
        linhas_kpi('maismed', [(date(2026, 10, d), 1000.0, 1, 0, 50.0) for d in (3, 16)]),  # atrasada
    ], ignore_index=True)
    ref = datas_corte_ref_por_mes(df_mes)[(2026, 10)]
    assert ref == date(2026, 10, 18)

    divisores = {
        emp: calcular_kpis_empresa(df_mes[df_mes['empresa'] == emp], hoje=hoje, data_corte_ref=ref)['dias_corridos']
        for emp in ('sert', 'falcon', 'maismed')
    }
    assert divisores == {'sert': 18, 'falcon': 18, 'maismed': 18}

    kpis_mm = calcular_kpis_empresa(df_mes[df_mes['empresa'] == 'maismed'], hoje=hoje, data_corte_ref=ref)
    assert kpis_mm['faturamento_dia'] == pytest.approx(2000.0 / 18)  # e não ÷16
    assert kpis_mm['mes_fechado'] is False


def test_mes_corrente_sem_ref_falha_em_vez_de_usar_divisor_da_empresa():
    df = linhas_kpi('maismed', [(date(2026, 10, 3), 1000.0, 1, 0, 50.0)])
    with pytest.raises(ValueError):
        calcular_kpis_empresa(df, hoje=date(2026, 10, 20))


def test_mes_corrente_ref_tem_teto_em_hoje():
    df = linhas_kpi('sert', [(date(2026, 10, 3), 1000.0, 1, 0, 50.0)])
    kpis = calcular_kpis_empresa(df, hoje=date(2026, 10, 20), data_corte_ref=date(2026, 10, 25))
    assert kpis['dias_corridos'] == 20


def test_dias_corridos_periodo_historico():
    refs = {(2026, 8): date(2026, 8, 31), (2026, 10): date(2026, 10, 18)}
    # ago e set fechados (31 + 30) + out corrente até a maior data_corte (18)
    assert dias_corridos_periodo(2026, 8, 2026, 10, date(2026, 10, 20), refs) == 31 + 30 + 18
    # mês corrente sem nenhuma linha carregada não soma dias
    assert dias_corridos_periodo(2026, 9, 2026, 10, date(2026, 10, 20), {}) == 30


# 3. ticket médio = soma de valor / total de remoções (≠ média das médias)
def test_ticket_medio_ponderado_pelo_volume():
    df = linhas_kpi('alfa', [
        (date(2026, 8, 1), 1000.0, 1, 0, 10.0),  # ticket do dia 1000
        (date(2026, 8, 2), 600.0, 2, 1, 30.0),   # ticket do dia 200
    ])
    kpis = calcular_kpis_empresa(df, hoje=date(2026, 10, 2))

    assert kpis['ticket_medio'] == pytest.approx(1600.0 / 4)  # 400
    media_das_medias = df['ticket_medio'].mean()             # 600
    assert media_das_medias == pytest.approx(600.0)
    assert kpis['ticket_medio'] != pytest.approx(media_das_medias)


# 4. montar_linhas
def planilha_sintetica():
    """Fevereiro/2026 (28 dias) com dias sem remoção e volumes variados."""
    adulto, neo = [], []
    for dia, valores in {1: [500.0, 700.0], 4: [300.0], 15: [1000.0, 250.0, 125.5], 28: [800.0]}.items():
        for v in valores:
            adulto.append({'PACIENTE': 'X', 'DATA': pd.Timestamp(2026, 2, dia), 'VALOR TOTAL': v, 'KM TOTAL': 40.0})
    for dia, valores in {4: [2000.0], 20: [1500.0, 900.0], 28: [450.25]}.items():
        for v in valores:
            neo.append({'PACIENTE': 'Y', 'DATA': pd.Timestamp(2026, 2, dia), 'VALOR TOTAL': v, 'KM TOTAL': 60.0})
    return pd.DataFrame(adulto), pd.DataFrame(neo)


def test_montar_linhas_soma_dos_dias_igual_consolidado_da_ultima_linha():
    df_adulto, df_neo = planilha_sintetica()
    linhas = montar_linhas(df_adulto, df_neo)

    assert [l['data_corte'] for l in linhas] == [date(2026, 2, d) for d in (1, 4, 15, 20, 28)]
    total = df_adulto['VALOR TOTAL'].sum() + df_neo['VALOR TOTAL'].sum()
    assert sum(l['faturamento_dia'] for l in linhas) == pytest.approx(linhas[-1]['valor_consolidado'], abs=0.05)
    assert linhas[-1]['valor_consolidado'] == pytest.approx(total)
    assert sum(l['remocoes_adulto'] + l['remocoes_neonatal'] for l in linhas) == len(df_adulto) + len(df_neo)


def test_montar_linhas_previsao_do_ultimo_dia_igual_consolidado_quando_mes_completo():
    df_adulto, df_neo = planilha_sintetica()
    ultimo = montar_linhas(df_adulto, df_neo)[-1]

    assert ultimo['data_corte'] == date(2026, 2, 28)
    assert ultimo['previsao_faturamento'] == pytest.approx(ultimo['valor_consolidado'])
    assert ultimo['previsao_remocoes'] == len(df_adulto) + len(df_neo)


def test_montar_linhas_mantem_formulas_por_linha():
    df_adulto, df_neo = planilha_sintetica()
    dia4 = montar_linhas(df_adulto, df_neo)[1]

    assert dia4['data_corte'] == date(2026, 2, 4)
    assert dia4['remocoes_adulto'] == 1 and dia4['remocoes_neonatal'] == 1
    assert dia4['faturamento_dia'] == pytest.approx(2300.0)
    assert dia4['km_dia'] == pytest.approx(100.0)
    assert dia4['ticket_medio'] == pytest.approx(1150.0)
    assert dia4['valor_consolidado'] == pytest.approx(3500.0)
    # previsão = acumulado / dias corridos (4) × dias do mês (28)
    assert dia4['previsao_faturamento'] == pytest.approx(3500.0 / 4 * 28)
    assert dia4['previsao_remocoes'] == round(4 / 4 * 28)


class _CursorFalso:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.sql = []
        self.rowcount = 0

    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, sql, params=None): self.sql.append(sql)
    def fetchone(self): return self.respostas.pop(0)


class _ConexaoFalsa:
    """Imita o `with conn:` do psycopg2: commit sem erro, rollback com erro."""
    def __init__(self, respostas):
        self.cur = _CursorFalso(respostas)
        self.commits = self.rollbacks = 0

    def __enter__(self): return self
    def __exit__(self, tipo, *a):
        if tipo is None: self.commits += 1
        else: self.rollbacks += 1
        return False
    def cursor(self): return self.cur


def test_substituir_mes_faz_rollback_se_soma_nao_bate():
    linhas = montar_linhas(*planilha_sintetica())
    conn = _ConexaoFalsa(respostas=[(100.0,), (200.0,)])  # SUM ≠ consolidado
    with pytest.raises(RuntimeError):
        substituir_mes(conn, 'maismed', 2026, 2, linhas)
    assert (conn.commits, conn.rollbacks) == (0, 1)
    assert conn.cur.sql[0].lstrip().startswith('DELETE')


def test_substituir_mes_commita_quando_soma_bate():
    linhas = montar_linhas(*planilha_sintetica())
    total = linhas[-1]['valor_consolidado']
    conn = _ConexaoFalsa(respostas=[(total + 0.04,), (total,)])
    substituir_mes(conn, 'maismed', 2026, 2, linhas)
    assert (conn.commits, conn.rollbacks) == (1, 0)
    assert sum('INSERT' in s for s in conn.cur.sql) == len(linhas)


# 5. localização/validação da planilha (virada de mês e de ano)
def test_padrao_planilha_monta_caminho_com_ano_e_sufixo_do_ano():
    pasta_alfa = EMPRESAS['alfa']['pasta']
    assert padrao_planilha(pasta_alfa, 2026, 9) == f"{pasta_alfa}/2026/09_*26.xlsx"
    assert padrao_planilha(pasta_alfa, 2027, 1) == f"{pasta_alfa}/2027/01_*27.xlsx"

    pasta_mm = EMPRESAS['maismed']['pasta']
    assert padrao_planilha(pasta_mm, 2026, 9) == f"{pasta_mm}/2026/09_*26.xlsx"
    assert padrao_planilha(pasta_mm, 2027, 1) == f"{pasta_mm}/2027/01_*27.xlsx"


@pytest.mark.parametrize('ano_mes, esperado', [
    ((2027, 1), (2026, 12)),
    ((2026, 10), (2026, 9)),
])
def test_mes_anterior(ano_mes, esperado):
    assert mes_anterior(*ano_mes) == esperado


def test_validar_mes_planilha_rejeita_mesmo_mes_ano_diferente():
    df = pd.DataFrame({'DATA': pd.to_datetime(['2026-09-05', '2027-09-06'])})
    with pytest.raises(ValueError):
        validar_mes_planilha(df, 2026, 9)


def test_validar_mes_planilha_aceita_quando_tudo_bate():
    df = pd.DataFrame({'DATA': pd.to_datetime(['2026-09-01', '2026-09-30'])})
    validar_mes_planilha(df, 2026, 9)  # não levanta


def test_encontrar_planilha_retorna_none_se_nao_existe(tmp_path):
    assert encontrar_planilha(str(tmp_path), 2026, 9) is None


def test_encontrar_planilha_retorna_unico_arquivo(tmp_path):
    pasta_ano = tmp_path / "2026"
    pasta_ano.mkdir()
    arquivo = pasta_ano / "09_fat26.xlsx"
    arquivo.touch()
    assert encontrar_planilha(str(tmp_path), 2026, 9) == str(arquivo)


def test_encontrar_planilha_aborta_se_mais_de_um_arquivo(tmp_path):
    pasta_ano = tmp_path / "2026"
    pasta_ano.mkdir()
    (pasta_ano / "09_fat26.xlsx").touch()
    (pasta_ano / "09_outra26.xlsx").touch()

    with pytest.raises(RuntimeError):
        encontrar_planilha(str(tmp_path), 2026, 9)


# 6. dashboards sem fórmula de card (inspeção do fonte)
FONTES_DASHBOARD = ['dashboard_todas.py', 'dashboard_alfa_humanize.py',
                    'dashboard_sert_falcon_maismed.py', 'ui.py']


@pytest.mark.parametrize('arquivo', FONTES_DASHBOARD)
def test_dashboards_nao_calculam_kpi(arquivo):
    fonte = (RAIZ / arquivo).read_text(encoding='utf-8')
    assert '.mean(' not in fonte

    proibidos = []
    for no in ast.walk(ast.parse(fonte)):
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute) \
                and no.func.attr in {'mean', 'sum', 'count', 'median'}:
            proibidos.append(f"linha {no.lineno}: .{no.func.attr}()")
        if isinstance(no, ast.BinOp) and isinstance(no.op, (ast.Div, ast.FloorDiv)):
            proibidos.append(f"linha {no.lineno}: divisão")
    assert proibidos == []


@pytest.mark.parametrize('arquivo', FONTES_DASHBOARD[:3])
def test_dashboards_usam_ui_compartilhada(arquivo):
    fonte = (RAIZ / arquivo).read_text(encoding='utf-8')
    assert 'render_dashboard_mensal(' in fonte
    assert 'def brl' not in fonte and 'def num' not in fonte and 'def carregar_dados' not in fonte


def test_ui_tira_numeros_do_kpi_calc():
    fonte = (RAIZ / 'ui.py').read_text(encoding='utf-8')
    assert 'calcular_kpis_empresa(df_emp, hoje=hoje, data_corte_ref=data_corte_ref)' in fonte
