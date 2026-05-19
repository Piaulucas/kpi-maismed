# KPI Dashboard — Mais Med UTI Móvel

Dashboard de monitoramento de KPIs operacionais e financeiros para empresas de UTI móvel contratadas pela SESAB (Secretaria de Saúde do Estado da Bahia).

## O que faz

Processa dados de faturamento mensais de até 5 empresas simultâneas, calcula indicadores-chave e exibe painéis interativos com atualização automática a cada 5 minutos.

## Stack

- **Python** · Pandas · psycopg2
- **Streamlit** — interface dos dashboards
- **PostgreSQL / Supabase** — armazenamento dos KPIs históricos
- **Plotly** — gráficos de evolução diária
- **Excel (OneDrive)** — fonte primária dos dados de faturamento

## Arquitetura

```
Planilha Excel (OneDrive)
        ↓
atualizar_kpi_multi.py        ← pipeline de extração e carga (5 empresas)
        ↓
PostgreSQL (Supabase)
        ↓
dashboard_todas.py                    ← dashboard consolidado (todas as empresas)
dashboard_sert_falcon_maismed.py      ← dashboard por grupo
dashboard_alfa_humanize.py            ← dashboard por grupo
```

## KPIs monitorados

| Indicador | Descrição |
|---|---|
| Valor Consolidado | Faturamento total até o corte |
| Remoções Adulto / Neonatal | Volume por tipo de atendimento |
| Remoções/dia | Média diária de atendimentos |
| Km/dia | Média diária de quilometragem |
| Ticket Médio | Receita por remoção |
| Previsão do Mês | Projeção de remoções e faturamento |

## Como rodar localmente

```bash
pip install -r requirements.txt
```

Crie o arquivo `.env` com as credenciais do banco:

```
DB_HOST=...
DB_PORT=5432
DB_NAME=postgres
DB_USER=...
DB_PASS=...
```

Atualize o banco com os dados de uma empresa:

```bash
python atualizar_kpi_multi.py maismed
```

Inicie o dashboard consolidado:

```bash
streamlit run dashboard_todas.py
```

## Contexto

Desenvolvido para uso interno na gestão de contratos SESAB de transporte inter-hospitalar. Os dados são provenientes de planilhas de faturamento compartilhadas via OneDrive. Este repositório centraliza o pipeline de ingestão — os dashboards por grupo de empresas estão nos repositórios [`kpi-sert-falcon-maismed`](https://github.com/Piaulucas/kpi-sert-falcon-maismed) e [`kpi-alfa-humanize`](https://github.com/Piaulucas/kpi-alfa-humanize).

---
Desenvolvido por [Lucas Piau](https://linkedin.com/in/lucaspiausantana) · Piau Gestão em Saúde
