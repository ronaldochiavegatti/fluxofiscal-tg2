"""Testes da camada anticorrupção do Documents (US-46).

Duas fronteiras: a resposta do Gemini (não confiável, formato do modelo) e o
payload para o Limits (contexto de outro serviço). A tradução é o único ponto
que conhece os dois lados.
"""

import pytest

from app import main
from app.traducao import (
    CAMPOS_QUE_NAO_ATRAVESSAM,
    traduzir_para_limits,
    traduzir_valor_monetario,
)
from tests.conftest import EMAIL

NOTA = "\n".join(
    [
        "NOTA FISCAL",
        "Salao da Marcia LTDA",
        "CNPJ: 12.345.678/0001-95",
        "VALOR TOTAL R$ 1.234,56",
        "Emissao: 17/06/2026",
    ]
)


class TestTraduzirValorMonetario:
    """Cenário: resposta do modelo é traduzida, não confiada."""

    def test_string_com_mascara_brasileira_vira_decimal(self):
        assert traduzir_valor_monetario("1.234,56") == 1234.56

    def test_string_com_prefixo_de_moeda(self):
        assert traduzir_valor_monetario("R$ 1.234,56") == 1234.56

    def test_string_no_formato_americano(self):
        assert traduzir_valor_monetario("1,234.56") == 1234.56

    def test_string_simples_com_virgula_decimal(self):
        assert traduzir_valor_monetario("1234,56") == 1234.56

    def test_numero_ja_decimal_passa_direto(self):
        assert traduzir_valor_monetario(1234.56) == 1234.56

    def test_inteiro_vira_float(self):
        assert traduzir_valor_monetario(1234) == 1234.0

    @pytest.mark.parametrize(
        "bruto",
        [None, "", "  ", "grátis", "abc", "R$", "-", True, False, [], {}, object()],
    )
    def test_lixo_e_rejeitado(self, bruto):
        assert traduzir_valor_monetario(bruto) is None

    @pytest.mark.parametrize("bruto", [0, 0.0, "0,00", -10, "-10,00", -0.01])
    def test_valor_nao_positivo_e_rejeitado(self, bruto):
        assert traduzir_valor_monetario(bruto) is None

    def test_acima_do_teto_e_rejeitado(self):
        assert traduzir_valor_monetario("999.999.999,99") is None

    def test_sanitize_gemini_result_usa_a_traducao(self):
        limpo = main.sanitize_gemini_result({"amount": "1.234,56"})
        assert limpo["value"] == 1234.56


class TestTraduzirParaLimits:
    """Cenário: confiança não atravessa a fronteira."""

    def _payload(self, **ajustes):
        base = {
            "email": EMAIL,
            "amount": 1234.56,
            "tx_date": None,
            "source": "upload:nota.pdf",
            "tx_type": "venda",
        }
        return traduzir_para_limits(**{**base, **ajustes})

    def test_so_os_seis_campos_da_transacao(self):
        assert set(self._payload()) == {
            "email",
            "amount",
            "tx_date",
            "source",
            "tx_type",
            "cnpj_cliente",
        }

    def test_nenhum_campo_de_estimativa_atravessa(self):
        payload = self._payload()
        for proibido in CAMPOS_QUE_NAO_ATRAVESSAM:
            assert proibido not in payload

    def test_tx_type_desconhecido_vira_venda(self):
        assert self._payload(tx_type="doacao")["tx_type"] == "venda"

    def test_sem_data_usa_hoje(self):
        assert self._payload()["tx_date"]  # ISO string, não None

    def test_cnpj_cliente_atravessa_em_venda(self):
        """Cenário US-27: CNPJ do cliente é o que alimenta a concentração de
        cliente — só faz sentido, e só atravessa, numa venda."""
        payload = self._payload(cnpj_cliente="12.345.678/0001-90")
        assert payload["cnpj_cliente"] == "12.345.678/0001-90"

    def test_cnpj_cliente_nao_atravessa_em_compra(self):
        """Em compra o CNPJ disponível é o do fornecedor (emitente), não o
        de um cliente — não é o dado que esta história quer agregar."""
        payload = self._payload(tx_type="compra", cnpj_cliente="12.345.678/0001-90")
        assert payload["cnpj_cliente"] is None


class TestFronteiraDoConfirm:
    """A confiança da extração não pode chegar ao Limits pelo /confirm."""

    def _confirmar(self, cliente, **campos):
        corpo = {
            "email": EMAIL,
            "amount": 1234.56,
            "tx_date": "2026-06-17",
            "tx_type": "venda",
            "description": "Servico de manicure",
            "source_filename": "nota.pdf",
            "ocr_text": NOTA,
            **campos,
        }
        return cliente.post("/confirm", json=corpo)

    def test_payload_do_limits_nao_carrega_confianca(self, cliente, limits_falso):
        resposta = self._confirmar(cliente)
        assert resposta.status_code == 200

        enviado = next(e for e in limits_falso if e["url"].endswith("/transactions"))
        for proibido in CAMPOS_QUE_NAO_ATRAVESSAM:
            assert proibido not in enviado["json"]
        assert set(enviado["json"]) == {
            "email",
            "amount",
            "tx_date",
            "source",
            "tx_type",
            "cnpj_cliente",
        }

    def test_confirm_repassa_cnpj_destinatario_como_cnpj_cliente_em_venda(
        self, cliente, limits_falso
    ):
        """US-27: numa venda, quem recebeu a nota é o cliente."""
        resposta = self._confirmar(cliente, cnpj_destinatario="98.765.432/0001-10")
        assert resposta.status_code == 200

        enviado = next(e for e in limits_falso if e["url"].endswith("/transactions"))
        assert enviado["json"]["cnpj_cliente"] == "98.765.432/0001-10"

    def test_confirm_nao_repassa_cnpj_cliente_em_compra(self, cliente, limits_falso):
        resposta = self._confirmar(
            cliente, tx_type="compra", cnpj_destinatario="98.765.432/0001-10"
        )
        assert resposta.status_code == 200

        enviado = next(e for e in limits_falso if e["url"].endswith("/transactions"))
        assert enviado["json"]["cnpj_cliente"] is None
