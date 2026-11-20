"""Parâmetros das regras fiscais do MEI, configuráveis por usuário (#91).

Os números que as regras usam — teto anual, faixa de alerta, margem de
desenquadramento, meta mensal, alerta de concentração de cliente e os limiares
da projeção de ritmo — mudam quando muda o regulamento do MEI, e alguns são
escolha pessoal (a meta do mês, a partir de quanto avisar). Por isso as regras
os recebem em `ParametrosFiscais` em vez de lê-los de uma constante.

Este módulo é a folha do pacote: não importa nenhum outro módulo de
`dominio/`, e os demais importam os valores padrão daqui. Os padrões são os
valores oficiais vigentes quando o sistema foi escrito e servem só de ponto de
partida para quem nunca configurou nada — o sistema não os atualiza sozinho
quando a lei muda (decisão registrada na issue #91).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import Decimal

# ---------------------------------------------------------------------------
# Valores padrão
# ---------------------------------------------------------------------------

#: Teto anual de faturamento do MEI, R$ 81.000,00 desde 2018.
LIMITE_ANUAL_MEI = Decimal("81000.00")

#: A partir de 80% do teto, o MEI entra em faixa de alerta.
LIMIAR_ALERTA = Decimal("0.80")

#: Ultrapassar o teto em até 20% gera DAS complementar e migração para
#: Microempresa a partir de janeiro seguinte. Acima de 20%, o desenquadramento
#: retroage a 1º de janeiro do ano do estouro, com juros — consequência de outra natureza,
#: e por isso um nível de alerta próprio.
MARGEM_DESENQUADRAMENTO = Decimal("1.20")

#: Acima disso, um único cliente concentra risco de dependência —
#: `docs/dashboard-v2.md` §2.5.
LIMIAR_CONCENTRACAO_CLIENTE = Decimal("0.70")

#: Abaixo disso, extrapolar para o ano é ruído, não sinal.
DIAS_MINIMOS_PARA_PROJETAR = 30

#: Idem, em número de transações — três pontos é o mínimo para falar em ritmo.
TRANSACOES_MINIMAS_PARA_PROJETAR = 3

#: Abaixo disso, a taxa diária usa os dias desde a abertura do MEI, não desde
#: 1º de janeiro — nos primeiros dias, "desde janeiro" dilui o ritmo real.
DIAS_ABERTURA_RECENTE = 60

#: Uma única venda acima disso do faturamento do ano marca a projeção como
#: influenciada por lançamento atípico (ela continua sendo calculada).
LIMIAR_LANCAMENTO_ATIPICO = Decimal("0.60")

#: Realizado abaixo disso, mesmo com ritmo alto, ainda não é "atenção" —
#: é o `atencao_ritmo`, mais brando.
LIMIAR_ATENCAO_RITMO_REALIZADO = Decimal("0.50")

#: Teto de sanidade para valores monetários configurados: a coluna
#: `Numeric(10, 2)` das transações comporta até 99.999.999,99.
VALOR_MAXIMO = Decimal("99999999.99")


@dataclass(frozen=True, slots=True)
class ParametrosFiscais:
    """Os números que as regras fiscais usam. Imutável e sempre válido: um
    valor fora da faixa levanta `ValueError` na construção, nunca chega a uma
    regra."""

    # Regras do MEI ----------------------------------------------------------
    limite_anual: Decimal = LIMITE_ANUAL_MEI
    limite_proporcional: bool = True
    """No ano de abertura, o teto é proporcional aos meses de atividade."""
    margem_desenquadramento: Decimal = MARGEM_DESENQUADRAMENTO
    """Fator sobre o teto (1,20 = 20% acima) a partir do qual o estouro é
    desenquadramento retroativo."""

    # Metas e alertas pessoais ---------------------------------------------
    limiar_alerta: Decimal = LIMIAR_ALERTA
    """Fração do teto (0,80 = 80%) a partir da qual o painel avisa."""
    meta_mensal: Decimal | None = None
    """Meta de vendas por mês. `None` = teto aplicável ÷ 12."""
    limiar_concentracao_cliente: Decimal = LIMIAR_CONCENTRACAO_CLIENTE

    # Projeção de ritmo ----------------------------------------------------
    dias_minimos_para_projetar: int = DIAS_MINIMOS_PARA_PROJETAR
    transacoes_minimas_para_projetar: int = TRANSACOES_MINIMAS_PARA_PROJETAR
    dias_abertura_recente: int = DIAS_ABERTURA_RECENTE
    limiar_lancamento_atipico: Decimal = LIMIAR_LANCAMENTO_ATIPICO
    limiar_atencao_ritmo_realizado: Decimal = LIMIAR_ATENCAO_RITMO_REALIZADO

    def __post_init__(self) -> None:
        _exigir_faixa("limite_anual", self.limite_anual, Decimal("0.01"), VALOR_MAXIMO)
        _exigir_faixa(
            "margem_desenquadramento", self.margem_desenquadramento, Decimal("1"), Decimal("5")
        )
        _exigir_fracao("limiar_alerta", self.limiar_alerta)
        if self.meta_mensal is not None:
            _exigir_faixa("meta_mensal", self.meta_mensal, Decimal("0.01"), VALOR_MAXIMO)
        _exigir_fracao("limiar_concentracao_cliente", self.limiar_concentracao_cliente)
        _exigir_faixa("dias_minimos_para_projetar", self.dias_minimos_para_projetar, 1, 366)
        _exigir_faixa(
            "transacoes_minimas_para_projetar", self.transacoes_minimas_para_projetar, 1, 10_000
        )
        _exigir_faixa("dias_abertura_recente", self.dias_abertura_recente, 0, 366)
        _exigir_fracao("limiar_lancamento_atipico", self.limiar_lancamento_atipico)
        _exigir_fracao("limiar_atencao_ritmo_realizado", self.limiar_atencao_ritmo_realizado)

    @classmethod
    def com_ajustes(cls, ajustes: dict[str, object]) -> ParametrosFiscais:
        """Padrão com os campos de `ajustes` sobrescritos. Chave desconhecida
        é erro (`ValueError`), não é ignorada: um nome digitado errado faria a
        configuração do usuário sumir em silêncio."""
        nomes = {campo.name for campo in fields(cls)}
        desconhecidos = sorted(set(ajustes) - nomes)
        if desconhecidos:
            raise ValueError(f"parâmetro desconhecido: {', '.join(desconhecidos)}")
        return cls(**ajustes)  # type: ignore[arg-type]


def _exigir_faixa(
    nome: str, valor: Decimal | int, minimo: Decimal | int, maximo: Decimal | int
) -> None:
    if isinstance(valor, bool) or not minimo <= valor <= maximo:
        raise ValueError(f"{nome} deve estar entre {minimo} e {maximo}, recebido {valor}")


def _exigir_fracao(nome: str, valor: Decimal) -> None:
    """Fração estritamente positiva, no máximo 1 (100%)."""
    if not Decimal("0") < valor <= Decimal("1"):
        raise ValueError(f"{nome} deve estar entre 0 (exclusive) e 1, recebido {valor}")


#: Os valores oficiais de quando o sistema foi escrito — ponto de partida de
#: quem nunca configurou nada.
PARAMETROS_PADRAO = ParametrosFiscais()
