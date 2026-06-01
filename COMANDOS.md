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
python3 atualizar_kpi_multi.py maismed --mes 05 && python3 atualizar_kpi_multi.py alfa --mes 05 && python3 atualizar_kpi_multi.py humanize --mes 05 && python3 atualizar_kpi_multi.py sert --mes 05 && python3 atualizar_kpi_multi.py falcon --mes 05
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
  AND EXTRACT(MONTH FROM data_corte) = 5;
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

## Links
- Dashboard todas as empresas: https://dashboardtodaspy-2bzkn4aywu2yji5hhpoezx.streamlit.app
- Dashboard Sert + Falcon + Mais Med: https://dashboardsertfalconmaismedpy-bt6kkmur69smimkovgistp.streamlit.app
- Dashboard Alfa + Humanize: https://dashboardalfahumanizepy-...streamlit.app
- Supabase: https://supabase.com/dashboard/project/ltfvmvpijonkhmuhzflk
- GitHub: https://github.com/Piaulucas/kpi-maismed
