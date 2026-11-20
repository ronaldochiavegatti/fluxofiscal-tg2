"""Testes do núcleo de domínio fiscal.

Sem banco, sem HTTP, sem framework: só as regras. A suíte inteira roda em
milissegundos, que é o que permite executá-la a cada salvamento.

As bordas têm caso próprio de propósito. É nelas que erro de sinal se esconde,
e erro de sinal aqui significa dizer a um MEI que ele foi desenquadrado quando
não foi.
"""

from decimal import Decimal

import pytest

from app.dominio import (
    LIMIAR_ALERTA,
    LIMITE_ANUAL_MEI,
    NivelAlerta,
    TipoTransacao,
    calcular_percentual_usado,
    calcular_resumo,
    classificar_nivel,
)


class TestSoVendaContaParaOTeto:
    def test_compras_nao_entram_no_faturamento(self):
        resumo = calcular_resumo(vendas=Decimal("50000"), compras=Decimal("30000"))

        assert resumo.faturamento == Decimal("50000.00")
        assert resumo.despesas == Decimal("30000.00")
        assert resumo.saldo_liquido == Decimal("20000.00")

    def test_compras_nao_afetam_o_restante(self):
        so_vendas = calcular_resumo(Decimal("50000"), Decimal("0"))
        com_compras = calcular_resumo(Decimal("50000"), Decimal("30000"))

        assert so_vendas.restante == com_compras.restante
        assert so_vendas.nivel_alerta == com_compras.nivel_alerta

    def test_compras_podem_superar_vendas(self):
        """Negócio no prejuízo é situação válida, não erro."""
        resumo = calcular_resumo(Decimal("10000"), Decimal("25000"))

        assert resumo.saldo_liquido == Decimal("-15000.00")
        assert resumo.nivel_alerta is NivelAlerta.OK


class TestNiveisDeAlerta:
    @pytest.mark.parametrize(
        ("faturamento", "esperado"),
        [
            ("0", NivelAlerta.OK),
            ("1000.00", NivelAlerta.OK),
            ("64799.99", NivelAlerta.OK),
            ("64800.00", NivelAlerta.ATENCAO),
            ("70000.00", NivelAlerta.ATENCAO),
            ("80999.99", NivelAlerta.ATENCAO),
            ("81000.00", NivelAlerta.ATENCAO),
            ("81000.01", NivelAlerta.EXCEDIDO),
            ("100000.00", NivelAlerta.EXCEDIDO),
        ],
    )
    def test_faixas(self, faturamento, esperado):
        assert classificar_nivel(Decimal(faturamento), LIMITE_ANUAL_MEI) is esperado

    def test_teto_exato_nao_excede(self):
        """R$ 81.000,00 é o limite, não a ultrapassagem dele.

        O teto do MEI é "até R$ 81.000,00". Quem fatura exatamente isso está no
        limite, com zero de folga — e não desenquadrado.
        """
        resumo = calcular_resumo(LIMITE_ANUAL_MEI, Decimal("0"))

        assert resumo.excedeu is False
        assert resumo.restante == Decimal("0.00")
        assert resumo.nivel_alerta is NivelAlerta.ATENCAO

    def test_um_centavo_acima_do_teto_excede(self):
        resumo = calcular_resumo(LIMITE_ANUAL_MEI + Decimal("0.01"), Decimal("0"))

        assert resumo.excedeu is True
        assert resumo.restante == Decimal("-0.01")
        assert resumo.nivel_alerta is NivelAlerta.EXCEDIDO

    def test_limiar_de_alerta_e_oitenta_por_cento(self):
        limiar = LIMITE_ANUAL_MEI * LIMIAR_ALERTA

        assert limiar == Decimal("64800.0000")


class TestPercentualUsado:
    @pytest.mark.parametrize(
        ("faturamento", "esperado"),
        [
            ("0", "0.00"),
            ("8100.00", "10.00"),
            ("40500.00", "50.00"),
            ("81000.00", "100.00"),
            ("47304.00", "58.40"),
        ],
    )
    def test_calculo(self, faturamento, esperado):
        percentual = calcular_percentual_usado(Decimal(faturamento), LIMITE_ANUAL_MEI)
        assert percentual == Decimal(esperado)

    def test_valor_absurdo_e_limitado(self):
        """Erro de OCR que lê 1.234,56 como 123456,00 não pode quebrar a tela."""
        percentual = calcular_percentual_usado(Decimal("999999999"), LIMITE_ANUAL_MEI)
        assert percentual == Decimal("999.00")


class TestArredondamento:
    def test_valores_saem_com_dois_decimais(self):
        resumo = calcular_resumo(Decimal("1234.567"), Decimal("100.001"))

        assert resumo.faturamento == Decimal("1234.57")
        assert resumo.despesas == Decimal("100.00")

    def test_meio_arredonda_para_cima(self):
        """Convenção contábil: 0,005 vira 0,01, não 0,00."""
        resumo = calcular_resumo(Decimal("0.005"), Decimal("0"))
        assert resumo.faturamento == Decimal("0.01")


class TestEntradasInvalidas:
    def test_vendas_negativas(self):
        with pytest.raises(ValueError, match="vendas"):
            calcular_resumo(Decimal("-1"), Decimal("0"))

    def test_compras_negativas(self):
        with pytest.raises(ValueError, match="compras"):
            calcular_resumo(Decimal("0"), Decimal("-1"))

    @pytest.mark.parametrize("limite", ["0", "-100"])
    def test_limite_nao_positivo(self, limite):
        with pytest.raises(ValueError, match="limite"):
            classificar_nivel(Decimal("100"), Decimal(limite))

    def test_percentual_com_limite_invalido(self):
        with pytest.raises(ValueError, match="limite"):
            calcular_percentual_usado(Decimal("100"), Decimal("0"))


class TestTipoTransacao:
    def test_valores(self):
        assert TipoTransacao.VENDA == "venda"
        assert TipoTransacao.COMPRA == "compra"

    def test_apenas_dois_tipos(self):
        assert {t.value for t in TipoTransacao} == {"venda", "compra"}


class TestResumoEImutavel:
    def test_nao_permite_alteracao(self):
        resumo = calcular_resumo(Decimal("1000"), Decimal("0"))

        with pytest.raises(AttributeError):
            resumo.faturamento = Decimal("999999")


class TestIndependenciaDeInfraestrutura:
    def test_dominio_nao_importa_framework(self):
        """O domínio precisa continuar puro. Se alguém importar SQLAlchemy aqui,
        a regra fiscal volta a depender de como o dado é armazenado."""
        import pathlib

        raiz = pathlib.Path(__file__).parent.parent / "app" / "dominio"
        proibidos = ("fastapi", "sqlalchemy", "httpx", "pydantic", "reportlab")

        for arquivo in raiz.glob("*.py"):
            fonte = arquivo.read_text(encoding="utf-8")
            for modulo in proibidos:
                assert f"import {modulo}" not in fonte, (
                    f"{arquivo.name} importa {modulo}; o domínio deve permanecer puro"
                )
