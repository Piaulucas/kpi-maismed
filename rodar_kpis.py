#!/usr/bin/env python3
"""Roda atualizar_kpi_multi.py para as 5 empresas.

Modo virada de mês (sem --mes/--ano): nos primeiros 5 dias do mês, roda para
cada empresa PRIMEIRO o mês anterior e DEPOIS o mês corrente — o ETL
substitui o mês inteiro numa única transação, então rodar o mesmo mês mais de
uma vez é seguro. Fora dessa janela, roda só o mês corrente.

Falha de uma empresa/mês nunca interrompe as demais. No mês corrente, não
achar a planilha no dia 1 é esperado (ainda não foi criada) e vira AVISO;
qualquer outra falha vira FALHA no resumo final.

Modo --mes M --ano AAAA: roda as 5 empresas só daquele mês, sem lógica de
virada (uso: fechamento depois do dia 5, ou reprocessar um mês inteiro).
Nesse modo, planilha não encontrada é sempre FALHA.

Uso:
    rodar_kpis.py                        # roda de verdade (virada de mês)
    rodar_kpis.py --dry-run              # só imprime o que executaria (hoje real)
    rodar_kpis.py --dry-run AAAA-MM-DD   # idem, simulando outra data de "hoje"
    rodar_kpis.py --mes M --ano AAAA [--dry-run]   # roda só esse mês, 5 empresas

Salva log em kpi_cron.log (e imprime o resumo também no stdout).
"""
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from atualizar_kpi_multi import EMPRESAS, EXIT_PLANILHA_NAO_ENCONTRADA, mes_anterior

LOG = SCRIPT_DIR / "kpi_cron.log"


class ArgsInvalidos(Exception):
    """Argumentos de linha de comando inválidos (mensagem já amigável)."""


def parse_argv(argv):
    """argv (sem o nome do programa) -> dict com dry_run, hoje_str, mes, ano.

    Levanta ArgsInvalidos (mensagem pronta para print) se algo for inválido.
    Não faz sys.exit — mantém a função pura e testável.
    """
    dry_run = False
    hoje_str = None
    mes = ano = None

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == '--dry-run':
            dry_run = True
            if i + 1 < len(argv) and not argv[i + 1].startswith('--'):
                hoje_str = argv[i + 1]
                i += 1
        elif arg == '--mes':
            if i + 1 >= len(argv):
                raise ArgsInvalidos("Informe o mês após --mes. Ex: --mes 9")
            try:
                mes = int(argv[i + 1])
            except ValueError:
                raise ArgsInvalidos(f"Mês inválido: '{argv[i + 1]}'")
            i += 1
        elif arg == '--ano':
            if i + 1 >= len(argv):
                raise ArgsInvalidos("Informe o ano após --ano. Ex: --ano 2026")
            try:
                ano = int(argv[i + 1])
            except ValueError:
                raise ArgsInvalidos(f"Ano inválido: '{argv[i + 1]}'")
            i += 1
        else:
            raise ArgsInvalidos(f"Argumento desconhecido: '{arg}'")
        i += 1

    if (mes is None) != (ano is None):
        raise ArgsInvalidos("--mes e --ano devem ser usados juntos.")
    if mes is not None and not 1 <= mes <= 12:
        raise ArgsInvalidos(f"Mês inválido: {mes}. Use um valor entre 1 e 12.")
    if ano is not None and not 1000 <= ano <= 9999:
        raise ArgsInvalidos(f"Ano inválido: {ano}. Use um ano de 4 dígitos.")
    if hoje_str is not None:
        try:
            datetime.strptime(hoje_str, '%Y-%m-%d')
        except ValueError:
            raise ArgsInvalidos(f"Data inválida: '{hoje_str}'. Use o formato AAAA-MM-DD")

    return {'dry_run': dry_run, 'hoje_str': hoje_str, 'mes': mes, 'ano': ano}


def log(msg):
    with open(LOG, 'a') as f:
        f.write(msg + "\n")


def rodar_empresa_mes(empresa, mes, ano, pode_ser_aviso):
    """Roda o ETL de uma empresa/mês via subprocess (mesmo interpretador:
    sys.executable), grava a saída no log e devolve o status (OK/AVISO/FALHA).

    pode_ser_aviso: True só quando "planilha não encontrada" é esperado nesse
    contexto (mês corrente, dia 1). Fora disso, vira sempre FALHA.
    """
    log(f"--- {empresa} ({mes:02d}/{ano}) ---")
    resultado = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "atualizar_kpi_multi.py"), empresa,
         "--mes", str(mes), "--ano", str(ano)],
        capture_output=True, text=True,
    )
    saida = (resultado.stdout + resultado.stderr).rstrip("\n")
    if saida:
        log(saida)

    if resultado.returncode == 0:
        status = "OK"
    elif resultado.returncode == EXIT_PLANILHA_NAO_ENCONTRADA:
        if pode_ser_aviso:
            log("⚠️  Aviso esperado (planilha do mês corrente ainda não existe no dia 1).")
            status = "AVISO"
        else:
            log("❌ Planilha não encontrada (fora do esperado).")
            status = "FALHA"
    else:
        log(f"❌ Falha ao processar {empresa} ({mes:02d}/{ano}) — código {resultado.returncode}.")
        status = "FALHA"
    return status


def listar_execucoes_virada(hoje):
    """[(mes, ano), ...] que o modo virada rodaria para CADA empresa, na
    ordem em que rodaria (mês anterior antes do corrente, só dentro da
    janela de dia <= 5)."""
    ano_anterior, mes_ant = mes_anterior(hoje.year, hoje.month)
    execucoes = []
    if hoje.day <= 5:
        execucoes.append((mes_ant, ano_anterior))
    execucoes.append((hoje.month, hoje.year))
    return execucoes


def modo_virada(hoje, dry_run):
    execucoes = listar_execucoes_virada(hoje)
    ano_anterior, mes_ant = mes_anterior(hoje.year, hoje.month)

    if dry_run:
        print(f"Hoje (simulado): {hoje.isoformat()} (dia {hoje.day})")
        print(f"Mês corrente: {hoje.year}-{hoje.month:02d}")
        print(f"Mês anterior: {ano_anterior}-{mes_ant:02d}")
        print()
        if hoje.day <= 5:
            print("Dentro da janela de virada de mês (dia <= 5). Para cada empresa, executaria:")
        else:
            print("Fora da janela de virada de mês (dia > 5). Para cada empresa, executaria só:")
        for empresa in EMPRESAS:
            for mes, ano in execucoes:
                print(f"  {sys.executable} atualizar_kpi_multi.py {empresa} --mes {mes:02d} --ano {ano}")
        return

    resumo = []
    log("=" * 30)
    log(f"{datetime.now():%Y-%m-%d %H:%M:%S} — Iniciando atualização")

    for empresa in EMPRESAS:
        for mes, ano in execucoes:
            eh_mes_corrente = (mes, ano) == (hoje.month, hoje.year)
            pode_ser_aviso = eh_mes_corrente and hoje.day == 1
            status = rodar_empresa_mes(empresa, mes, ano, pode_ser_aviso)
            resumo.append(f"{empresa} {mes:02d}/{ano}: {status}")

    _fechar_resumo(resumo)


def modo_mes_especifico(mes, ano, dry_run):
    if dry_run:
        print(f"Mês específico: {mes:02d}/{ano}. Para cada empresa, executaria:")
        for empresa in EMPRESAS:
            print(f"  {sys.executable} atualizar_kpi_multi.py {empresa} --mes {mes:02d} --ano {ano}")
        return

    resumo = []
    log("=" * 30)
    log(f"{datetime.now():%Y-%m-%d %H:%M:%S} — Iniciando atualização (mês específico {mes:02d}/{ano})")

    for empresa in EMPRESAS:
        status = rodar_empresa_mes(empresa, mes, ano, pode_ser_aviso=False)
        resumo.append(f"{empresa} {mes:02d}/{ano}: {status}")

    _fechar_resumo(resumo)


def _fechar_resumo(resumo):
    log("--- Resumo ---")
    for linha in resumo:
        log(linha)
    log(f"{datetime.now():%Y-%m-%d %H:%M:%S} — Concluído")

    print("--- Resumo ---")
    for linha in resumo:
        print(linha)


def main(argv):
    try:
        args = parse_argv(argv[1:])
    except ArgsInvalidos as e:
        print(f"❌ {e}")
        sys.exit(1)

    if args['mes'] is not None:
        modo_mes_especifico(args['mes'], args['ano'], args['dry_run'])
        return

    hoje = (datetime.strptime(args['hoje_str'], '%Y-%m-%d').date()
             if args['hoje_str'] else date.today())
    modo_virada(hoje, args['dry_run'])


if __name__ == '__main__':
    main(sys.argv)
