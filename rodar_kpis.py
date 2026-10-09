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

Em modo real, ao final: acrescenta o resumo no kpi_cron.log, imprime no
stdout, abre uma janela com o resumo completo e dispara um banner curto (via
osascript, sem esperar). O kpi_cron.log é podado para as últimas ~2.000 linhas.
"""
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import NamedTuple

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from atualizar_kpi_multi import (
    EMPRESAS,
    EXIT_DATA_FORA_DO_MES,
    EXIT_DATA_INVALIDA,
    EXIT_LANCAMENTO_SEM_PACIENTE,
    EXIT_PLANILHA_NAO_ENCONTRADA,
    EXIT_PLANILHA_VAZIA,
    PREFIXO_DETALHE,
    mes_anterior,
)

LOG = SCRIPT_DIR / "kpi_cron.log"
MAX_LINHAS_LOG = 2000

MESES_ABREV = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun',
               'jul', 'ago', 'set', 'out', 'nov', 'dez']

# O texto vai por argv (on run argv), nunca interpolado no script: aspas e
# quebras de linha do resumo não precisam de escape.
SCRIPT_JANELA = '''on run argv
    set texto to item 1 of argv
    set titulo to item 2 of argv
    activate
    if item 3 of argv is "caution" then
        display dialog texto with title titulo buttons {"OK"} default button "OK" giving up after 1800 with icon caution
    else
        display dialog texto with title titulo buttons {"OK"} default button "OK" giving up after 1800 with icon note
    end if
end run'''

SCRIPT_BANNER = '''on run argv
    display notification (item 2 of argv) with title (item 1 of argv)
end run'''


class Resultado(NamedTuple):
    empresa: str
    mes: int
    ano: int
    nivel: str          # OK / AVISO / FALHA
    texto: str          # ex.: "FALHA — DATA ERRADA"
    detalhes: tuple = ()


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


def ultima_linha_de_erro(saida):
    """Última linha com ❌ da saída do ETL; sem ela (ex.: traceback), a última
    linha não vazia."""
    linhas = [l.strip() for l in saida.splitlines() if l.strip()]
    for linha in reversed(linhas):
        if '❌' in linha:
            return linha.replace('❌', '').strip()
    return linhas[-1] if linhas else ''


def classificar(returncode, saida, pode_ser_aviso):
    """Código de saída do ETL -> (nivel, texto, detalhes)."""
    if returncode == 0:
        return 'OK', 'OK', ()
    if returncode == EXIT_PLANILHA_VAZIA:
        return 'AVISO', 'AVISO — planilha sem lançamentos', ()
    if returncode == EXIT_PLANILHA_NAO_ENCONTRADA:
        if pode_ser_aviso:
            return 'AVISO', 'AVISO — planilha do mês ainda não criada', ()
        return 'FALHA', 'FALHA — planilha não encontrada', ()
    falhas_com_detalhe = {
        EXIT_DATA_FORA_DO_MES: 'FALHA — DATA ERRADA',
        EXIT_LANCAMENTO_SEM_PACIENTE: 'FALHA — LANÇAMENTO SEM PACIENTE',
        EXIT_DATA_INVALIDA: 'FALHA — DATA VAZIA OU INVÁLIDA',
    }
    if returncode in falhas_com_detalhe:
        detalhes = tuple(l[len(PREFIXO_DETALHE):] for l in saida.splitlines()
                         if l.startswith(PREFIXO_DETALHE))
        return 'FALHA', falhas_com_detalhe[returncode], detalhes
    erro = ultima_linha_de_erro(saida) or f'código {returncode}'
    return 'FALHA', f'FALHA — {erro}', ()


def rodar_empresa_mes(empresa, mes, ano, pode_ser_aviso):
    """Roda o ETL de uma empresa/mês via subprocess (mesmo interpretador:
    sys.executable), grava a saída no log e devolve um Resultado.

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

    nivel, texto, detalhes = classificar(resultado.returncode, saida, pode_ser_aviso)
    if nivel != 'OK':
        log(f"{texto} (código {resultado.returncode})")
    return Resultado(empresa, mes, ano, nivel, texto, detalhes)


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

    resultados = []
    log("=" * 30)
    log(f"{datetime.now():%Y-%m-%d %H:%M:%S} — Iniciando atualização")

    for empresa in EMPRESAS:
        for mes, ano in execucoes:
            eh_mes_corrente = (mes, ano) == (hoje.month, hoje.year)
            pode_ser_aviso = eh_mes_corrente and hoje.day == 1
            resultados.append(rodar_empresa_mes(empresa, mes, ano, pode_ser_aviso))

    finalizar(resultados)


def modo_mes_especifico(mes, ano, dry_run):
    if dry_run:
        print(f"Mês específico: {mes:02d}/{ano}. Para cada empresa, executaria:")
        for empresa in EMPRESAS:
            print(f"  {sys.executable} atualizar_kpi_multi.py {empresa} --mes {mes:02d} --ano {ano}")
        return

    resultados = []
    log("=" * 30)
    log(f"{datetime.now():%Y-%m-%d %H:%M:%S} — Iniciando atualização (mês específico {mes:02d}/{ano})")

    for empresa in EMPRESAS:
        resultados.append(rodar_empresa_mes(empresa, mes, ano, pode_ser_aviso=False))

    finalizar(resultados)


def montar_resumo(resultados, quando):
    """Texto do resumo: cabeçalho + uma empresa/mês por linha, com os
    detalhes (ex.: linhas de data errada) indentados logo abaixo."""
    largura = max(len(e) for e in EMPRESAS) + 1
    linhas = [f"KPI — {quando:%d/%m/%Y %H:%M}"]
    for r in resultados:
        linhas.append(f"{r.empresa.ljust(largura)}{r.mes:02d}/{r.ano}: {r.texto}")
        linhas.extend(f"    {d}" for d in r.detalhes)
    return "\n".join(linhas)


def titulo_banner(resultados):
    """'KPI 10/2026'; com mais de um mês (virada): 'KPI set+out/2026', ou
    'KPI dez/2026+jan/2027' na virada de ano."""
    meses = sorted({(r.ano, r.mes) for r in resultados})
    if len(meses) == 1:
        ano, mes = meses[0]
        return f"KPI {mes:02d}/{ano}"
    anos = {ano for ano, _ in meses}
    if len(anos) == 1:
        return f"KPI {'+'.join(MESES_ABREV[m - 1] for _, m in meses)}/{anos.pop()}"
    return "KPI " + "+".join(f"{MESES_ABREV[m - 1]}/{a}" for a, m in meses)


def texto_banner(resultados):
    """'3 OK · 1 aviso · 1 falha'."""
    n = {nivel: sum(r.nivel == nivel for r in resultados) for nivel in ('OK', 'AVISO', 'FALHA')}
    avisos = f"{n['AVISO']} aviso" + ("" if n['AVISO'] == 1 else "s")
    falhas = f"{n['FALHA']} falha" + ("" if n['FALHA'] == 1 else "s")
    return f"{n['OK']} OK · {avisos} · {falhas}"


def _osascript(script, *args):
    """Dispara o osascript sem esperar. start_new_session tira o processo do
    grupo do launchd, que mataria a janela ao fim do job. Qualquer erro só vai
    para o log: notificação nunca derruba o script nem muda o código de saída."""
    try:
        subprocess.Popen(
            ["/usr/bin/osascript", "-e", script, *args],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        try:
            log(f"⚠️  Falha ao chamar osascript: {e}")
        except Exception:
            pass


def notificar(resultados, texto):
    tem_falha = any(r.nivel == 'FALHA' for r in resultados)
    _osascript(SCRIPT_JANELA, texto, "KPI — resumo da carga", "caution" if tem_falha else "note")
    _osascript(SCRIPT_BANNER, titulo_banner(resultados), texto_banner(resultados))


def podar_log(caminho=None, max_linhas=MAX_LINHAS_LOG):
    """Mantém só as últimas max_linhas do log (corta as mais antigas)."""
    caminho = caminho or LOG
    try:
        with open(caminho) as f:
            linhas = f.readlines()
        if len(linhas) > max_linhas:
            with open(caminho, 'w') as f:
                f.writelines(linhas[-max_linhas:])
    except OSError as e:
        print(f"⚠️  Não foi possível podar {caminho}: {e}")


def finalizar(resultados, quando=None):
    """Só no modo real: resumo no log + stdout, janela e banner, poda do log."""
    texto = montar_resumo(resultados, quando or datetime.now())
    log("--- Resumo ---")
    log(texto)
    print(texto)
    notificar(resultados, texto)
    log(f"{datetime.now():%Y-%m-%d %H:%M:%S} — Concluído")
    podar_log()


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
