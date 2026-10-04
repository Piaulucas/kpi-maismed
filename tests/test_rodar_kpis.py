"""Testes de rodar_kpis.py: validação de --mes/--ano, lista de execuções da
virada de mês e isolamento de falha entre empresas — tudo com subprocess
mockado, sem rodar o ETL de verdade nem tocar no banco/OneDrive."""
from datetime import date
from types import SimpleNamespace

import pytest

import rodar_kpis


# 1. validação de --mes/--ano
@pytest.mark.parametrize('argv', [
    ['--mes', '13', '--ano', '2026'],   # mês fora do intervalo 1-12
    ['--mes', '0', '--ano', '2026'],    # mês fora do intervalo (zero)
    ['--mes', '9', '--ano', '26'],      # ano de 2 dígitos, não 4
    ['--mes', '9'],                     # só --mes, sem --ano
    ['--ano', '2026'],                  # só --ano, sem --mes
])
def test_parse_argv_rejeita_entradas_invalidas(argv):
    with pytest.raises(rodar_kpis.ArgsInvalidos):
        rodar_kpis.parse_argv(argv)


def test_parse_argv_aceita_mes_e_ano_validos():
    args = rodar_kpis.parse_argv(['--mes', '9', '--ano', '2026'])
    assert args['mes'] == 9 and args['ano'] == 2026 and args['dry_run'] is False


def test_parse_argv_dry_run_com_data_override():
    args = rodar_kpis.parse_argv(['--dry-run', '2026-10-04'])
    assert args['dry_run'] is True
    assert args['hoje_str'] == '2026-10-04'
    assert args['mes'] is None and args['ano'] is None


def test_parse_argv_dry_run_combinado_com_mes_ano():
    args = rodar_kpis.parse_argv(['--dry-run', '--mes', '9', '--ano', '2026'])
    assert args['dry_run'] is True
    assert args['mes'] == 9 and args['ano'] == 2026
    # "--dry-run" não deve "comer" o "--mes" seguinte como se fosse uma data
    assert args['hoje_str'] is None


# 2. lista de execuções da virada de mês (mesma lista usada para as 5 empresas)
@pytest.mark.parametrize('hoje, esperado', [
    (date(2026, 10, 4), [(9, 2026), (10, 2026)]),   # dentro da janela (dia <= 5)
    (date(2027, 1, 3), [(12, 2026), (1, 2027)]),    # dentro da janela + virada de ano
    (date(2026, 10, 10), [(10, 2026)]),             # fora da janela: só mês corrente
])
def test_listar_execucoes_virada(hoje, esperado):
    assert rodar_kpis.listar_execucoes_virada(hoje) == esperado


def test_modo_virada_dry_run_lista_as_5_empresas(capsys):
    rodar_kpis.modo_virada(date(2026, 10, 4), dry_run=True)
    saida = capsys.readouterr().out

    for empresa in rodar_kpis.EMPRESAS:
        assert f"{empresa} --mes 09 --ano 2026" in saida
        assert f"{empresa} --mes 10 --ano 2026" in saida
    # 5 empresas x 2 execuções (mês anterior + corrente)
    assert saida.count("--mes") == 2 * len(rodar_kpis.EMPRESAS)


# 3. falha de uma empresa não interrompe as demais (subprocess mockado)
def test_rodar_empresa_mes_falha_de_uma_nao_impede_as_outras(tmp_path, monkeypatch):
    monkeypatch.setattr(rodar_kpis, 'LOG', tmp_path / "kpi_cron.log")

    chamadas = []

    def fake_run(cmd, capture_output, text):
        empresa = cmd[2]
        chamadas.append(empresa)
        if empresa == 'alfa':
            return SimpleNamespace(returncode=1, stdout='', stderr='erro proposital')
        return SimpleNamespace(returncode=0, stdout='ok', stderr='')

    monkeypatch.setattr(rodar_kpis.subprocess, 'run', fake_run)

    resumo = {
        empresa: rodar_kpis.rodar_empresa_mes(empresa, 10, 2026, pode_ser_aviso=False)
        for empresa in rodar_kpis.EMPRESAS
    }

    # as 5 empresas foram chamadas, mesmo com a alfa falhando no meio
    assert chamadas == list(rodar_kpis.EMPRESAS)
    assert resumo['alfa'] == 'FALHA'
    assert all(status == 'OK' for empresa, status in resumo.items() if empresa != 'alfa')


def test_rodar_empresa_mes_planilha_nao_encontrada_vira_aviso_so_quando_permitido(tmp_path, monkeypatch):
    monkeypatch.setattr(rodar_kpis, 'LOG', tmp_path / "kpi_cron.log")
    monkeypatch.setattr(
        rodar_kpis.subprocess, 'run',
        lambda *a, **k: SimpleNamespace(returncode=rodar_kpis.EXIT_PLANILHA_NAO_ENCONTRADA, stdout='', stderr='')
    )

    assert rodar_kpis.rodar_empresa_mes('sert', 10, 2026, pode_ser_aviso=True) == 'AVISO'
    assert rodar_kpis.rodar_empresa_mes('sert', 10, 2026, pode_ser_aviso=False) == 'FALHA'


def test_modo_mes_especifico_nao_para_por_falha_de_uma_empresa(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(rodar_kpis, 'LOG', tmp_path / "kpi_cron.log")

    def fake_run(cmd, capture_output, text):
        empresa = cmd[2]
        if empresa == 'sert':
            return SimpleNamespace(returncode=rodar_kpis.EXIT_PLANILHA_NAO_ENCONTRADA, stdout='', stderr='')
        return SimpleNamespace(returncode=0, stdout='', stderr='')

    monkeypatch.setattr(rodar_kpis.subprocess, 'run', fake_run)
    rodar_kpis.modo_mes_especifico(9, 2026, dry_run=False)

    saida = capsys.readouterr().out
    # fora do modo virada não existe "dia 1 esperado": não encontrada é sempre FALHA
    assert 'sert 09/2026: FALHA' in saida
    for empresa in rodar_kpis.EMPRESAS:
        if empresa != 'sert':
            assert f'{empresa} 09/2026: OK' in saida
