"""Testes de rodar_kpis.py: validação de --mes/--ano, lista de execuções da
virada de mês, isolamento de falha entre empresas, status, resumo e
notificações — tudo com subprocess mockado, sem rodar o ETL de verdade, sem
banco/OneDrive e sem abrir janela de verdade."""
from datetime import date, datetime
from types import SimpleNamespace

import pytest

import rodar_kpis
from rodar_kpis import Resultado


@pytest.fixture(autouse=True)
def popen_falso(monkeypatch, tmp_path):
    """Nenhum teste abre janela nem escreve no kpi_cron.log real."""
    chamadas = []

    class PopenFalso:
        def __init__(self, cmd, **kwargs):
            chamadas.append((cmd, kwargs))

        def wait(self, *a, **k):
            raise AssertionError("rodar_kpis não pode esperar o osascript")

    monkeypatch.setattr(rodar_kpis.subprocess, 'Popen', PopenFalso)
    monkeypatch.setattr(rodar_kpis, 'LOG', tmp_path / "kpi_cron.log")
    return chamadas


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
    assert resumo['alfa'].nivel == 'FALHA'
    assert resumo['alfa'].texto == 'FALHA — erro proposital'
    assert all(r.nivel == 'OK' for empresa, r in resumo.items() if empresa != 'alfa')


def test_rodar_empresa_mes_planilha_nao_encontrada_vira_aviso_so_quando_permitido(tmp_path, monkeypatch):
    monkeypatch.setattr(rodar_kpis, 'LOG', tmp_path / "kpi_cron.log")
    monkeypatch.setattr(
        rodar_kpis.subprocess, 'run',
        lambda *a, **k: SimpleNamespace(returncode=rodar_kpis.EXIT_PLANILHA_NAO_ENCONTRADA, stdout='', stderr='')
    )

    assert rodar_kpis.rodar_empresa_mes('sert', 10, 2026, pode_ser_aviso=True).nivel == 'AVISO'
    assert rodar_kpis.rodar_empresa_mes('sert', 10, 2026, pode_ser_aviso=False).nivel == 'FALHA'


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
    assert 'sert     09/2026: FALHA — planilha não encontrada' in saida
    for empresa in rodar_kpis.EMPRESAS:
        if empresa != 'sert':
            assert f'{empresa.ljust(9)}09/2026: OK' in saida


# 4. código de saída do ETL -> status
DETALHE_FALCON = 'aba ADULTO-PED, linha 32: 07/10/2023 · MAV*** · R$ 8.057,35'


@pytest.mark.parametrize('codigo, pode_ser_aviso, saida, esperado', [
    (0, False, '', ('OK', 'OK', ())),
    (4, False, '', ('AVISO', 'AVISO — planilha sem lançamentos', ())),
    (2, True, '', ('AVISO', 'AVISO — planilha do mês ainda não criada', ())),
    (2, False, '', ('FALHA', 'FALHA — planilha não encontrada', ())),
    (3, False, f'❌ [Falcon] data fora\nDETALHE: {DETALHE_FALCON}\n',
     ('FALHA', 'FALHA — DATA ERRADA', (DETALHE_FALCON,))),
    (5, False, 'DETALHE: aba NEONATAL, linha 19: 02/10/2026 · sem paciente · R$ 300,00\n',
     ('FALHA', 'FALHA — LANÇAMENTO SEM PACIENTE', ('aba NEONATAL, linha 19: 02/10/2026 · sem paciente · R$ 300,00',))),
    (6, False, 'DETALHE: aba ADULTO-PED, linha 17: data vazia ou inválida · MAV*** · R$ 500,00\n',
     ('FALHA', 'FALHA — DATA VAZIA OU INVÁLIDA', ('aba ADULTO-PED, linha 17: data vazia ou inválida · MAV*** · R$ 500,00',))),
    (1, False, '📂 x\n❌ [Alfa Saúde] planilha vazia, mas o banco tem 7 dias deste mês — verifique o arquivo\n',
     ('FALHA', 'FALHA — [Alfa Saúde] planilha vazia, mas o banco tem 7 dias deste mês — verifique o arquivo', ())),
    (1, False, 'Traceback (most recent call last):\n  ...\nKeyError: \'DATA\'\n',
     ('FALHA', "FALHA — KeyError: 'DATA'", ())),
    (1, False, '', ('FALHA', 'FALHA — código 1', ())),
])
def test_classificar_codigo_para_status(codigo, pode_ser_aviso, saida, esperado):
    assert rodar_kpis.classificar(codigo, saida, pode_ser_aviso) == esperado


# 5. resumo
RESULTADOS_EXEMPLO = [
    Resultado('sert', 10, 2026, 'OK', 'OK'),
    Resultado('alfa', 10, 2026, 'AVISO', 'AVISO — planilha sem lançamentos'),
    Resultado('falcon', 10, 2026, 'FALHA', 'FALHA — DATA ERRADA', (DETALHE_FALCON,)),
]


def test_montar_resumo_texto_exato():
    texto = rodar_kpis.montar_resumo(RESULTADOS_EXEMPLO, datetime(2026, 10, 8, 15, 0))
    assert texto == (
        "KPI — 08/10/2026 15:00\n"
        "sert     10/2026: OK\n"
        "alfa     10/2026: AVISO — planilha sem lançamentos\n"
        "falcon   10/2026: FALHA — DATA ERRADA\n"
        "    aba ADULTO-PED, linha 32: 07/10/2023 · MAV*** · R$ 8.057,35"
    )


def test_banner_titulo_e_texto():
    assert rodar_kpis.titulo_banner(RESULTADOS_EXEMPLO) == 'KPI 10/2026'
    assert rodar_kpis.texto_banner(RESULTADOS_EXEMPLO) == '1 OK · 1 aviso · 1 falha'

    virada = [Resultado('sert', 9, 2026, 'OK', 'OK'), Resultado('sert', 10, 2026, 'OK', 'OK')]
    assert rodar_kpis.titulo_banner(virada) == 'KPI set+out/2026'
    assert rodar_kpis.texto_banner(virada) == '2 OK · 0 avisos · 0 falhas'

    virada_ano = [Resultado('sert', 1, 2027, 'OK', 'OK'), Resultado('sert', 12, 2026, 'OK', 'OK')]
    assert rodar_kpis.titulo_banner(virada_ano) == 'KPI dez/2026+jan/2027'


# 6. janela e banner
def _etl_falso(monkeypatch, codigo=0):
    monkeypatch.setattr(rodar_kpis.subprocess, 'run',
                        lambda *a, **k: SimpleNamespace(returncode=codigo, stdout='', stderr=''))


def test_modo_real_abre_janela_e_banner_sem_esperar(monkeypatch, popen_falso):
    _etl_falso(monkeypatch, codigo=rodar_kpis.EXIT_DATA_FORA_DO_MES)
    rodar_kpis.modo_mes_especifico(10, 2026, dry_run=False)

    assert len(popen_falso) == 2
    (janela, kw_janela), (banner, _) = popen_falso
    assert janela[:2] == ['/usr/bin/osascript', '-e'] and 'on run argv' in janela[2]
    assert 'display dialog' in janela[2]
    texto, titulo, icone = janela[3:]
    assert titulo == 'KPI — resumo da carga' and icone == 'caution'
    assert 'falcon   10/2026: FALHA — DATA ERRADA' in texto
    assert kw_janela['start_new_session'] is True   # sobrevive ao fim do job do launchd
    assert 'display notification' in banner[2]
    assert banner[3:] == ['KPI 10/2026', '0 OK · 0 avisos · 5 falhas']


def test_janela_sem_falha_usa_icone_normal(monkeypatch, popen_falso):
    _etl_falso(monkeypatch, codigo=0)
    rodar_kpis.modo_mes_especifico(10, 2026, dry_run=False)
    assert popen_falso[0][0][5] == 'note'


def test_dry_run_nao_abre_janela_nem_banner(monkeypatch, popen_falso):
    _etl_falso(monkeypatch)
    rodar_kpis.modo_mes_especifico(10, 2026, dry_run=True)
    rodar_kpis.modo_virada(date(2026, 10, 4), dry_run=True)
    assert popen_falso == []


def test_erro_no_osascript_nao_altera_codigo_de_saida(monkeypatch, tmp_path):
    def popen_quebrado(*a, **k):
        raise FileNotFoundError('osascript')

    monkeypatch.setattr(rodar_kpis.subprocess, 'Popen', popen_quebrado)
    _etl_falso(monkeypatch)
    monkeypatch.setattr(rodar_kpis, 'date', SimpleNamespace(today=lambda: date(2026, 10, 8)))

    # main termina normalmente (código 0), sem levantar nem chamar sys.exit
    assert rodar_kpis.main(['rodar_kpis.py']) is None
    assert 'Falha ao chamar osascript' in (tmp_path / "kpi_cron.log").read_text()


# 7. poda do log
def test_podar_log_mantem_ultimas_linhas(tmp_path):
    log = tmp_path / "kpi_cron.log"
    log.write_text("".join(f"linha {i}\n" for i in range(2500)))
    rodar_kpis.podar_log(log, max_linhas=2000)
    linhas = log.read_text().splitlines()
    assert len(linhas) == 2000
    assert linhas[0] == 'linha 500' and linhas[-1] == 'linha 2499'
