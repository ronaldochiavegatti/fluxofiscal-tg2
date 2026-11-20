"""Rota "origem do faturamento" do Limits (US-27), sobre
`dominio.faturamento.calcular_concentracao_clientes`.
"""

EMAIL = "marcia@mei.com.br"
ANO = 2026
CNPJ_A = "12.345.678/0001-90"
CNPJ_B = "98.765.432/0001-10"


class TestConcentracao:
    def test_usuario_sem_transacoes_devolve_lista_vazia(self, cliente):
        corpo = cliente.get("/concentracao/ninguem@mei.com.br", params={"year": ANO}).json()

        assert corpo == []

    def test_venda_sem_cnpj_identificado_fica_fora(self, cliente, registrar):
        registrar(EMAIL, 1000.00, f"{ANO}-03-10", "venda")  # sem cnpj_cliente

        corpo = cliente.get(f"/concentracao/{EMAIL}", params={"year": ANO}).json()

        assert corpo == []

    def test_compra_nunca_entra_na_concentracao(self, cliente, registrar):
        registrar(EMAIL, 1000.00, f"{ANO}-03-10", "compra", cnpj_cliente=CNPJ_A)

        corpo = cliente.get(f"/concentracao/{EMAIL}", params={"year": ANO}).json()

        assert corpo == []

    def test_agrupa_por_cnpj_e_ordena_do_maior_para_o_menor(self, cliente, registrar):
        registrar(EMAIL, 3800.00, f"{ANO}-03-10", "venda", cnpj_cliente=CNPJ_A)
        registrar(EMAIL, 6200.00, f"{ANO}-04-10", "venda", cnpj_cliente=CNPJ_B)

        corpo = cliente.get(f"/concentracao/{EMAIL}", params={"year": ANO}).json()

        assert [item["cnpj"] for item in corpo] == [CNPJ_B, CNPJ_A]

    def test_cenario_38_por_cento_no_topo_com_o_percentual(self, cliente, registrar):
        """Cenário Gherkin: "Concentração é sinalizada" — 38% no topo com o
        percentual, sem aviso (abaixo de 70%)."""
        registrar(EMAIL, 3800.00, f"{ANO}-03-10", "venda", cnpj_cliente=CNPJ_A)
        registrar(EMAIL, 6200.00, f"{ANO}-04-10", "venda", cnpj_cliente=CNPJ_B)

        corpo = cliente.get(f"/concentracao/{EMAIL}", params={"year": ANO}).json()

        item_a = next(i for i in corpo if i["cnpj"] == CNPJ_A)
        assert item_a["percentual"] == 38.0
        assert item_a["alerta"] is False

    def test_aviso_de_concentracao_acima_de_70_por_cento(self, cliente, registrar):
        registrar(EMAIL, 7500.00, f"{ANO}-03-10", "venda", cnpj_cliente=CNPJ_A)
        registrar(EMAIL, 2500.00, f"{ANO}-04-10", "venda", cnpj_cliente=CNPJ_B)

        corpo = cliente.get(f"/concentracao/{EMAIL}", params={"year": ANO}).json()

        dominante = next(i for i in corpo if i["cnpj"] == CNPJ_A)
        assert dominante["percentual"] == 75.0
        assert dominante["alerta"] is True

    def test_ignora_ano_diferente(self, cliente, registrar):
        registrar(EMAIL, 1000.00, f"{ANO - 1}-03-10", "venda", cnpj_cliente=CNPJ_A)

        corpo = cliente.get(f"/concentracao/{EMAIL}", params={"year": ANO}).json()

        assert corpo == []
