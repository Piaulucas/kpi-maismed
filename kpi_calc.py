"""Cálculo de KPIs mensais por empresa, compartilhado entre os dashboards.

Extraído de dashboard_todas.py (versão corrigida e validada) para eliminar a
duplicação dessa lógica — que existia com bugs divergentes — em
dashboard_alfa_humanize.py e dashboard_sert_falcon_maismed.py.
"""
from datetime import date

import pandas as pd


def calcular_kpis_empresa(df_emp, hoje=None):
    """Recebe o dataframe filtrado de uma empresa (linhas de kpi_historico)
    e retorna um dict com os KPIs consolidados do mês.

    - dias_corridos: dias do mês até a data de corte mais recente da empresa,
      com `hoje` como teto (min(corte_emp, hoje)). Guard defensivo: se o ETL
      gravasse uma data_corte no futuro, o divisor não deve contar dias que
      ainda não aconteceram.
    - faturamento_dia, remocoes_dia, km_dia: soma do mês / dias_corridos.
      kpi_historico só tem linha nos dias com movimento, então usar .mean()
      sobre as linhas existentes divide por "dias com movimento" e infla as
      médias — por isso a divisão é sempre por dias_corridos.
    - ticket_medio: valor_consolidado / total_remocoes.
    - mes_fechado: True quando o mês da empresa já virou (primeiro dia do mês
      seguinte já chegou) — usado para controlar a exibição da previsão.
    - previsao_faturamento / previsao_remocoes: vêm prontos da última linha
      (o ETL já calcula corretamente; não são recalculados aqui).
    """
    if hoje is None:
        hoje = date.today()

    datas_corte = pd.to_datetime(df_emp['data_corte'])
    corte_max = datas_corte.max().date()
    primeiro_dia_mes = date(corte_max.year, corte_max.month, 1)
    corte_emp = min(corte_max, hoje)
    dias_corridos = max((corte_emp - primeiro_dia_mes).days + 1, 1)

    valor_consolidado = df_emp['faturamento_dia'].sum()
    remocoes_adulto   = int(df_emp['remocoes_adulto'].sum())
    remocoes_neonatal = int(df_emp['remocoes_neonatal'].sum())
    total_remocoes    = remocoes_adulto + remocoes_neonatal

    faturamento_dia = valor_consolidado / dias_corridos
    remocoes_dia    = df_emp['remocoes_dia'].sum() / dias_corridos
    km_dia          = df_emp['km_dia'].sum() / dias_corridos
    ticket_medio    = valor_consolidado / total_remocoes if total_remocoes else 0.0

    ultimo = df_emp.sort_values("data_corte").iloc[-1]

    proximo_mes = (date(corte_max.year + 1, 1, 1) if corte_max.month == 12
                   else date(corte_max.year, corte_max.month + 1, 1))
    mes_fechado = proximo_mes <= hoje

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
        'mes_fechado': mes_fechado,
        'previsao_faturamento': float(ultimo['previsao_faturamento']),
        'previsao_remocoes': int(ultimo['previsao_remocoes']),
        'ultimo': ultimo,
    }
