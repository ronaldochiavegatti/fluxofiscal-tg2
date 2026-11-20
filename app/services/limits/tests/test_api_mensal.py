"""Rota "mês a mês" do Limits (US-27), sobre `dominio.faturamento`.

O motor em si já é testado sem banco em `test_dominio_faturamento.py`. O que
importa aqui é a agregação: se a rota soma por mês e tipo corretamente e
traduz o resultado do domínio sem perder informação.
"""

EMAIL = "marcia@mei.com.br"
ANO = 2026


class TestAgregacaoMensal:
    def test_doze_meses_sempre_presentes(self, cliente, registrar):
        registrar(EMAIL, 1000.00, f"{ANO}-03-10", "venda")

        corpo = cliente.get(f"/mensal/{EMAIL}", params={"year": ANO}).json()

        assert [ponto["mes"] for ponto in corpo] == list(range(1, 13))

    def test_soma_vendas_e_despesas_separadamente_por_mes(self, cliente, registrar):
        registrar(EMAIL, 9640.00, f"{ANO}-08-05", "venda")
        registrar(EMAIL, 2100.00, f"{ANO}-08-18", "compra")

        corpo = cliente.get(f"/mensal/{EMAIL}", params={"year": ANO}).json()

        agosto = next(ponto for ponto in corpo if ponto["mes"] == 8)
        assert agosto["vendas"] == 9640.00
        assert agosto["despesas"] == 2100.00

    def test_ignora_mes_e_ano_de_fora(self, cliente, registrar):
        registrar(EMAIL, 1000.00, f"{ANO}-03-10", "venda")
        registrar(EMAIL, 5000.00, f"{ANO - 1}-03-10", "venda")

        corpo = cliente.get(f"/mensal/{EMAIL}", params={"year": ANO}).json()

        marco = next(ponto for ponto in corpo if ponto["mes"] == 3)
        assert marco["vendas"] == 1000.00

    def test_meta_e_o_limite_cheio_dividido_por_doze_sem_abertura(self, cliente, registrar):
        """Cenário Gherkin: "Barras com linha de meta" — meta 6.750 no mock
        de referência (81.000 / 12), sem data de abertura informada."""
        registrar(EMAIL, 1000.00, f"{ANO}-03-10", "venda")

        corpo = cliente.get(f"/mensal/{EMAIL}", params={"year": ANO}).json()

        assert all(ponto["meta"] == 6750.00 for ponto in corpo)

    def test_mes_acima_da_meta_fica_destacado(self, cliente, registrar):
        registrar(EMAIL, 9640.00, f"{ANO}-08-05", "venda")

        corpo = cliente.get(f"/mensal/{EMAIL}", params={"year": ANO}).json()

        agosto = next(ponto for ponto in corpo if ponto["mes"] == 8)
        setembro = next(ponto for ponto in corpo if ponto["mes"] == 9)
        assert agosto["acima_da_meta"] is True
        assert setembro["acima_da_meta"] is False

    def test_limite_proporcional_reduz_a_meta(self, cliente, registrar):
        registrar(EMAIL, 1000.00, f"{ANO}-08-10", "venda")

        corpo = cliente.get(
            f"/mensal/{EMAIL}", params={"year": ANO, "data_abertura": f"{ANO}-07-03"}
        ).json()

        # limite proporcional a 6 meses: 40.500 / 12 = 3.375,00
        assert all(ponto["meta"] == 3375.00 for ponto in corpo)

    def test_usuario_sem_transacoes_nao_quebra(self, cliente):
        corpo = cliente.get("/mensal/ninguem@mei.com.br", params={"year": ANO}).json()

        assert len(corpo) == 12
        assert all(ponto["vendas"] == 0.0 for ponto in corpo)


class TestValidacaoMensal:
    def test_data_abertura_depois_do_ano_e_400_nao_500(self, cliente, registrar):
        """Mesma borda encontrada pela suíte de contrato em /ritmo (US-26):
        `calcular_limite_aplicavel` recusa abertura depois do ano de
        referência com `ValueError` — a rota converte para 400, não 500."""
        registrar(EMAIL, 1000.00, f"{ANO}-03-10", "venda")

        resposta = cliente.get(
            f"/mensal/{EMAIL}", params={"year": ANO, "data_abertura": f"{ANO + 1}-01-01"}
        )

        assert resposta.status_code == 400
