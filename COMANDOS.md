# Comandos — KPI Mais Med

## Atualizar banco de dados
> Cada execução recalcula **todos os dias do mês** da planilha e substitui as linhas
> daquele mês/empresa no banco numa única transação (se algo falhar, nada é gravado).
> Editou um dia passado na planilha? É só rodar de novo — não precisa apagar nada antes.

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
> `rodar_kpis.sh` já faz isso sozinho nos primeiros 5 dias do mês — rode os
> comandos abaixo manualmente só se precisar reprocessar fora dessa janela.
>
> Importante: sempre passe `--ano` junto com `--mes`. Sem `--ano` o script usa
> o ano de hoje, que é o ano errado para o mês anterior quando ele cai no ano
> passado (virada de ano, ver exemplo abaixo).

```bash
cd ~/Desktop/Estudos/KPI_maismed
python3 atualizar_kpi_multi.py maismed --mes 09 --ano 2026; python3 atualizar_kpi_multi.py alfa --mes 09 --ano 2026; python3 atualizar_kpi_multi.py humanize --mes 09 --ano 2026; python3 atualizar_kpi_multi.py sert --mes 09 --ano 2026; python3 atualizar_kpi_multi.py falcon --mes 09 --ano 2026
```

### Exemplo — virada de ano (hoje é janeiro, mês anterior é dezembro do ano passado)
```bash
cd ~/Desktop/Estudos/KPI_maismed
python3 atualizar_kpi_multi.py maismed --mes 12 --ano 2026; python3 atualizar_kpi_multi.py alfa --mes 12 --ano 2026; python3 atualizar_kpi_multi.py humanize --mes 12 --ano 2026; python3 atualizar_kpi_multi.py sert --mes 12 --ano 2026; python3 atualizar_kpi_multi.py falcon --mes 12 --ano 2026
```

## Reprocessar um dia específico
> Mantido por compatibilidade: hoje equivale a rodar o mês daquela data (o mês inteiro
> é recalculado, não só o dia). Só confere, a mais, que o dia existe na planilha.

```bash
cd ~/Desktop/Estudos/KPI_maismed
python3 atualizar_kpi_multi.py <empresa> --reprocessar YYYY-MM-DD
```

### Exemplos
```bash
python3 atualizar_kpi_multi.py maismed --reprocessar 2026-05-15
python3 atualizar_kpi_multi.py falcon --reprocessar 2026-05-10
```

## Rodar os testes
```bash
cd ~/Desktop/Estudos/KPI_maismed
python3 -m pip install -r requirements-dev.txt
python3 -m pytest -q
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
