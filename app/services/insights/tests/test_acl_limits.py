"""Camada anticorrupção Insights -> Limits (US-23, ADR-0015).

O contrato do Limits (`amount`, `tx_type`, `total_revenue`, `total_despesas`)
entra e sai traduzido para o vocabulário do Insights. Um Limits fora do ar vira
`LimitsIndisponivel` — a reconstrução e a conciliação abortam em vez de gravar
número errado.
"""

import httpx
import pytest

from app.acl_limits import ClienteLimits, LimitsIndisponivel

RESUMO_LIMITS = {
    "email": "marcia@mei.com.br",
    "year": 2026,
    "total_revenue": 4700.0,
    "total_despesas": 300.0,
    "saldo_liquido": 4400.0,
    "annual_limit": 81000.0,
    "remaining": 76300.0,
    "exceeded": False,
    "percent_used": 5.8,
    "alert_level": "ok",
}


def _cliente(handler) -> ClienteLimits:
    transporte = httpx.MockTransport(handler)
    return ClienteLimits(
        cliente_http=httpx.Client(base_url="http://limits:8000", transport=transporte)
    )


class TestTransacoes:
    def test_traduz_amount_e_tx_type_para_valor_e_tipo(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/transactions"
            assert request.url.params["email"] == "marcia@mei.com.br"
            assert request.url.params["year"] == "2026"
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 1,
                        "email": "marcia@mei.com.br",
                        "amount": 1500.0,
                        "tx_date": "2026-03-10",
                        "source": None,
                        "tx_type": "venda",
                    },
                    {
                        "id": 2,
                        "email": "marcia@mei.com.br",
                        "amount": 200.0,
                        "tx_date": "2026-04-01",
                        "source": "nota",
                        "tx_type": "compra",
                    },
                ],
            )

        transacoes = _cliente(handler).transacoes("marcia@mei.com.br", 2026)

        assert [(t.valor, t.tipo, t.data) for t in transacoes] == [
            (1500.0, "venda", "2026-03-10"),
            (200.0, "compra", "2026-04-01"),
        ]

    def test_resposta_fora_do_contrato_vira_indisponivel(self):
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"erro": "boom"})

        with pytest.raises(LimitsIndisponivel):
            _cliente(handler).transacoes("marcia@mei.com.br", 2026)


class TestResumo:
    def test_traduz_total_revenue_e_total_despesas(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/summary/marcia@mei.com.br"
            return httpx.Response(200, json=RESUMO_LIMITS)

        resumo = _cliente(handler).resumo("marcia@mei.com.br", 2026)

        assert resumo.total_vendas == 4700.0
        assert resumo.total_compras == 300.0

    def test_limits_fora_do_ar_vira_indisponivel(self):
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(503)

        with pytest.raises(LimitsIndisponivel):
            _cliente(handler).resumo("marcia@mei.com.br", 2026)

    def test_campo_ausente_no_resumo_vira_indisponivel(self):
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"email": "x", "year": 2026})

        with pytest.raises(LimitsIndisponivel):
            _cliente(handler).resumo("marcia@mei.com.br", 2026)


def test_context_manager_fecha_o_cliente_proprio():
    with ClienteLimits(base_url="http://limits:8000") as cliente:
        assert cliente is not None
    # fechar() de novo é inofensivo
    cliente.fechar()
