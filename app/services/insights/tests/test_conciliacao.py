"""Conciliação da projeção contra o Limits (US-23, ADR-0009).

Cenário Gherkin: "Divergência é detectada" — dada uma projeção fora de sincronia,
quando a conciliação noturna executa, a divergência é alertada.
"""

import logging
import time

import pytest

from app import conciliacao, projecao
from app.acl_limits import LimitsIndisponivel, ResumoLimits

EMAIL = "marcia@mei.com.br"


class ACLResumoFake:
    def __init__(self, resumos: dict[str, ResumoLimits | Exception]):
        self._resumos = resumos

    def resumo(self, email: str, ano: int) -> ResumoLimits:
        valor = self._resumos.get(email)
        if isinstance(valor, Exception):
            raise valor
        assert valor is not None
        return valor


def _semear(sessao_factory, *, vendas: float, compras: float = 0.0, ano: int = 2026) -> None:
    with sessao_factory() as db:
        db.add(
            projecao.ResumoInsights(
                usuario_email=EMAIL, ano=ano, total_vendas=vendas, total_compras=compras
            )
        )
        db.commit()


def test_divergencia_acima_da_tolerancia_e_alertada(sessao_factory, caplog):
    _semear(sessao_factory, vendas=4700.0)
    acl = ACLResumoFake({EMAIL: ResumoLimits(total_vendas=4000.0, total_compras=0.0)})

    with caplog.at_level(logging.WARNING, logger="insights.conciliacao"):
        divergencias = conciliacao.conciliar(sessao_factory, acl, ano=2026)

    assert len(divergencias) == 1
    d = divergencias[0]
    assert d.campo == "total_vendas"
    assert d.diferenca == 700.0
    assert "conciliacao.divergencia" in caplog.text


def test_dentro_da_tolerancia_de_um_centavo_nao_alerta(sessao_factory):
    _semear(sessao_factory, vendas=4700.00)
    acl = ACLResumoFake({EMAIL: ResumoLimits(total_vendas=4700.008, total_compras=0.0)})

    assert conciliacao.conciliar(sessao_factory, acl, ano=2026) == []


def test_limits_indisponivel_nao_gera_falso_positivo(sessao_factory, caplog):
    _semear(sessao_factory, vendas=4700.0)
    acl = ACLResumoFake({EMAIL: LimitsIndisponivel("timeout")})

    with caplog.at_level(logging.WARNING, logger="insights.conciliacao"):
        divergencias = conciliacao.conciliar(sessao_factory, acl, ano=2026)

    assert divergencias == []
    assert "limits_indisponivel" in caplog.text


def test_divergencia_em_compras_tambem_conta(sessao_factory):
    _semear(sessao_factory, vendas=100.0, compras=50.0)
    acl = ACLResumoFake({EMAIL: ResumoLimits(total_vendas=100.0, total_compras=999.0)})

    divergencias = conciliacao.conciliar(sessao_factory, acl, ano=2026)

    assert [d.campo for d in divergencias] == ["total_compras"]


def test_sem_projecao_a_conciliacao_e_um_no_op(sessao_factory):
    acl = ACLResumoFake({})
    assert conciliacao.conciliar(sessao_factory, acl, ano=2026) == []


class TestConciliadorNoturno:
    def test_o_laco_executa_uma_rodada_e_registra_a_divergencia(self, sessao_factory, caplog):
        _semear(sessao_factory, vendas=4700.0)
        acl = ACLResumoFake({EMAIL: ResumoLimits(total_vendas=1.0, total_compras=0.0)})

        conciliador = conciliacao.Conciliador(
            session_factory=sessao_factory,
            acl_factory=lambda: acl,
            intervalo=0.05,
        )
        with caplog.at_level(logging.WARNING, logger="insights.conciliacao"):
            conciliador.iniciar()
            prazo = time.time() + 2
            while "conciliacao.divergencia" not in caplog.text and time.time() < prazo:
                time.sleep(0.05)
            conciliador.parar()

        assert "conciliacao.divergencia" in caplog.text

    def test_intervalo_zero_nao_sobe_thread(self, sessao_factory):
        conciliador = conciliacao.Conciliador(sessao_factory, acl_factory=lambda: None, intervalo=0)
        conciliador.iniciar()
        conciliador.parar()  # inofensivo mesmo sem thread
        assert conciliador._thread is None


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [("300", 300), ("lixo", conciliacao.INTERVALO_PADRAO_S), ("", conciliacao.INTERVALO_PADRAO_S)],
)
def test_intervalo_s_le_do_ambiente(monkeypatch, bruto, esperado):
    monkeypatch.setenv("CONCILIACAO_INTERVALO_S", bruto)
    assert conciliacao.intervalo_s() == esperado
