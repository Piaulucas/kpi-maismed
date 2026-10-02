#!/bin/bash
# Roda o atualizar_kpi_multi.py para todas as empresas.
#
# Na virada do mês (dia de hoje <= 5), para cada empresa roda PRIMEIRO o mês
# anterior e DEPOIS o mês corrente — o ETL substitui o mês inteiro numa única
# transação, então rodar o mesmo mês mais de uma vez é seguro. Fora dessa
# janela, roda só o mês corrente.
#
# Falha de uma empresa/mês nunca interrompe as demais. No mês corrente, não
# achar a planilha no dia 1 é esperado (ainda não foi criada) e vira aviso;
# qualquer outra falha vira FALHA no resumo final.
#
# Uso:
#   ./rodar_kpis.sh                    # roda de verdade
#   ./rodar_kpis.sh --dry-run          # só imprime o que executaria (hoje real)
#   ./rodar_kpis.sh --dry-run AAAA-MM-DD  # idem, simulando outra data de "hoje"
#
# Salva log em kpi_cron.log

SCRIPT_DIR="/Users/lucaspiau/Desktop/Estudos/KPI_maismed"
PYTHON="/usr/bin/python3"
LOG="$SCRIPT_DIR/kpi_cron.log"

EMPRESAS=(maismed alfa humanize sert falcon)

DRY_RUN=false
if [ "$1" = "--dry-run" ]; then
    DRY_RUN=true
    HOJE="${2:-$(date '+%Y-%m-%d')}"
else
    HOJE="$(date '+%Y-%m-%d')"
fi

# (ano, mes) do mês anterior ao de $1 (formato YYYY-MM-DD). Em janeiro, o
# anterior é dezembro do ano anterior. Imprime "ANO MES" (mes com 2 dígitos).
# Usa `date -v-1m` (BSD date do macOS) para não reimplementar a aritmética de
# virada de ano na mão.
mes_anterior() {
    date -v-1m -j -f "%Y-%m-%d" "$1" "+%Y %m"
}

ANO_ATUAL=$(date -j -f "%Y-%m-%d" "$HOJE" "+%Y")
MES_ATUAL=$(date -j -f "%Y-%m-%d" "$HOJE" "+%m")
DIA_ATUAL=$(date -j -f "%Y-%m-%d" "$HOJE" "+%d")
read ANO_ANTERIOR MES_ANTERIOR <<< "$(mes_anterior "$HOJE")"

if $DRY_RUN; then
    echo "Hoje (simulado): $HOJE (dia $((10#$DIA_ATUAL)))"
    echo "Mês corrente: $ANO_ATUAL-$MES_ATUAL"
    echo "Mês anterior: $ANO_ANTERIOR-$MES_ANTERIOR"
    echo
    if [ "$((10#$DIA_ATUAL))" -le 5 ]; then
        echo "Dentro da janela de virada de mês (dia <= 5). Para cada empresa, executaria:"
        for empresa in "${EMPRESAS[@]}"; do
            echo "  $PYTHON atualizar_kpi_multi.py $empresa --mes $MES_ANTERIOR --ano $ANO_ANTERIOR"
            echo "  $PYTHON atualizar_kpi_multi.py $empresa --mes $MES_ATUAL --ano $ANO_ATUAL"
        done
    else
        echo "Fora da janela de virada de mês (dia > 5). Para cada empresa, executaria só:"
        for empresa in "${EMPRESAS[@]}"; do
            echo "  $PYTHON atualizar_kpi_multi.py $empresa --mes $MES_ATUAL --ano $ANO_ATUAL"
        done
    fi
    exit 0
fi

# resumo[i] = "empresa mes/ano: STATUS"
resumo=()

# Roda uma empresa/mês e registra o resultado no resumo e no log.
# $1=empresa $2=mes $3=ano $4=eh_mes_corrente (true/false)
rodar_empresa_mes() {
    local empresa="$1" mes="$2" ano="$3" eh_mes_corrente="$4"
    echo "--- $empresa ($mes/$ano) ---" >> "$LOG"
    $PYTHON "$SCRIPT_DIR/atualizar_kpi_multi.py" "$empresa" --mes "$mes" --ano "$ano" >> "$LOG" 2>&1
    local status_cod=$?

    local status
    if [ "$status_cod" -eq 0 ]; then
        status="OK"
    elif [ "$status_cod" -eq 2 ]; then
        # Planilha não encontrada. No mês corrente, dia 1, é esperado.
        if [ "$eh_mes_corrente" = true ] && [ "$((10#$DIA_ATUAL))" -eq 1 ]; then
            echo "⚠️  Aviso esperado (planilha do mês corrente ainda não existe no dia 1)." >> "$LOG"
            status="AVISO"
        else
            echo "❌ Planilha não encontrada (fora do esperado)." >> "$LOG"
            status="FALHA"
        fi
    else
        echo "❌ Falha ao processar $empresa ($mes/$ano) — código $status_cod." >> "$LOG"
        status="FALHA"
    fi
    resumo+=("$empresa $mes/$ano: $status")
}

echo "==============================" >> "$LOG"
echo "$(date '+%Y-%m-%d %H:%M:%S') — Iniciando atualização" >> "$LOG"

for empresa in "${EMPRESAS[@]}"; do
    if [ "$((10#$DIA_ATUAL))" -le 5 ]; then
        rodar_empresa_mes "$empresa" "$MES_ANTERIOR" "$ANO_ANTERIOR" false
    fi
    rodar_empresa_mes "$empresa" "$MES_ATUAL" "$ANO_ATUAL" true
done

echo "--- Resumo ---" >> "$LOG"
for linha in "${resumo[@]}"; do
    echo "$linha" >> "$LOG"
done

echo "$(date '+%Y-%m-%d %H:%M:%S') — Concluído" >> "$LOG"
