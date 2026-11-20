"""Mês a mês e origem do faturamento (US-27).

Duas perguntas, uma por seção do dashboard v2 (`docs/dashboard-v2.md` §3.1):
como o ano se distribui entre os meses, e de quais clientes vem o
faturamento. A segunda não é só exibição — "concentração de cliente" é um dos
"outros alertas do motor" (§2.5): um único CNPJ acima de 70% do faturamento é
risco de dependência, e possível indício de relação de emprego disfarçada de
MEI. É regra fiscal/de negócio, por isso mora em `dominio/`, não na rota.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .limites import CENTAVO

# Padrão em `parametros.py`, configurável por usuário (#91).
from .parametros import LIMIAR_CONCENTRACAO_CLIENTE


def _arredondar(valor: Decimal) -> Decimal:
    """Cópia local e deliberada de `limites._arredondar` — mesma nota de
    `ritmo._arredondar`: é regra de exibição, não regra fiscal duplicada."""
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class MesResumo:
    """Um mês do ano civil: o que entrou, o que saiu, e se passou da meta."""

    mes: int
    """1 a 12."""

    vendas: Decimal
    despesas: Decimal

    meta: Decimal
    """`limite_aplicavel / 12`, ou a meta mensal configurada pelo usuário
    (#91). Fixa ao longo do ano — diferente do
    faturamento seguro por mês (`ritmo.Projecao.faturamento_seguro_mes`), que
    é recalculado a partir do que falta e some quando o limite já estourou."""

    acima_da_meta: bool


def calcular_serie_mensal(
    vendas_por_mes: dict[int, Decimal],
    despesas_por_mes: dict[int, Decimal],
    limite_aplicavel: Decimal,
    meta_mensal: Decimal | None = None,
) -> list[MesResumo]:
    """Um `MesResumo` por mês de janeiro a dezembro, mês sem lançamento incluso.

    Mês ausente do dicionário vira zero, não é omitido: a lista sempre tem 12
    posições, porque o gráfico de barras do "mês a mês" precisa do eixo
    completo — omitir um mês sem venda deslocaria os rótulos dos meses
    seguintes.
    """
    if limite_aplicavel <= 0:
        raise ValueError(f"limite_aplicavel deve ser positivo, recebido {limite_aplicavel}")

    meta = _arredondar(meta_mensal if meta_mensal is not None else limite_aplicavel / 12)
    return [
        MesResumo(
            mes=mes,
            vendas=(vendas := _arredondar(vendas_por_mes.get(mes, Decimal("0")))),
            despesas=_arredondar(despesas_por_mes.get(mes, Decimal("0"))),
            meta=meta,
            acima_da_meta=vendas > meta,
        )
        for mes in range(1, 13)
    ]


@dataclass(frozen=True, slots=True)
class ConcentracaoCliente:
    """Fatia do faturamento identificado atribuída a um CNPJ."""

    cnpj: str
    valor: Decimal
    percentual: Decimal
    """Sobre o total identificado (soma de `vendas_por_cnpj`), não sobre o
    faturamento do ano inteiro — ver `calcular_concentracao_clientes`."""

    alerta: bool
    """`True` quando `percentual` ultrapassa o limiar (padrão
    `LIMIAR_CONCENTRACAO_CLIENTE`, configurável — #91)."""


def calcular_concentracao_clientes(
    vendas_por_cnpj: dict[str, Decimal],
    limiar: Decimal = LIMIAR_CONCENTRACAO_CLIENTE,
) -> list[ConcentracaoCliente]:
    """Um `ConcentracaoCliente` por CNPJ, do maior para o menor.

    O denominador é o total **identificado** — a soma de `vendas_por_cnpj` —
    não o faturamento total do ano. Nem toda venda tem CNPJ do cliente
    (lançamento manual, documento sem essa informação); dividir pelo
    faturamento total faria essas vendas "desaparecerem" do gráfico sem
    sobrar em lugar nenhum, e um MEI com poucos documentos identificados
    pareceria artificialmente mais concentrado do que é.
    """
    total = sum(vendas_por_cnpj.values(), Decimal("0"))
    if total <= 0:
        return []

    itens = [
        ConcentracaoCliente(
            cnpj=cnpj,
            valor=_arredondar(valor),
            percentual=_arredondar((valor / total) * Decimal("100")),
            alerta=(valor / total) > limiar,
        )
        for cnpj, valor in vendas_por_cnpj.items()
        if valor > 0
    ]
    return sorted(itens, key=lambda item: item.valor, reverse=True)


__all__ = [
    "LIMIAR_CONCENTRACAO_CLIENTE",
    "ConcentracaoCliente",
    "MesResumo",
    "calcular_concentracao_clientes",
    "calcular_serie_mensal",
]
