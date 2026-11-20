"""Mês a mês e origem do faturamento (US-27) — motor de domínio, sem banco.

Cenários Gherkin da história: "Barras com linha de meta" (série mensal) e
"Concentração é sinalizada" (origem do faturamento por CNPJ).
"""

from decimal import Decimal

import pytest

from app.dominio.faturamento import (
    LIMIAR_CONCENTRACAO_CLIENTE,
    calcular_concentracao_clientes,
    calcular_serie_mensal,
)


class TestSerieMensal:
    def test_doze_meses_sempre_presentes_mesmo_sem_lancamento(self):
        serie = calcular_serie_mensal({}, {}, Decimal("81000.00"))

        assert [ponto.mes for ponto in serie] == list(range(1, 13))
        assert all(ponto.vendas == Decimal("0.00") for ponto in serie)

    def test_meta_e_o_limite_aplicavel_dividido_por_doze(self):
        serie = calcular_serie_mensal({}, {}, Decimal("81000.00"))

        # 81000 / 12 = 6750,00 — a "meta 6.750" do mock de dashboard-v2.md.
        assert all(ponto.meta == Decimal("6750.00") for ponto in serie)

    def test_mes_acima_da_meta_fica_destacado(self):
        """Cenário: "Barras com linha de meta" — meses acima da meta destacados."""
        serie = calcular_serie_mensal({8: Decimal("9640.00")}, {}, Decimal("81000.00"))

        agosto = next(ponto for ponto in serie if ponto.mes == 8)
        setembro = next(ponto for ponto in serie if ponto.mes == 9)

        assert agosto.acima_da_meta is True
        assert setembro.acima_da_meta is False

    def test_vendas_e_despesas_nao_se_misturam(self):
        serie = calcular_serie_mensal(
            {8: Decimal("9640.00")}, {8: Decimal("2100.00")}, Decimal("81000.00")
        )

        agosto = next(ponto for ponto in serie if ponto.mes == 8)

        assert agosto.vendas == Decimal("9640.00")
        assert agosto.despesas == Decimal("2100.00")

    def test_limite_aplicavel_zero_ou_negativo_e_erro(self):
        with pytest.raises(ValueError, match="positivo"):
            calcular_serie_mensal({}, {}, Decimal("0"))


class TestConcentracaoClientes:
    def test_sem_vendas_identificadas_devolve_lista_vazia(self):
        assert calcular_concentracao_clientes({}) == []

    def test_ordena_do_maior_para_o_menor(self):
        itens = calcular_concentracao_clientes(
            {
                "11.111.111/0001-11": Decimal("1000.00"),
                "22.222.222/0001-22": Decimal("5000.00"),
            }
        )

        assert [item.cnpj for item in itens] == [
            "22.222.222/0001-22",
            "11.111.111/0001-11",
        ]

    def test_cenario_38_por_cento_aparece_no_topo_com_o_percentual(self):
        """Cenário: "Concentração é sinalizada" — dado que um CNPJ representa
        38% do faturamento, ele aparece no topo da lista com o percentual."""
        itens = calcular_concentracao_clientes(
            {
                "12.345.678/0001-90": Decimal("3800.00"),
                "outro/cliente": Decimal("6200.00"),
            }
        )

        topo = itens[0]
        assert topo.cnpj == "outro/cliente"
        assert itens[1].cnpj == "12.345.678/0001-90"
        assert itens[1].percentual == Decimal("38.00")

    def test_aviso_de_concentracao_acima_de_70_por_cento(self):
        """Cenário: "Concentração é sinalizada" — aviso acima de 70%."""
        itens = calcular_concentracao_clientes(
            {
                "12.345.678/0001-90": Decimal("7500.00"),
                "outro/cliente": Decimal("2500.00"),
            }
        )

        dominante = next(i for i in itens if i.cnpj == "12.345.678/0001-90")
        minoritario = next(i for i in itens if i.cnpj == "outro/cliente")

        assert dominante.percentual == Decimal("75.00")
        assert dominante.alerta is True
        assert minoritario.alerta is False

    def test_exatamente_no_limiar_nao_dispara_alerta(self):
        """A borda é exclusiva: "acima de 70%" não inclui exatamente 70%."""
        itens = calcular_concentracao_clientes(
            {
                "no-limiar": Decimal("70.00"),
                "resto": Decimal("30.00"),
            }
        )

        no_limiar = next(i for i in itens if i.cnpj == "no-limiar")
        assert no_limiar.percentual == Decimal("70.00")
        assert no_limiar.alerta is False

    def test_percentual_e_sobre_o_total_identificado_nao_sobre_zero(self):
        """CNPJ com valor zero (ou negativo, defensivamente) não entra e não
        distorce o denominador dos demais."""
        itens = calcular_concentracao_clientes(
            {
                "identificado": Decimal("1000.00"),
                "sem-venda-de-verdade": Decimal("0"),
            }
        )

        assert len(itens) == 1
        assert itens[0].percentual == Decimal("100.00")

    def test_limiar_de_concentracao_e_70_por_cento(self):
        assert Decimal("0.70") == LIMIAR_CONCENTRACAO_CLIENTE
