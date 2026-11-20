"""Testes da camada anticorrupção do agente (US-46).

O resumo do Limits é um modelo de outro contexto. A tradução para o
`RetratoFiscal` é a fronteira: campo novo do Limits não chega ao prompt, campo
que sumiu vira padrão em vez de quebrar.
"""

import pytest

from app import main
from app.acl import RetratoFiscal, traduzir_resumo_limits
from tests.conftest import EMAIL, RESUMO


def _prompt(resumo: dict) -> str:
    return main.build_prompt(
        retrato=traduzir_resumo_limits(resumo),
        user_message="quanto ainda posso faturar?",
        email=EMAIL,
        knowledge_hits=[],
        document_hits=[],
    )


class TestTraducaoDoResumo:
    def test_traduz_os_campos_conhecidos(self):
        retrato = traduzir_resumo_limits(RESUMO)

        assert isinstance(retrato, RetratoFiscal)
        assert retrato.faturamento_vendas == RESUMO["total_revenue"]
        assert retrato.despesas_compras == RESUMO["total_despesas"]
        assert retrato.limite_anual == RESUMO["annual_limit"]
        assert retrato.nivel_alerta == "ok"

    def test_campo_ausente_recebe_padrao_em_vez_de_quebrar(self):
        retrato = traduzir_resumo_limits({"email": EMAIL})

        assert retrato.faturamento_vendas == 0.0
        assert retrato.despesas_compras == 0.0
        assert retrato.ano is None
        assert retrato.ultrapassou is False
        assert retrato.nivel_alerta == "ok"

    def test_saldo_liquido_ausente_e_derivado(self):
        retrato = traduzir_resumo_limits({"total_revenue": 1000.0, "total_despesas": 400.0})
        assert retrato.saldo_liquido == 600.0

    def test_nivel_de_alerta_desconhecido_vira_ok(self):
        assert traduzir_resumo_limits({"alert_level": "pânico"}).nivel_alerta == "ok"

    def test_numero_como_string_e_convertido(self):
        assert traduzir_resumo_limits({"total_revenue": "1234.56"}).faturamento_vendas == 1234.56


class TestMudancaNoResumoNaoQuebraOPrompt:
    """Cenário: o Limits adiciona um campo ao resumo e o prompt não muda."""

    def test_campo_novo_no_resumo_e_absorvido(self):
        antes = _prompt(RESUMO)
        depois = _prompt(
            {
                **RESUMO,
                "novo_indicador_de_risco": 0.87,
                "regime_tributario": "MEI",
                "total_revenue_v2": 999999.0,
            }
        )
        assert antes == depois

    def test_campo_renomeado_no_resumo_nao_vaza_para_o_prompt(self):
        # O Limits troca `total_revenue` por `faturamento`: a tradução não
        # reconhece a chave nova, então o prompt cai no padrão (0,00) em vez de
        # exibir um nome de campo cru do outro serviço.
        prompt = _prompt(
            {k: v for k, v in RESUMO.items() if k != "total_revenue"} | {"faturamento": 50000.0}
        )
        assert "faturamento: 50000" not in prompt
        assert "R$ 0,00" in prompt


def test_limiar_de_alerta_configurado_chega_ao_retrato():
    retrato = traduzir_resumo_limits({"alert_threshold_percent": 65.0})
    assert retrato.limiar_alerta_percentual == 65.0


def test_sem_limiar_na_resposta_usa_o_padrao_oficial():
    assert traduzir_resumo_limits({}).limiar_alerta_percentual == 80.0


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (81000.0, "R$ 81.000,00"),
        (1234567.891, "R$ 1.234.567,89"),
        (0.5, "R$ 0,50"),
        (999.999, "R$ 1.000,00"),
        (-1500.25, "-R$ 1.500,25"),
    ],
)
def test_valores_em_reais_no_padrao_brasileiro(valor, esperado):
    assert main.formatar_brl(valor) == esperado
