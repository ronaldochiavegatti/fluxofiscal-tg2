"""Testes do motor de ritmo de vendas (US-28).

Sem banco, sem HTTP: só as regras de `docs/dashboard-v2.md` §2, que este
arquivo verifica linha a linha. As bordas de cada guarda têm caso próprio —
é onde um erro de sinal se esconde, e aqui um erro de sinal é dizer a um MEI
que ele está seguro quando o ritmo diz o contrário.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.dominio import (
    DIAS_ABERTURA_RECENTE,
    DIAS_MINIMOS_PARA_PROJETAR,
    LIMITE_ANUAL_MEI,
    TRANSACOES_MINIMAS_PARA_PROJETAR,
    NivelRitmo,
    Tendencia,
    calcular_limite_aplicavel,
    calcular_projecao,
)

ANO = 2026  # não bissexto: 365 dias — verificado em TestTotalDiasAno.
JAN1 = date(ANO, 1, 1)
ABERTURA_ANTIGA = date(2018, 1, 1)  # havia MEI antes do ano corrente: limite cheio.


def _hoje_no_dia(dia_do_ano: int) -> date:
    """`dia_do_ano`-ésimo dia decorrido de `ANO` (1º de janeiro = dia 1)."""
    return JAN1 + timedelta(days=dia_do_ano - 1)


def _projetar(
    *,
    faturamento_acumulado: Decimal,
    hoje: date,
    data_abertura: date = ABERTURA_ANTIGA,
    faturamento_ultimos_30_dias: Decimal = Decimal("0.00"),
    faturamento_ultimos_90_dias: Decimal = Decimal("0.00"),
    qtd_transacoes_ano: int = TRANSACOES_MINIMAS_PARA_PROJETAR,
    maior_transacao_ano: Decimal = Decimal("0.01"),
):
    """Atalho: preenche os parâmetros que um teste específico não quer variar."""
    return calcular_projecao(
        faturamento_acumulado=faturamento_acumulado,
        faturamento_ultimos_30_dias=faturamento_ultimos_30_dias,
        faturamento_ultimos_90_dias=faturamento_ultimos_90_dias,
        qtd_transacoes_ano=qtd_transacoes_ano,
        maior_transacao_ano=maior_transacao_ano,
        data_abertura=data_abertura,
        hoje=hoje,
    )


class TestTotalDiasAno:
    def test_2026_nao_e_bissexto(self):
        assert (
            _projetar(faturamento_acumulado=Decimal("0"), hoje=_hoje_no_dia(200)).total_dias_ano
            == 365
        )

    def test_2028_e_bissexto(self):
        hoje = date(2028, 1, 1) + timedelta(days=199)
        assert _projetar(faturamento_acumulado=Decimal("0"), hoje=hoje).total_dias_ano == 366


class TestLimiteAplicavel:
    def test_abertura_em_ano_anterior_e_limite_cheio(self):
        limite = calcular_limite_aplicavel(ABERTURA_ANTIGA, ANO)

        assert limite.valor == LIMITE_ANUAL_MEI
        assert limite.meses_de_atividade is None
        assert limite.proporcional is False

    def test_abertura_em_julho_e_proporcional_a_6_meses(self):
        """Cenário Gherkin: "Limite proporcional para abertura no ano"."""
        limite = calcular_limite_aplicavel(date(ANO, 7, 3), ANO)

        assert limite.valor == Decimal("40500.00")
        assert limite.meses_de_atividade == 6
        assert limite.proporcional is True

    def test_abertura_em_janeiro_equivale_ao_limite_cheio(self):
        limite = calcular_limite_aplicavel(date(ANO, 1, 15), ANO)

        assert limite.valor == LIMITE_ANUAL_MEI
        assert limite.meses_de_atividade == 12

    def test_abertura_em_dezembro_e_um_doze_avos(self):
        limite = calcular_limite_aplicavel(date(ANO, 12, 20), ANO)

        assert limite.valor == Decimal("6750.00")
        assert limite.meses_de_atividade == 1

    def test_abertura_depois_do_ano_de_referencia_e_invalida(self):
        with pytest.raises(ValueError, match="não pode ser depois"):
            calcular_limite_aplicavel(date(ANO + 1, 1, 1), ANO)

    def test_limite_cheio_customizado_e_respeitado(self):
        limite = calcular_limite_aplicavel(ABERTURA_ANTIGA, ANO, limite_cheio=Decimal("120000.00"))

        assert limite.valor == Decimal("120000.00")


class TestCenarioDeReferencia:
    """Cenário Gherkin: "Projeção a partir do ritmo" — os três números do
    critério de aceite, verificados juntos para travar o cenário inteiro."""

    def test_taxa_diaria_projecao_e_data_de_estouro(self):
        projecao = _projetar(
            faturamento_acumulado=Decimal("47304.00"),
            hoje=_hoje_no_dia(168),
            qtd_transacoes_ano=50,
        )

        assert projecao.dias_decorridos == 168
        assert projecao.taxa_diaria == Decimal("281.57")
        assert projecao.projecao_disponivel is True
        assert projecao.projecao_anual == Decimal("102773.57")
        assert projecao.dias_ate_estouro == 120
        assert projecao.data_prevista_estouro == date(ANO, 10, 15)

    def test_arredondar_a_taxa_diaria_antes_de_multiplicar_erraria_a_projecao(self):
        """`281.57 x 365 = 102.773,05`, não `102.773,57`. A projeção precisa
        vir da divisão exata, arredondada só no final — ver o comentário em
        `calcular_projecao`. Este teste existe para que ninguém "simplifique"
        isso de volta."""
        projecao = _projetar(
            faturamento_acumulado=Decimal("47304.00"),
            hoje=_hoje_no_dia(168),
            qtd_transacoes_ano=50,
        )

        assert projecao.projecao_anual != Decimal("281.57") * 365

    def test_indice_de_ritmo_e_tendencia(self):
        """Cenário Gherkin: "Índice de ritmo com tendência" — mesmo cenário de
        referência (taxa diária R$ 281,57), com taxa de referência do teto
        cheio dando R$ 221,92 (`81000 / 365`) e últimos 30 dias acima da
        média do ano, o suficiente para acelerar."""
        projecao = _projetar(
            faturamento_acumulado=Decimal("47304.00"),
            faturamento_ultimos_30_dias=Decimal("9640.00"),
            hoje=_hoje_no_dia(168),
            qtd_transacoes_ano=50,
        )

        assert projecao.taxa_diaria_referencia == Decimal("221.92")
        assert projecao.indice_ritmo == Decimal("1.27")
        assert projecao.tendencia is Tendencia.ACELERANDO


class TestLancamentoAtipico:
    """Cenário Gherkin: "Lançamento atípico é sinalizado"."""

    def test_venda_unica_de_65_por_cento_e_sinalizada(self):
        projecao = _projetar(
            faturamento_acumulado=Decimal("10000.00"),
            maior_transacao_ano=Decimal("6500.00"),
            hoje=_hoje_no_dia(200),
        )

        assert projecao.influenciada_por_lancamento_atipico is True

    def test_exatamente_60_por_cento_nao_e_atipico(self):
        """A guarda é "acima de 60%" — 60% exato ainda é normal."""
        projecao = _projetar(
            faturamento_acumulado=Decimal("10000.00"),
            maior_transacao_ano=Decimal("6000.00"),
            hoje=_hoje_no_dia(200),
        )

        assert projecao.influenciada_por_lancamento_atipico is False

    def test_60_01_por_cento_ja_e_atipico(self):
        projecao = _projetar(
            faturamento_acumulado=Decimal("10000.00"),
            maior_transacao_ano=Decimal("6001.00"),
            hoje=_hoje_no_dia(200),
        )

        assert projecao.influenciada_por_lancamento_atipico is True

    def test_sem_faturamento_nao_e_atipico(self):
        """`0/0` indefinido — a guarda não dispara sem faturamento, ela some."""
        projecao = _projetar(faturamento_acumulado=Decimal("0.00"), hoje=_hoje_no_dia(200))

        assert projecao.influenciada_por_lancamento_atipico is False


class TestGuardaDeDiasMinimos:
    def test_abaixo_do_minimo_nao_projeta(self):
        projecao = _projetar(
            faturamento_acumulado=Decimal("5000.00"),
            hoje=_hoje_no_dia(DIAS_MINIMOS_PARA_PROJETAR - 1),
            qtd_transacoes_ano=10,
        )

        assert projecao.projecao_disponivel is False
        assert projecao.motivo_indisponivel == "dados insuficientes para projeção"
        assert projecao.projecao_anual is None
        assert projecao.indice_ritmo is None
        assert projecao.aceleracao is None
        assert projecao.dias_ate_estouro is None
        assert projecao.data_prevista_estouro is None

    def test_exatamente_no_minimo_ja_projeta(self):
        projecao = _projetar(
            faturamento_acumulado=Decimal("5000.00"),
            hoje=_hoje_no_dia(DIAS_MINIMOS_PARA_PROJETAR),
            qtd_transacoes_ano=10,
        )

        assert projecao.projecao_disponivel is True
        assert projecao.projecao_anual is not None

    def test_faturamento_seguro_por_mes_independe_da_guarda(self):
        """FS não é extrapolado do ritmo — é só o que resta dividido pelos
        meses restantes. Continua calculado mesmo sem dado para projetar."""
        projecao = _projetar(
            faturamento_acumulado=Decimal("5000.00"),
            hoje=_hoje_no_dia(DIAS_MINIMOS_PARA_PROJETAR - 1),
            qtd_transacoes_ano=1,
        )

        assert projecao.projecao_disponivel is False
        assert projecao.faturamento_seguro_mes > 0


class TestGuardaDeTransacoesMinimas:
    def test_abaixo_do_minimo_nao_projeta(self):
        projecao = _projetar(
            faturamento_acumulado=Decimal("5000.00"),
            hoje=_hoje_no_dia(200),
            qtd_transacoes_ano=TRANSACOES_MINIMAS_PARA_PROJETAR - 1,
        )

        assert projecao.projecao_disponivel is False
        assert projecao.motivo_indisponivel == "dados insuficientes para projeção"

    def test_exatamente_no_minimo_ja_projeta(self):
        projecao = _projetar(
            faturamento_acumulado=Decimal("5000.00"),
            hoje=_hoje_no_dia(200),
            qtd_transacoes_ano=TRANSACOES_MINIMAS_PARA_PROJETAR,
        )

        assert projecao.projecao_disponivel is True


class TestSemFaturamentoRegistrado:
    """`td = 0`: a projeção continua "disponível" (há dado suficiente), mas o
    dia do estouro é indefinido — infinito, na fórmula normativa."""

    def test_taxa_diaria_zero_nao_projeta_data_de_estouro(self):
        projecao = _projetar(
            faturamento_acumulado=Decimal("0.00"),
            hoje=_hoje_no_dia(200),
            qtd_transacoes_ano=5,
        )

        assert projecao.projecao_disponivel is True
        assert projecao.taxa_diaria == Decimal("0.00")
        assert projecao.projecao_anual == Decimal("0.00")
        assert projecao.dias_ate_estouro is None
        assert projecao.data_prevista_estouro is None
        assert projecao.motivo_indisponivel == "sem faturamento registrado"

    def test_taxa_diaria_zero_torna_aceleracao_indefinida(self):
        projecao = _projetar(
            faturamento_acumulado=Decimal("0.00"),
            faturamento_ultimos_30_dias=Decimal("500.00"),
            hoje=_hoje_no_dia(200),
            qtd_transacoes_ano=5,
        )

        assert projecao.aceleracao is None

    def test_sem_aceleracao_a_tendencia_e_estavel(self):
        """Sem base para apontar direção, o painel não inventa uma."""
        projecao = _projetar(
            faturamento_acumulado=Decimal("0.00"),
            faturamento_ultimos_30_dias=Decimal("500.00"),
            hoje=_hoje_no_dia(200),
            qtd_transacoes_ano=5,
        )

        assert projecao.tendencia is Tendencia.ESTAVEL


class TestTaxaDiaria90Dias:
    """`td90` — o ritmo "otimista" do cone de projeção da US-26
    (`docs/dashboard-v2.md` §3.1). Mesma conta de `td30`, janela de 90 dias."""

    def test_calcula_a_media_dos_ultimos_90_dias(self):
        projecao = _projetar(
            faturamento_acumulado=Decimal("10000.00"),
            faturamento_ultimos_90_dias=Decimal("9000.00"),
            hoje=_hoje_no_dia(200),
            qtd_transacoes_ano=10,
        )

        assert projecao.taxa_diaria_90d == Decimal("100.00")

    def test_sem_vendas_recentes_e_zero_nao_none(self):
        """Ao contrário de `aceleracao`, `td90` não guarda por falta de dado —
        é só uma média, não uma razão que possa ficar indefinida."""
        projecao = _projetar(faturamento_acumulado=Decimal("0.00"), hoje=_hoje_no_dia(200))

        assert projecao.taxa_diaria_90d == Decimal("0.00")


class TestTendencia:
    """`AC = td30 / td` — `docs/dashboard-v2.md` §2.2: `> 1` acelera, `< 1`
    desacelera."""

    def test_ultimos_30_dias_acima_da_media_do_ano_acelera(self):
        projecao = _projetar(
            faturamento_acumulado=Decimal("10000.00"),
            faturamento_ultimos_30_dias=Decimal("3000.00"),  # td30=100 > td
            hoje=_hoje_no_dia(200),
            qtd_transacoes_ano=10,
        )

        assert projecao.tendencia is Tendencia.ACELERANDO

    def test_ultimos_30_dias_abaixo_da_media_do_ano_desacelera(self):
        projecao = _projetar(
            faturamento_acumulado=Decimal("10000.00"),
            faturamento_ultimos_30_dias=Decimal("60.00"),  # td30=2 < td
            hoje=_hoje_no_dia(200),
            qtd_transacoes_ano=10,
        )

        assert projecao.tendencia is Tendencia.DESACELERANDO

    def test_ultimos_30_dias_no_mesmo_ritmo_fica_estavel(self):
        # F=10000 em D=200 -> td=50; para td30=50 exato, 30 dias somam 1500.
        projecao = _projetar(
            faturamento_acumulado=Decimal("10000.00"),
            faturamento_ultimos_30_dias=Decimal("1500.00"),
            hoje=_hoje_no_dia(200),
            qtd_transacoes_ano=10,
        )

        assert projecao.aceleracao == Decimal("1.00")
        assert projecao.tendencia is Tendencia.ESTAVEL


class TestAberturaRecente:
    """Abaixo de `DIAS_ABERTURA_RECENTE`, a taxa diária usa os dias desde a
    abertura — não desde 1º de janeiro, que diluiria o ritmo real de um MEI
    recém-aberto."""

    def test_abertura_ha_menos_de_60_dias_usa_dias_desde_a_abertura(self):
        hoje = _hoje_no_dia(200)
        abertura_recente = hoje - timedelta(days=DIAS_ABERTURA_RECENTE - 2)  # 59 dias atrás

        projecao = _projetar(
            faturamento_acumulado=Decimal("5000.00"),
            hoje=hoje,
            data_abertura=abertura_recente,
            qtd_transacoes_ano=10,
        )

        assert projecao.dias_decorridos == DIAS_ABERTURA_RECENTE - 1  # 59, não 200

    def test_exatamente_60_dias_ja_usa_desde_1_de_janeiro(self):
        hoje = _hoje_no_dia(200)
        abertura_no_limite = hoje - timedelta(days=DIAS_ABERTURA_RECENTE - 1)  # 60 dias atrás

        projecao = _projetar(
            faturamento_acumulado=Decimal("5000.00"),
            hoje=hoje,
            data_abertura=abertura_no_limite,
            qtd_transacoes_ano=10,
        )

        assert projecao.dias_decorridos == 200  # desde 1º de janeiro, não desde a abertura

    def test_abertura_recente_tambem_aplica_o_limite_proporcional(self):
        """As duas guardas compõem: MEI aberto há pouco, no mesmo ano — o
        limite já é proporcional aos meses de atividade."""
        hoje = date(ANO, 8, 10)
        abertura = date(ANO, 7, 20)  # < 60 dias antes de `hoje`

        projecao = _projetar(
            faturamento_acumulado=Decimal("1000.00"), hoje=hoje, data_abertura=abertura
        )

        assert projecao.meses_de_atividade == 6  # jul..dez
        assert projecao.limite_aplicavel == Decimal("40500.00")


class TestNiveis:
    """Do mais brando ao mais severo. `D = A` (hoje = 31/12) nos testes que só
    olham o realizado — assim `projeção == faturamento` e o nível não
    depende do ritmo, só do acumulado."""

    FIM_DO_ANO = _hoje_no_dia(365)

    def test_ok_sem_faturamento_relevante(self):
        projecao = _projetar(faturamento_acumulado=Decimal("1000.00"), hoje=self.FIM_DO_ANO)
        assert projecao.nivel is NivelRitmo.OK

    def test_atencao_realizado_entre_80_e_100_por_cento(self):
        projecao = _projetar(
            faturamento_acumulado=Decimal("68850.00"), hoje=self.FIM_DO_ANO
        )  # 85% de L
        assert projecao.nivel is NivelRitmo.ATENCAO

    def test_estourado_no_limite_exato_ainda_nao_e_desenquadramento(self):
        projecao = _projetar(faturamento_acumulado=LIMITE_ANUAL_MEI, hoje=self.FIM_DO_ANO)
        assert projecao.nivel is NivelRitmo.ESTOURADO

    def test_desenquadramento_acima_de_120_por_cento(self):
        projecao = _projetar(
            faturamento_acumulado=Decimal("105300.00"), hoje=self.FIM_DO_ANO
        )  # 130%
        assert projecao.nivel is NivelRitmo.DESENQUADRAMENTO

    def test_desenquadramento_e_borda_exclusiva(self):
        """`> 1,2 L`, não `>=` — exatamente 120% ainda é só "estourado"."""
        projecao = _projetar(
            faturamento_acumulado=Decimal("97200.00"), hoje=self.FIM_DO_ANO
        )  # 120%
        assert projecao.nivel is NivelRitmo.ESTOURADO

    def test_risco_quando_projecao_ultrapassa_o_limite_mas_realizado_nao(self):
        # D=100 dias, F=25000: projeção = 25000/100*365 = 91.250 > 81.000,
        # com o realizado (25000) bem abaixo do teto.
        projecao = _projetar(
            faturamento_acumulado=Decimal("25000.00"), hoje=_hoje_no_dia(100), qtd_transacoes_ano=10
        )

        assert projecao.projecao_anual == Decimal("91250.00")
        assert projecao.nivel is NivelRitmo.RISCO

    def test_atencao_ritmo_quando_projecao_alta_mas_realizado_ainda_baixo(self):
        # D=120, F=24300 (30% de L): projeção = 24300/120*365 = 73.912,50 —
        # acima de 80% do teto, mas o realizado está bem abaixo de 50%.
        projecao = _projetar(
            faturamento_acumulado=Decimal("24300.00"), hoje=_hoje_no_dia(120), qtd_transacoes_ano=10
        )

        assert projecao.projecao_anual == Decimal("73912.50")
        assert projecao.nivel is NivelRitmo.ATENCAO_RITMO

    def test_zona_sem_regra_explicita_cai_em_ok(self):
        """`docs/dashboard-v2.md` não cobre realizado em [50%, 80%) do teto
        com projeção em [80%, 100%] — nem "atencao" (pede realizado >= 80%)
        nem "atencao_ritmo" (pede realizado < 50%) casam. Escolha de
        implementação: o padrão seguro é não alarmar sem regra clara."""
        # D=258, F=48600 (60% de L): projeção = 48600/258*365 ≈ 68.755,81 —
        # entre 80% e 100% do teto.
        projecao = _projetar(
            faturamento_acumulado=Decimal("48600.00"), hoje=_hoje_no_dia(258), qtd_transacoes_ano=10
        )

        assert Decimal("64800.00") < projecao.projecao_anual < LIMITE_ANUAL_MEI
        assert projecao.nivel is NivelRitmo.OK

    def test_dado_insuficiente_ainda_classifica_pelo_realizado(self):
        """Sem projeção confiável, os níveis que só olham o realizado
        continuam válidos — só os que dependem de `P` ficam fora do ar."""
        projecao = _projetar(
            faturamento_acumulado=Decimal("68850.00"),  # 85% de L
            hoje=_hoje_no_dia(DIAS_MINIMOS_PARA_PROJETAR - 1),
            qtd_transacoes_ano=10,
        )

        assert projecao.projecao_disponivel is False
        assert projecao.nivel is NivelRitmo.ATENCAO

    def test_risco_nao_dispara_sem_dado_suficiente_para_projetar(self):
        """Mesmos números do teste de "risco" acima, mas com transação de
        menos que o mínimo: sem `P`, o nível cai para o que o realizado
        sozinho sustenta — aqui, `ok`."""
        projecao = _projetar(
            faturamento_acumulado=Decimal("25000.00"),
            hoje=_hoje_no_dia(100),
            qtd_transacoes_ano=TRANSACOES_MINIMAS_PARA_PROJETAR - 1,
        )

        assert projecao.projecao_disponivel is False
        assert projecao.nivel is NivelRitmo.OK


class TestFaturamentoSeguroPorMes:
    def test_divide_o_restante_pelos_meses_que_faltam(self):
        # 31/12: 1 mês restante (o próprio dezembro).
        projecao = _projetar(faturamento_acumulado=Decimal("57000.00"), hoje=TestNiveis.FIM_DO_ANO)

        assert projecao.faturamento_seguro_mes == Decimal("24000.00")

    def test_nunca_fica_negativo_com_o_limite_ja_ultrapassado(self):
        projecao = _projetar(faturamento_acumulado=Decimal("100000.00"), hoje=TestNiveis.FIM_DO_ANO)

        assert projecao.faturamento_seguro_mes == Decimal("0.00")


class TestValidacoes:
    def test_faturamento_negativo_e_invalido(self):
        with pytest.raises(ValueError, match="não pode ser negativo"):
            _projetar(faturamento_acumulado=Decimal("-1"), hoje=_hoje_no_dia(200))

    def test_quantidade_de_transacoes_negativa_e_invalida(self):
        with pytest.raises(ValueError, match="não pode ser negativo"):
            _projetar(
                faturamento_acumulado=Decimal("100"), hoje=_hoje_no_dia(200), qtd_transacoes_ano=-1
            )

    def test_abertura_depois_de_hoje_e_invalida(self):
        hoje = _hoje_no_dia(100)
        with pytest.raises(ValueError, match="não pode ser depois de hoje"):
            _projetar(
                faturamento_acumulado=Decimal("100"),
                hoje=hoje,
                data_abertura=hoje + timedelta(days=1),
            )
