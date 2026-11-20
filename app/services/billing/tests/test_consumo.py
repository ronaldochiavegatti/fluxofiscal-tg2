"""Registro de consumo medido (ADR-0012, primeira etapa no ADR-0024).

O que se protege aqui: o registro guarda exatamente os tokens informados,
calcula os créditos pela tabela versionada (com margem e mínimo) e não mexe
no saldo, que continua debitado pela tabela fixa.
"""

from app import main

EMAIL = "mei@exemplo.com"


def _registrar(cliente, **ajustes):
    corpo = {
        "email": EMAIL,
        "servico": "documents",
        "operacao": "extracao_imagem",
        "modelo": "gemini-3.5-flash-lite",
        "tokens_entrada": 1580,
        "tokens_saida": 109,
        **ajustes,
    }
    return cliente.post("/usage", json=corpo)


class TestTabelaDeConversao:
    def test_aplica_taxas_e_margem_do_modelo_gerador(self):
        # (1580/1000*1 + 109/1000*3) * 1,5 = 2,86 -> 3
        assert main.creditos_proporcionais("gemini-3.5-flash-lite", 1580, 109) == 3

    def test_embedding_curto_paga_o_minimo_por_operacao(self):
        assert main.creditos_proporcionais("gemini-embedding-001", 6, 0) == 1

    def test_modelo_fora_da_tabela_nao_sai_de_graca(self):
        assert main.creditos_proporcionais("modelo-novo", 2000, 0) == 3

    def test_custo_estimado_usa_o_preco_de_referencia(self):
        # 1.000.000 tokens de entrada a US$ 0,075 x 5,50
        assert main.custo_estimado_brl("gemini-3.5-flash-lite", 1_000_000, 0) == 0.4125


class TestRegistro:
    def test_grava_tokens_creditos_e_versao(self, cliente):
        resposta = _registrar(cliente)

        assert resposta.status_code == 201
        corpo = resposta.json()
        assert corpo["tokens_entrada"] == 1580
        assert corpo["tokens_saida"] == 109
        assert corpo["creditos_proporcionais"] == 3
        assert corpo["versao_tabela"] == main.TABELA_CONVERSAO["versao"]

    def test_nao_debita_o_saldo(self, cliente):
        antes = cliente.get(f"/tokens/{EMAIL}").json()["balance"]

        _registrar(cliente, tokens_entrada=500_000)

        assert cliente.get(f"/tokens/{EMAIL}").json()["balance"] == antes

    def test_rotulo_com_texto_livre_e_recusado(self, cliente):
        """O extrato não pode virar depósito de conteúdo de nota ou de chat."""
        resposta = _registrar(cliente, operacao="Minha nota da padaria")

        assert resposta.status_code == 422

    def test_tokens_negativos_sao_recusados(self, cliente):
        assert _registrar(cliente, tokens_saida=-1).status_code == 422


class TestExtrato:
    def test_soma_por_operacao_e_lista_os_registros(self, cliente):
        _registrar(cliente)
        _registrar(cliente, tokens_entrada=1546, tokens_saida=112)
        _registrar(
            cliente,
            servico="agent-orchestrator",
            operacao="embedding_pergunta",
            modelo="gemini-embedding-001",
            tokens_entrada=12,
            tokens_saida=0,
        )

        extrato = cliente.get(f"/usage/{EMAIL}").json()

        totais = {t["operacao"]: t for t in extrato["totais"]}
        assert totais["extracao_imagem"]["chamadas"] == 2
        assert totais["extracao_imagem"]["tokens_entrada"] == 1580 + 1546
        assert totais["embedding_pergunta"]["creditos_proporcionais"] == 1
        assert len(extrato["registros"]) == 3
        assert extrato["registros"][0]["operacao"] == "embedding_pergunta"

    def test_extrato_e_por_usuario(self, cliente):
        _registrar(cliente)

        assert cliente.get("/usage/outro@exemplo.com").json()["totais"] == []

    def test_reset_apaga_o_consumo_registrado(self, cliente):
        _registrar(cliente)

        cliente.delete(f"/reset/{EMAIL}")

        assert cliente.get(f"/usage/{EMAIL}").json()["registros"] == []
