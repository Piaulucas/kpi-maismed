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

Os 3 dashboards vivem neste repositório e compartilham a mesma lógica: `ui.py`
(layout e cards) e `kpi_calc.py` (todo o cálculo de KPI — nenhum dashboard faz
conta própria). Cada um é publicado como um app separado no Streamlit Cloud:

- Todas as empresas: https://dashboardtodaspy-2bzkn4aywu2yji5hhpoezx.streamlit.app
- Alfa Saúde + Humanize Life Care: https://kpi-alfa-humanize.streamlit.app
- Sert Med + Falcon + Mais Med: https://kpi-sert-falcon-maismed.streamlit.app

### Regra de cálculo (`kpi_calc.py`)

- Divisor das médias diárias (`faturamento_dia`, `remocoes_dia`, `km_dia`) é
  sempre **dias corridos do mês**, nunca "dias com movimento". No mês
  corrente, esse divisor usa uma **referência global**: a maior `data_corte`
  entre *todas* as empresas do mês (não a da própria empresa), para uma
  empresa com carga atrasada não ficar com divisor menor e média inflada.
- `ticket_medio` é sempre `valor_consolidado / total_remoções` (soma sobre
  soma), nunca a média das médias diárias.
- No mês fechado, o divisor é o número de dias do mês e as previsões ficam
  ocultas (previsão == consolidado).

### ETL (`atualizar_kpi_multi.py`)

A cada execução, para a empresa e o mês informados, o ETL lê a planilha,
recalcula todos os dias presentes nela e substitui as linhas daquele
mês/empresa em `kpi_historico` numa única transação (DELETE do mês + INSERT
de todos os dias, com conferência de soma antes do COMMIT). Rodar o mesmo
mês mais de uma vez é seguro.

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

Cada app no Streamlit Cloud precisa das credenciais do banco em
`st.secrets["database"]` (Settings → Secrets do app):

```toml
[database]
host = "..."
port = "5432"
dbname = "postgres"
user = "..."
password = "..."
```

## Agendamento

`rodar_kpis.sh` roda `atualizar_kpi_multi.py` para as 5 empresas todo dia às
15h via launchd (macOS) — ver `COMANDOS.md` para status, execução manual e
logs. Nos primeiros 5 dias do mês ele também roda o mês anterior, para pegar
os últimos dias que a planilha do mês anterior ainda recebe depois da virada.

Para rodar manualmente (todas as empresas, mês corrente):

```bash
./rodar_kpis.sh
```

## Contexto

Desenvolvido para uso interno na gestão de contratos SESAB de transporte inter-hospitalar. Os dados são provenientes de planilhas de faturamento compartilhadas via OneDrive.

---
Desenvolvido por [Lucas Piau](https://linkedin.com/in/lucaspiausantana) · Piau Gestão em Saúde
