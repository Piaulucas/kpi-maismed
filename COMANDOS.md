# Comandos — KPI Mais Med

## Atualizar banco de dados

### Todas as empresas
```bash
cd ~/Desktop/Estudos/KPI_maismed
python3 atualizar_kpi_multi.py maismed && python3 atualizar_kpi_multi.py alfa && python3 atualizar_kpi_multi.py humanize && python3 atualizar_kpi_multi.py sert && python3 atualizar_kpi_multi.py falcon
```

### Empresa específica
```bash
cd ~/Desktop/Estudos/KPI_maismed
python3 atualizar_kpi_multi.py maismed
python3 atualizar_kpi_multi.py alfa
python3 atualizar_kpi_multi.py humanize
python3 atualizar_kpi_multi.py sert
python3 atualizar_kpi_multi.py falcon
```

## Atualizar mês anterior (virada de mês)
> Use quando virar o mês e precisar inserir os últimos dias do mês anterior.

```bash
cd ~/Desktop/Estudos/KPI_maismed
python3 atualizar_kpi_multi.py maismed --mes 09 && python3 atualizar_kpi_multi.py alfa --mes 09 && python3 atualizar_kpi_multi.py humanize --mes 09 && python3 atualizar_kpi_multi.py sert --mes 09 && python3 atualizar_kpi_multi.py falcon --mes 09
```

## Reprocessar um dia específico
> Use quando corrigir um valor na planilha após já ter inserido no banco.
> O script deleta o registro daquele dia e reinsere com os dados atuais.

```bash
cd ~/Desktop/Estudos/KPI_maismed
python3 atualizar_kpi_multi.py <empresa> --reprocessar YYYY-MM-DD
```

### Exemplos
```bash
python3 atualizar_kpi_multi.py maismed --reprocessar 2026-05-15
python3 atualizar_kpi_multi.py falcon --reprocessar 2026-05-10
```

## Deletar um mês inteiro e reinserir (correção em massa)
```sql
-- 1. Rodar no Supabase SQL Editor
DELETE FROM kpi_historico
WHERE EXTRACT(YEAR FROM data_corte) = 2026
  AND EXTRACT(MONTH FROM data_corte) = 6;
```
```bash
-- 2. Reinserir via script
cd ~/Desktop/Estudos/KPI_maismed
python3 atualizar_kpi_multi.py maismed && python3 atualizar_kpi_multi.py alfa && python3 atualizar_kpi_multi.py humanize && python3 atualizar_kpi_multi.py sert && python3 atualizar_kpi_multi.py falcon
```

## Carga histórica (uso único)
```bash
cd ~/Desktop/Estudos/KPI_maismed
python3 carga_historica.py
```

## Rodar dashboard localmente
```bash
cd ~/Desktop/Estudos/KPI_maismed
python3 -m streamlit run dashboard_todas.py
```

## Git — subir alterações
```bash
cd ~/Desktop/Estudos/KPI_maismed
git add . && git commit -m "mensagem" && git push
```

## Verificar total faturado por empresa e período
```sql
SELECT SUM(faturamento_dia) AS total_faturado
FROM kpi_historico
WHERE empresa = 'falcon'
  AND data_corte BETWEEN '2026-05-01' AND '2026-05-29';
```

## Status da carga automática (rodar_kpis.py)
> A cada execução real, o resumo vai para o `kpi_cron.log` (que guarda só as últimas
> ~2.000 linhas), aparece numa janela e num banner do macOS. Nada é apagado do banco
> em caso de aviso ou falha: a empresa/mês com problema simplesmente não é carregada.

| Status | Significado | O que fazer |
|---|---|---|
| `OK` | Mês da empresa recalculado e gravado. | Nada. |
| `AVISO — planilha sem lançamentos` | A planilha existe, mas não tem nenhuma linha, e o banco também não tem dias desse mês. | Normal no começo do mês. Se já deveria ter lançamentos, confira o arquivo. |
| `AVISO — planilha do mês ainda não criada` | Dia 1 do mês e a planilha do mês corrente ainda não existe. | Nada; criar a planilha quando começar o mês. |
| `FALHA — planilha não encontrada` | Não existe arquivo `MM_*AA.xlsx` na pasta do ano (fora do dia 1). | Criar/renomear a planilha no OneDrive e rodar de novo. |
| `FALHA — DATA ERRADA` | Há linha com data de outro mês/ano. As linhas abaixo dizem aba, linha do Excel, data, paciente (3 letras) e valor. | Corrigir a DATA naquela linha da planilha e rodar de novo. |
| `FALHA — LANÇAMENTO SEM PACIENTE` | Linha com DATA (e valor) mas sem PACIENTE. Linhas sem paciente **e** sem data (totais, linhas em branco) são ignoradas. | Preencher o paciente ou apagar a linha na planilha e rodar de novo. |
| `FALHA — DATA VAZIA OU INVÁLIDA` | Linha com paciente mas DATA vazia ou que não é data. | Preencher a DATA naquela linha e rodar de novo. |
| `FALHA — planilha vazia, mas o banco tem N dias deste mês…` | A planilha veio vazia, mas o mês já tinha sido carregado: arquivo trocado, apagado ou corrompido. | Verificar o arquivo no OneDrive (versões anteriores). O banco não foi alterado. |
| `FALHA — <mensagem>` | Qualquer outro erro do ETL (data inválida, banco fora do ar, soma não confere...). | Ler a mensagem e o trecho daquela empresa no `kpi_cron.log`. |

Códigos de saída do `atualizar_kpi_multi.py`: `0` OK · `1` erro · `2` planilha não
encontrada · `3` data fora do mês · `4` planilha sem lançamentos · `5` lançamento sem
paciente · `6` data vazia ou inválida.

## Links
- Dashboard todas as empresas: https://dashboardtodaspy-2bzkn4aywu2yji5hhpoezx.streamlit.app
- Dashboard Sert + Falcon + Mais Med: https://dashboardsertfalconmaismedpy-bt6kkmur69smimkovgistp.streamlit.app
- Dashboard Alfa + Humanize: https://dashboardalfahumanizepy-...streamlit.app
- Supabase: https://supabase.com/dashboard/project/ltfvmvpijonkhmuhzflk
- GitHub: https://github.com/Piaulucas/kpi-maismed
