#!/bin/bash
# Roda o atualizar_kpi_multi.py para todas as empresas
# Salva log em kpi_cron.log

SCRIPT_DIR="/Users/lucaspiau/Desktop/Estudos/KPI_maismed"
PYTHON="/usr/bin/python3"
LOG="$SCRIPT_DIR/kpi_cron.log"

echo "==============================" >> "$LOG"
echo "$(date '+%Y-%m-%d %H:%M:%S') — Iniciando atualização" >> "$LOG"

for empresa in maismed alfa humanize sert falcon; do
    echo "--- $empresa ---" >> "$LOG"
    $PYTHON "$SCRIPT_DIR/atualizar_kpi_multi.py" "$empresa" >> "$LOG" 2>&1
done

echo "$(date '+%Y-%m-%d %H:%M:%S') — Concluído" >> "$LOG"
