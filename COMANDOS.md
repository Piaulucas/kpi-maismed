# Comandos — KPI Mais Med

## Atualizar banco de dados

### Todas as empresas
```bash
cd ~/Desktop/Estudos/KPI_maismed
python3 atualizar_kpi_multi.py maismed && python3 atualizar_kpi_multi.py alfa && python3 atualizar_kpi_multi.py humanize && python3 atualizar_kpi_multi.py sert && python3 atualizar_kpi_multi.py falcon
```

### Empresa específica
```bash
python3 atualizar_kpi_multi.py maismed
python3 atualizar_kpi_multi.py alfa
python3 atualizar_kpi_multi.py humanize
python3 atualizar_kpi_multi.py sert
python3 atualizar_kpi_multi.py falcon
```

## Rodar dashboard localmente
```bash
cd ~/Desktop/Estudos/KPI_maismed
python3 -m streamlit run dashboard_todas.py
```

## Carga histórica (uso único)
```bash
cd ~/Desktop/Estudos/KPI_maismed
python3 carga_historica.py
```

## Git — subir alterações
```bash
cd ~/Desktop/Estudos/KPI_maismed
git add . && git commit -m "mensagem" && git push
```

## Links
- Dashboard todas as empresas: https://dashboardtodaspy-2bzkn4aywu2yji5hhpoezx.streamlit.app
- Dashboard Sert + Falcon + Mais Med: https://dashboardsertfalconmaismedpy-bt6kkmur69smimkovgistp.streamlit.app
- Dashboard Alfa + Humanize: https://dashboardalfahumanizepy-...streamlit.app
- Supabase: https://supabase.com/dashboard/project/ltfvmvpijonkhmuhzflk
- GitHub: https://github.com/Piaulucas/kpi-maismed
