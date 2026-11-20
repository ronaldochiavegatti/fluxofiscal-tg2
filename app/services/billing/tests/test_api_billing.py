"""Testes das rotas do Billing.

Duas coisas importam aqui. A primeira é aritmética de saldo: débito acontece ou
não acontece, nunca pela metade. A segunda é o contrato de assinatura, que
estava quebrado — `orm_mode` no Pydantic v2 é chave ignorada, e as duas rotas
devolviam 500 sem que nada avisasse, porque nenhum teste as exercitava e a
interface nunca chegou a usá-las.
"""

from datetime import datetime

import pytest

from app import main

EMAIL = "marcia@mei.com.br"
OUTRO = "douglas@mei.com.br"


class TestHealth:
    def test_responde_identificando_o_servico(self, cliente):
        assert cliente.get("/health").json() == {"status": "ok", "service": "billing"}


class TestAssinaturas:
    def test_cria_e_devolve_a_assinatura(self, cliente):
        """Regressão: com `orm_mode`, esta rota devolvia 500.

        No Pydantic v2 a chave passou a ser ignorada em silêncio, e sem
        `from_attributes` a validação a partir do objeto do SQLAlchemy falha.
        """
        resposta = cliente.post("/subscriptions", json={"email": EMAIL, "plan": "free"})

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["user_email"] == EMAIL
        assert corpo["plan"] == "free"
        assert corpo["active"] is True

    def test_plano_padrao_e_gratuito(self, cliente):
        resposta = cliente.post("/subscriptions", json={"email": EMAIL})

        assert resposta.json()["plan"] == "free"

    def test_consulta_por_identificador(self, cliente):
        criada = cliente.post("/subscriptions", json={"email": EMAIL}).json()

        resposta = cliente.get(f"/subscriptions/{criada['id']}")

        assert resposta.status_code == 200
        assert resposta.json()["id"] == criada["id"]

    def test_assinatura_inexistente(self, cliente):
        assert cliente.get("/subscriptions/9999").status_code == 404

    def test_data_de_criacao_declara_o_fuso(self, cliente):
        """Regressão: `format: date-time` é RFC 3339 e exige o deslocamento.

        A coluna é `timestamp` sem fuso; sem declarar UTC na saída, a resposta
        violava o esquema que o próprio serviço publica.
        """
        criada = cliente.post("/subscriptions", json={"email": EMAIL}).json()

        assert datetime.fromisoformat(criada["created_at"]).tzinfo is not None


class TestSaldoDeTokens:
    def test_primeira_consulta_abre_a_conta_com_o_saldo_inicial(self, cliente):
        resposta = cliente.get(f"/tokens/{EMAIL}")

        assert resposta.status_code == 200
        assert resposta.json()["balance"] == main.STARTING_TOKEN_BALANCE

    def test_devolve_a_tabela_de_custos(self, cliente):
        """A interface usa estes valores para estimar o custo antes da ação."""
        custos = cliente.get(f"/tokens/{EMAIL}").json()["costs"]

        assert custos == main.TOKEN_COSTS

    def test_contas_sao_independentes_por_usuario(self, cliente):
        cliente.post("/tokens/consume", json={"email": EMAIL, "reason": "chat_message"})

        assert cliente.get(f"/tokens/{OUTRO}").json()["balance"] == main.STARTING_TOKEN_BALANCE


class TestConsumoDeTokens:
    @pytest.mark.parametrize("motivo", ["document_confirm", "chat_message"])
    def test_debita_o_custo_do_motivo(self, cliente, motivo):
        resposta = cliente.post("/tokens/consume", json={"email": EMAIL, "reason": motivo})

        corpo = resposta.json()
        assert corpo["charged"] == main.TOKEN_COSTS[motivo]
        assert corpo["balance"] == main.STARTING_TOKEN_BALANCE - main.TOKEN_COSTS[motivo]
        assert corpo["insufficient"] is False

    def test_debitos_sucessivos_acumulam(self, cliente):
        for _ in range(3):
            cliente.post("/tokens/consume", json={"email": EMAIL, "reason": "chat_message"})

        esperado = main.STARTING_TOKEN_BALANCE - 3 * main.TOKEN_COSTS["chat_message"]
        assert cliente.get(f"/tokens/{EMAIL}").json()["balance"] == esperado

    def test_motivo_desconhecido_e_recusado(self, cliente):
        resposta = cliente.post("/tokens/consume", json={"email": EMAIL, "reason": "cafe"})

        assert resposta.status_code == 400
        assert "cafe" in resposta.json()["detail"]

    def test_saldo_insuficiente_nao_debita(self, cliente):
        """Saldo insuficiente precisa deixar a conta intacta.

        Cobrar parcialmente, ou zerar, seria pior do que recusar: o usuário
        pagaria por uma ação que não aconteceu.
        """
        custo = main.TOKEN_COSTS["chat_message"]
        for _ in range(main.STARTING_TOKEN_BALANCE // custo):
            cliente.post("/tokens/consume", json={"email": EMAIL, "reason": "chat_message"})
        restante = cliente.get(f"/tokens/{EMAIL}").json()["balance"]
        assert restante < main.TOKEN_COSTS["document_confirm"]

        resposta = cliente.post(
            "/tokens/consume", json={"email": EMAIL, "reason": "document_confirm"}
        )

        corpo = resposta.json()
        assert corpo["insufficient"] is True
        assert corpo["charged"] == 0
        assert corpo["balance"] == restante


class TestTokensIlimitados:
    """Modo demonstração: nenhuma ação é bloqueada nem debitada."""

    @pytest.fixture(autouse=True)
    def _ligar_modo_demo(self, monkeypatch):
        monkeypatch.setenv("BILLING_TOKENS_ILIMITADOS", "true")

    def test_consumo_nao_debita_nem_bloqueia(self, cliente):
        custo = main.TOKEN_COSTS["document_confirm"]
        for _ in range(main.STARTING_TOKEN_BALANCE // custo + 1):
            corpo = cliente.post(
                "/tokens/consume", json={"email": EMAIL, "reason": "document_confirm"}
            ).json()

        assert corpo["insufficient"] is False
        assert corpo["charged"] == 0
        assert corpo["ilimitado"] is True
        assert corpo["balance"] == main.STARTING_TOKEN_BALANCE

    def test_saldo_anuncia_o_modo(self, cliente):
        assert cliente.get(f"/tokens/{EMAIL}").json()["ilimitado"] is True

    def test_motivo_desconhecido_continua_recusado(self, cliente):
        resposta = cliente.post("/tokens/consume", json={"email": EMAIL, "reason": "cafe"})

        assert resposta.status_code == 400

    @pytest.mark.parametrize("valor", ["", "false", "0"])
    def test_desligado_por_padrao(self, cliente, monkeypatch, valor):
        monkeypatch.setenv("BILLING_TOKENS_ILIMITADOS", valor)

        assert cliente.get(f"/tokens/{EMAIL}").json()["ilimitado"] is False


class TestReset:
    def test_restaura_o_saldo_inicial(self, cliente):
        cliente.post("/tokens/consume", json={"email": EMAIL, "reason": "document_confirm"})

        resposta = cliente.delete(f"/reset/{EMAIL}")

        assert resposta.json() == {"email": EMAIL, "balance": main.STARTING_TOKEN_BALANCE}
        assert cliente.get(f"/tokens/{EMAIL}").json()["balance"] == main.STARTING_TOKEN_BALANCE

    def test_funciona_para_usuario_que_nunca_consumiu(self, cliente):
        """A conta pode não existir ainda: o reset precisa criá-la."""
        resposta = cliente.delete(f"/reset/{OUTRO}")

        assert resposta.status_code == 200
        assert cliente.get(f"/tokens/{OUTRO}").json()["balance"] == main.STARTING_TOKEN_BALANCE
