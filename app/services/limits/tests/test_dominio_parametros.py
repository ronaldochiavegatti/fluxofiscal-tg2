"""Parâmetros configuráveis das regras fiscais (#91).

Duas garantias: os padrões são os valores oficiais de antes (nada muda para
quem não configura) e cada parâmetro de fato muda a regra que o usa.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.dominio import (
    PARAMETROS_PADRAO,
    NivelAlerta,
    NivelRitmo,
    ParametrosFiscais,
    calcular_concentracao_clientes,
    calcular_limite_aplicavel,
    calcular_projecao,
    calcular_resumo,
    calcular_serie_mensal,
    classificar_nivel,
)
from app.dominio import parametros as p

D = Decimal


class TestPadrao:
    def test_padroes_sao_os_valores_oficiais_de_antes(self):
        assert PARAMETROS_PADRAO.limite_anual == D("81000.00")
        assert PARAMETROS_PADRAO.limiar_alerta == D("0.80")
        assert PARAMETROS_PADRAO.margem_desenquadramento == D("1.20")
        assert PARAMETROS_PADRAO.limite_proporcional is True
        assert PARAMETROS_PADRAO.meta_mensal is None
        assert PARAMETROS_PADRAO.limiar_concentracao_cliente == D("0.70")
        assert PARAMETROS_PADRAO.dias_minimos_para_projetar == 30
        assert PARAMETROS_PADRAO.transacoes_minimas_para_projetar == 3
        assert PARAMETROS_PADRAO.dias_abertura_recente == 60
        assert PARAMETROS_PADRAO.limiar_lancamento_atipico == D("0.60")
        assert PARAMETROS_PADRAO.limiar_atencao_ritmo_realizado == D("0.50")

    def test_constantes_reexportadas_continuam_iguais(self):
        from app.dominio.faturamento import LIMIAR_CONCENTRACAO_CLIENTE
        from app.dominio.limites import LIMIAR_ALERTA, LIMITE_ANUAL_MEI, MARGEM_DESENQUADRAMENTO

        assert LIMITE_ANUAL_MEI == p.LIMITE_ANUAL_MEI
        assert LIMIAR_ALERTA == p.LIMIAR_ALERTA
        assert MARGEM_DESENQUADRAMENTO == p.MARGEM_DESENQUADRAMENTO
        assert LIMIAR_CONCENTRACAO_CLIENTE == p.LIMIAR_CONCENTRACAO_CLIENTE


class TestValidacao:
    @pytest.mark.parametrize(
        ("campo", "valor"),
        [
            ("limite_anual", D("0")),
            ("limite_anual", D("-1")),
            ("limite_anual", D("100000000")),
            ("margem_desenquadramento", D("0.99")),
            ("margem_desenquadramento", D("5.01")),
            ("limiar_alerta", D("0")),
            ("limiar_alerta", D("1.01")),
            ("meta_mensal", D("0")),
            ("meta_mensal", D("100000000")),
            ("limiar_concentracao_cliente", D("0")),
            ("limiar_concentracao_cliente", D("1.5")),
            ("dias_minimos_para_projetar", 0),
            ("dias_minimos_para_projetar", 367),
            ("transacoes_minimas_para_projetar", 0),
            ("transacoes_minimas_para_projetar", 10_001),
            ("dias_abertura_recente", -1),
            ("dias_abertura_recente", 367),
            ("dias_minimos_para_projetar", True),
            ("limiar_lancamento_atipico", D("0")),
            ("limiar_lancamento_atipico", D("1.01")),
            ("limiar_atencao_ritmo_realizado", D("0")),
            ("limiar_atencao_ritmo_realizado", D("1.01")),
        ],
    )
    def test_valor_fora_da_faixa_e_recusado(self, campo, valor):
        with pytest.raises(ValueError, match=campo):
            ParametrosFiscais(**{campo: valor})

    @pytest.mark.parametrize(
        ("campo", "valor"),
        [
            ("limite_anual", D("0.01")),
            ("limite_anual", D("99999999.99")),
            ("margem_desenquadramento", D("1")),
            ("margem_desenquadramento", D("5")),
            ("limiar_alerta", D("1")),
            ("meta_mensal", D("0.01")),
            ("limiar_concentracao_cliente", D("1")),
            ("dias_minimos_para_projetar", 1),
            ("dias_minimos_para_projetar", 366),
            ("transacoes_minimas_para_projetar", 1),
            ("transacoes_minimas_para_projetar", 10_000),
            ("dias_abertura_recente", 0),
            ("dias_abertura_recente", 366),
            ("limiar_lancamento_atipico", D("1")),
            ("limiar_atencao_ritmo_realizado", D("1")),
        ],
    )
    def test_bordas_validas_sao_aceitas(self, campo, valor):
        assert getattr(ParametrosFiscais(**{campo: valor}), campo) == valor

    def test_com_ajustes_sobrescreve_so_o_informado(self):
        params = ParametrosFiscais.com_ajustes({"limite_anual": D("130000")})
        assert params.limite_anual == D("130000")
        assert params.limiar_alerta == PARAMETROS_PADRAO.limiar_alerta

    def test_com_ajustes_recusa_campo_desconhecido(self):
        with pytest.raises(ValueError, match="parâmetro desconhecido: inexistente"):
            ParametrosFiscais.com_ajustes({"inexistente": 1})

    def test_com_ajustes_valida(self):
        with pytest.raises(ValueError, match="limiar_alerta"):
            ParametrosFiscais.com_ajustes({"limiar_alerta": D("2")})


class TestEfeitoNasRegras:
    def test_limiar_alerta_muda_a_faixa_de_atencao(self):
        assert classificar_nivel(D("60000"), D("81000")) == NivelAlerta.OK
        assert classificar_nivel(D("60000"), D("81000"), D("0.70")) == NivelAlerta.ATENCAO
        # A borda continua inclusiva com o limiar configurado.
        assert classificar_nivel(D("56700"), D("81000"), D("0.70")) == NivelAlerta.ATENCAO
        assert classificar_nivel(D("56699.99"), D("81000"), D("0.70")) == NivelAlerta.OK

    def test_resumo_usa_limite_e_limiar_configurados(self):
        resumo = calcular_resumo(D("90000"), D("0"), limite=D("130000"), limiar_alerta=D("0.65"))
        assert resumo.limite == D("130000.00")
        assert resumo.restante == D("40000.00")
        assert resumo.excedeu is False
        assert resumo.nivel_alerta == NivelAlerta.ATENCAO

    def test_limite_proporcional_desligado_usa_o_teto_cheio_no_ano_de_abertura(self):
        abertura = date(2026, 7, 1)
        assert calcular_limite_aplicavel(abertura, 2026).valor == D("40500.00")
        cheio = calcular_limite_aplicavel(abertura, 2026, proporcional=False)
        assert cheio.valor == D("81000.00")
        assert cheio.proporcional is False

    def test_limite_proporcional_usa_o_teto_configurado(self):
        abertura = date(2026, 7, 1)
        assert calcular_limite_aplicavel(abertura, 2026, limite_cheio=D("120000")).valor == D(
            "60000.00"
        )

    def test_meta_mensal_configurada_substitui_limite_sobre_12(self):
        serie = calcular_serie_mensal({1: D("5000")}, {}, D("81000"), meta_mensal=D("4000"))
        assert serie[0].meta == D("4000.00")
        assert serie[0].acima_da_meta is True
        assert calcular_serie_mensal({1: D("5000")}, {}, D("81000"))[0].acima_da_meta is False

    def test_limiar_de_concentracao_configurado(self):
        vendas = {"11.111.111/0001-11": D("60"), "22.222.222/0001-22": D("40")}
        assert not any(c.alerta for c in calcular_concentracao_clientes(vendas))
        alerta = calcular_concentracao_clientes(vendas, limiar=D("0.50"))
        assert [c.alerta for c in alerta] == [True, False]


def _projecao(parametros=PARAMETROS_PADRAO, **mudancas):
    base = {
        "faturamento_acumulado": D("50000"),
        "faturamento_ultimos_30_dias": D("5000"),
        "faturamento_ultimos_90_dias": D("15000"),
        "qtd_transacoes_ano": 10,
        "maior_transacao_ano": D("5000"),
        "data_abertura": date(2020, 1, 1),
        "hoje": date(2026, 7, 1),
    }
    base.update(mudancas)
    return calcular_projecao(**base, parametros=parametros)


class TestEfeitoNaProjecao:
    def test_padrao_e_igual_a_nao_passar_parametros(self):
        base = {
            "faturamento_acumulado": D("50000"),
            "faturamento_ultimos_30_dias": D("5000"),
            "faturamento_ultimos_90_dias": D("15000"),
            "qtd_transacoes_ano": 10,
            "maior_transacao_ano": D("5000"),
            "data_abertura": date(2020, 1, 1),
            "hoje": date(2026, 7, 1),
        }
        assert calcular_projecao(**base) == _projecao()

    def test_limite_anual_configurado_muda_teto_e_nivel(self):
        assert _projecao().nivel == NivelRitmo.RISCO
        folgado = _projecao(ParametrosFiscais(limite_anual=D("200000")))
        assert folgado.limite_aplicavel == D("200000.00")
        assert folgado.nivel == NivelRitmo.OK

    def test_margem_de_desenquadramento_configurada(self):
        acima = {"faturamento_acumulado": D("90000")}
        assert _projecao(**acima).nivel == NivelRitmo.ESTOURADO
        margem_curta = ParametrosFiscais(margem_desenquadramento=D("1.05"))
        assert _projecao(margem_curta, **acima).nivel == NivelRitmo.DESENQUADRAMENTO

    def test_limiar_de_alerta_configurado_na_projecao(self):
        # 50.000 de 81.000 = 61,7%: abaixo dos 80% padrão, acima de 60%.
        sem_projecao = {"qtd_transacoes_ano": 1}
        assert _projecao(**sem_projecao).nivel == NivelRitmo.OK
        assert (
            _projecao(ParametrosFiscais(limiar_alerta=D("0.60")), **sem_projecao).nivel
            == NivelRitmo.ATENCAO
        )

    def test_minimos_para_projetar_configurados(self):
        poucos = {"qtd_transacoes_ano": 2}
        assert _projecao(**poucos).projecao_disponivel is False
        assert _projecao(
            ParametrosFiscais(transacoes_minimas_para_projetar=2), **poucos
        ).projecao_disponivel
        cedo = {"hoje": date(2026, 1, 20)}
        assert _projecao(**cedo).projecao_disponivel is False
        assert _projecao(
            ParametrosFiscais(dias_minimos_para_projetar=20), **cedo
        ).projecao_disponivel

    def test_abertura_recente_configurada(self):
        abertura = {"data_abertura": date(2026, 5, 1), "hoje": date(2026, 6, 1)}
        # 32 dias desde a abertura: recente pelo padrão (60), não por 30.
        assert _projecao(**abertura).dias_decorridos == 32
        assert (
            _projecao(ParametrosFiscais(dias_abertura_recente=30), **abertura).dias_decorridos
            == 152
        )

    def test_limiar_de_lancamento_atipico_configurado(self):
        grande = {"maior_transacao_ano": D("35000")}
        assert _projecao(**grande).influenciada_por_lancamento_atipico is True
        assert not _projecao(
            ParametrosFiscais(limiar_lancamento_atipico=D("0.75")), **grande
        ).influenciada_por_lancamento_atipico

    def test_limiar_de_atencao_por_ritmo_configurado(self):
        # Realizado 30.000 (37% de 81.000) com projeção acima de 80%: atenção
        # por ritmo pelo padrão (realizado < 50%), ok com o limiar em 30%.
        ritmo = {
            "faturamento_acumulado": D("30000"),
            "hoje": date(2026, 6, 1),
            "maior_transacao_ano": D("3000"),
        }
        # Projeção: 30.000 / 152 dias x 365 = 72.039 (>= 64.800, < 81.000).
        assert _projecao(**ritmo).nivel == NivelRitmo.ATENCAO_RITMO
        params = ParametrosFiscais(limiar_atencao_ritmo_realizado=D("0.30"))
        assert _projecao(params, **ritmo).nivel == NivelRitmo.OK
