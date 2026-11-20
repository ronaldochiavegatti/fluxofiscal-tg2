"""Reconstrução da projeção a partir do Limits (US-23, ADR-0009).

Cenário Gherkin: "Projeção pode ser reconstruída" — disparado o recálculo
completo, as projeções são refeitas a partir do Limits e os totais conferem com
a fonte da verdade.
"""

import logging

from app import projecao, reconstrucao
from app.acl_limits import LimitsIndisponivel, TransacaoLimits

EMAIL = "marcia@mei.com.br"


class ACLFake:
    """Duplo do `ClienteLimits`: devolve transações canned por e-mail. Um valor
    `LimitsIndisponivel` no lugar da lista simula o Limits fora do ar."""

    def __init__(self, por_email: dict[str, list[TransacaoLimits] | Exception]):
        self._por_email = por_email
        self.chamadas: list[tuple[str, int]] = []

    def transacoes(self, email: str, ano: int) -> list[TransacaoLimits]:
        self.chamadas.append((email, ano))
        valor = self._por_email.get(email, [])
        if isinstance(valor, Exception):
            raise valor
        return list(valor)


def _semear_projecao_errada(sessao_factory, *, total_vendas: float, ano: int = 2026) -> None:
    with sessao_factory() as db:
        db.add(
            projecao.ResumoInsights(
                usuario_email=EMAIL,
                ano=ano,
                total_vendas=total_vendas,
                total_compras=0.0,
                qtd_transacoes=99,
            )
        )
        db.commit()


def _projecao(sessao_factory, ano: int = 2026) -> projecao.ResumoInsights | None:
    with sessao_factory() as db:
        return db.get(projecao.ResumoInsights, (EMAIL, ano))


def test_refaz_a_projecao_a_partir_do_limits(sessao_factory):
    _semear_projecao_errada(sessao_factory, total_vendas=999_999.0)
    acl = ACLFake(
        {
            EMAIL: [
                TransacaoLimits(valor=1500.0, tipo="venda", data="2026-03-10"),
                TransacaoLimits(valor=2000.0, tipo="venda", data="2026-05-01"),
                TransacaoLimits(valor=300.0, tipo="compra", data="2026-05-02"),
            ]
        }
    )

    refeitos = reconstrucao.reconstruir(sessao_factory, acl, email=EMAIL, ano=2026)

    assert refeitos == [
        {
            "email": EMAIL,
            "ano": 2026,
            "total_vendas": 3500.0,
            "total_compras": 300.0,
            "qtd_transacoes": 3,
        }
    ]
    linha = _projecao(sessao_factory)
    assert float(linha.total_vendas) == 3500.0
    assert float(linha.total_compras) == 300.0
    assert linha.qtd_transacoes == 3
    assert linha.atualizado_em is not None


def test_totais_conferem_com_a_fonte_da_verdade(sessao_factory):
    """O que a reconstrução grava tem de bater com o que o Limits somaria."""
    _semear_projecao_errada(sessao_factory, total_vendas=0.0)
    transacoes = [
        TransacaoLimits(valor=v, tipo="venda", data="2026-02-01") for v in (100.0, 250.5, 49.5)
    ]
    acl = ACLFake({EMAIL: transacoes})

    reconstrucao.reconstruir(sessao_factory, acl, email=EMAIL, ano=2026)

    esperado = sum(t.valor for t in transacoes)
    assert float(_projecao(sessao_factory).total_vendas) == esperado


def test_transacao_de_outro_ano_nao_entra(sessao_factory):
    _semear_projecao_errada(sessao_factory, total_vendas=0.0)
    acl = ACLFake(
        {
            EMAIL: [
                TransacaoLimits(valor=1000.0, tipo="venda", data="2026-01-10"),
                TransacaoLimits(valor=5000.0, tipo="venda", data="2025-12-31"),
            ]
        }
    )

    reconstrucao.reconstruir(sessao_factory, acl, email=EMAIL, ano=2026)

    assert float(_projecao(sessao_factory).total_vendas) == 1000.0


def test_limits_indisponivel_preserva_a_projecao_antiga(sessao_factory, caplog):
    _semear_projecao_errada(sessao_factory, total_vendas=4700.0)
    acl = ACLFake({EMAIL: LimitsIndisponivel("timeout")})

    with caplog.at_level(logging.WARNING, logger="insights.reconstrucao"):
        refeitos = reconstrucao.reconstruir(sessao_factory, acl, email=EMAIL, ano=2026)

    assert refeitos == []
    assert float(_projecao(sessao_factory).total_vendas) == 4700.0
    assert "limits_indisponivel" in caplog.text


def test_sem_email_refaz_todos_os_que_tem_projecao(sessao_factory):
    with sessao_factory() as db:
        db.add(projecao.ResumoInsights(usuario_email=EMAIL, ano=2026, total_vendas=1.0))
        db.add(projecao.ResumoInsights(usuario_email="joao@mei.com.br", ano=2026, total_vendas=1.0))
        db.commit()
    acl = ACLFake(
        {
            EMAIL: [TransacaoLimits(valor=10.0, tipo="venda", data="2026-03-01")],
            "joao@mei.com.br": [TransacaoLimits(valor=20.0, tipo="venda", data="2026-03-01")],
        }
    )

    refeitos = reconstrucao.reconstruir(sessao_factory, acl, ano=2026)

    assert {r["email"] for r in refeitos} == {EMAIL, "joao@mei.com.br"}
    assert {c[0] for c in acl.chamadas} == {EMAIL, "joao@mei.com.br"}
