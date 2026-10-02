"""Cálculo de KPIs mensais por empresa, compartilhado entre os dashboards.

Fonte única de cálculo: dashboard_todas.py, dashboard_alfa_humanize.py,
dashboard_sert_falcon_maismed.py (via ui.py) e pages/dashboard_historico.py
não fazem conta própria de divisor nem de médias — tudo passa por aqui.

Regra do divisor (dias_corridos)
--------------------------------
- Mês fechado (o dia 1 do mês seguinte já chegou): número de dias do mês.
- Mês corrente: dias do dia 1 até `data_corte_ref`, com teto em `hoje`.
  `data_corte_ref` é a MAIOR data_corte entre TODAS as empresas carregadas
  naquele mês — não a da própria empresa. Assim uma empresa com carga atrasada
  usa o mesmo divisor das demais em vez de ficar com divisor menor e média
  inflada (caso real: Mais Med ÷28 enquanto as outras ÷30).
- Mês futuro: 0 dias.
"""
import calendar
from datetime import date

import pandas as pd


def _primeiro_dia_proximo_mes(ano, mes):
    return date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1)


def _como_date(valor):
    return pd.Timestamp(valor).date()


def mes_esta_fechado(ano, mes, hoje):
    """True quando o primeiro dia do mês seguinte já chegou."""
    return _primeiro_dia_proximo_mes(ano, mes) <= hoje


def dias_corridos_mes(ano, mes, hoje, data_corte_ref=None):
    """Divisor das médias diárias de um mês (ver regra no topo do módulo).

    `data_corte_ref` só é exigida no mês corrente; em mês fechado ou futuro é
    ignorada.
    """
    if mes_esta_fechado(ano, mes, hoje):
        return calendar.monthrange(ano, mes)[1]

    primeiro_dia = date(ano, mes, 1)
    if primeiro_dia > hoje:
        return 0

    if data_corte_ref is None:
        raise ValueError(
            f"data_corte_ref é obrigatória no mês corrente ({mes:02d}/{ano}): "
            "use a maior data_corte entre TODAS as empresas do mês."
        )
    ref = _como_date(data_corte_ref)
    if (ref.year, ref.month) != (ano, mes):
        raise ValueError(f"data_corte_ref {ref} fora do mês {mes:02d}/{ano}.")

    # Teto em hoje: se o ETL gravasse uma data_corte no futuro, o divisor não
    # deve contar dias que ainda não aconteceram.
    fim = min(ref, hoje)
    return max((fim - primeiro_dia).days + 1, 1)


def datas_corte_ref_por_mes(df):
    """{(ano, mes): maior data_corte do mês} sobre o df recebido.

    Para respeitar a regra do divisor, passe o df com TODAS as empresas (antes
    de qualquer filtro por empresa).
    """
    if df.empty:
        return {}
    datas = pd.to_datetime(df['data_corte'])
    maximos = datas.groupby([datas.dt.year, datas.dt.month]).max()
    return {(int(a), int(m)): ts.date() for (a, m), ts in maximos.items()}


def dias_corridos_periodo(ano_ini, mes_ini, ano_fim, mes_fim, hoje, refs):
    """Soma de dias_corridos_mes de cada mês do período (inclusive).

    `refs` é o dict de datas_corte_ref_por_mes(). Mês corrente sem nenhuma
    linha carregada conta 0 dias (ainda não há dado a dividir).
    """
    total = 0
    ano, mes = ano_ini, mes_ini
    while (ano, mes) <= (ano_fim, mes_fim):
        ref = refs.get((ano, mes))
        mes_corrente = not mes_esta_fechado(ano, mes, hoje) and date(ano, mes, 1) <= hoje
        if not (mes_corrente and ref is None):
            total += dias_corridos_mes(ano, mes, hoje, ref)
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return max(total, 1)


def calcular_kpis_empresa(df_emp, hoje=None, data_corte_ref=None):
    """Recebe o dataframe filtrado de uma empresa (linhas de kpi_historico de
    um único mês) e retorna um dict com os KPIs consolidados do mês.

    - data_corte_ref: maior data_corte entre TODAS as empresas do mês (o
      dashboard obtém com uma query própria, independente de quais empresas
      ele exibe). Obrigatória no mês corrente. Se vier menor que a data_corte
      da própria empresa, usa-se a da empresa (a ref é, por definição, >= ela).
    - dias_corridos: ver regra do divisor no topo do módulo.
    - faturamento_dia, remocoes_dia, km_dia: soma do mês / dias_corridos.
      kpi_historico só tem linha nos dias com movimento, então usar .mean()
      sobre as linhas existentes divide por "dias com movimento" e infla as
      médias — por isso a divisão é sempre por dias_corridos.
    - ticket_medio: valor_consolidado / total_remocoes (nunca média das médias
      diárias da coluna ticket_medio).
    - mes_fechado: True quando o mês já virou — usado para ocultar previsões.
    - previsao_faturamento / previsao_remocoes: vêm prontos da última linha
      (o ETL já calcula; não são recalculados aqui).
    """
    if hoje is None:
        hoje = date.today()

    corte_max = pd.to_datetime(df_emp['data_corte']).max().date()
    ano, mes = corte_max.year, corte_max.month

    if data_corte_ref is not None:
        data_corte_ref = max(_como_date(data_corte_ref), corte_max)
    dias_corridos = max(dias_corridos_mes(ano, mes, hoje, data_corte_ref), 1)

    valor_consolidado = df_emp['faturamento_dia'].sum()
    remocoes_adulto   = int(df_emp['remocoes_adulto'].sum())
    remocoes_neonatal = int(df_emp['remocoes_neonatal'].sum())
    total_remocoes    = remocoes_adulto + remocoes_neonatal

    faturamento_dia = valor_consolidado / dias_corridos
    remocoes_dia    = df_emp['remocoes_dia'].sum() / dias_corridos
    km_dia          = df_emp['km_dia'].sum() / dias_corridos
    ticket_medio    = valor_consolidado / total_remocoes if total_remocoes else 0.0

    ultimo = df_emp.sort_values("data_corte").iloc[-1]

    return {
        'dias_corridos': dias_corridos,
        'corte_max': corte_max,
        'valor_consolidado': valor_consolidado,
        'remocoes_adulto': remocoes_adulto,
        'remocoes_neonatal': remocoes_neonatal,
        'total_remocoes': total_remocoes,
        'faturamento_dia': faturamento_dia,
        'remocoes_dia': remocoes_dia,
        'km_dia': km_dia,
        'ticket_medio': ticket_medio,
        'mes_fechado': mes_esta_fechado(ano, mes, hoje),
        'previsao_faturamento': float(ultimo['previsao_faturamento']),
        'previsao_remocoes': int(ultimo['previsao_remocoes']),
        'ultimo': ultimo,
    }
