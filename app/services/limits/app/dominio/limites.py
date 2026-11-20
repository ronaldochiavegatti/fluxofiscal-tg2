"""Limite anual do MEI: o que conta, quanto falta, e quando alertar."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

# Os valores padrão das regras (teto, faixa de alerta, margem) moram em
# `parametros.py`, de onde são configuráveis por usuário (#91). Reexportados
# aqui porque é onde o resto do código sempre os buscou.
from .parametros import LIMIAR_ALERTA, LIMITE_ANUAL_MEI, MARGEM_DESENQUADRAMENTO

# ---------------------------------------------------------------------------
# Constantes do domínio
# ---------------------------------------------------------------------------

#: Duas casas decimais, como qualquer valor monetário em real.
CENTAVO = Decimal("0.01")


class TipoTransacao(StrEnum):
    """Só `VENDA` conta para o teto anual.

    `COMPRA` é despesa do negócio: entra no balancete e no cálculo do lucro,
    nunca no faturamento. Confundir os dois faria o sistema dizer a um MEI que
    ele estourou o limite quando não estourou.
    """

    VENDA = "venda"
    COMPRA = "compra"


class NivelAlerta(StrEnum):
    OK = "ok"
    ATENCAO = "warning"
    EXCEDIDO = "exceeded"


@dataclass(frozen=True, slots=True)
class ResumoFiscal:
    """Retrato do ano para um MEI. Imutável: é resultado de cálculo, não estado."""

    faturamento: Decimal
    """Soma das vendas. É o único número que conta para o teto."""

    despesas: Decimal
    """Soma das compras. Não conta para o teto."""

    saldo_liquido: Decimal
    """Faturamento menos despesas."""

    limite: Decimal
    """Teto aplicável ao ano."""

    restante: Decimal
    """Quanto ainda cabe no teto. Negativo quando já foi ultrapassado."""

    excedeu: bool
    percentual_usado: Decimal
    nivel_alerta: NivelAlerta


# ---------------------------------------------------------------------------
# Regras
# ---------------------------------------------------------------------------


def _arredondar(valor: Decimal) -> Decimal:
    """Arredonda para centavos usando meio-para-cima, a convenção contábil."""
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def classificar_nivel(
    faturamento: Decimal,
    limite: Decimal,
    limiar_alerta: Decimal = LIMIAR_ALERTA,
) -> NivelAlerta:
    """Classifica o nível de alerta pelo faturamento **realizado**.

    A projeção pelo ritmo de vendas é outra coisa e vive em `ritmo.py`
    (US-28). Aqui só existe o que já aconteceu.

    **Bordas.** O teto do MEI é "até R$ 81.000,00", então faturar exatamente
    R$ 81.000,00 **não** ultrapassa o limite — quem fatura o teto exato está no
    limite, não acima dele. Só R$ 81.000,01 excede. A faixa de alerta, ao
    contrário, é inclusiva: exatamente R$ 64.800,00 já é 80% do teto e já
    merece aviso.

    Essa assimetria é deliberada e é a razão de esta função existir. Errar o
    sinal aqui faria o sistema declarar desenquadramento para quem está
    exatamente no limite — orientação fiscal errada, que é a pior falha
    possível neste domínio.
    """
    if limite <= 0:
        raise ValueError(f"limite deve ser positivo, recebido {limite}")

    if faturamento > limite:
        return NivelAlerta.EXCEDIDO
    if faturamento >= limite * limiar_alerta:
        return NivelAlerta.ATENCAO
    return NivelAlerta.OK


def calcular_percentual_usado(faturamento: Decimal, limite: Decimal) -> Decimal:
    """Percentual do teto já consumido.

    Limitado a 999% para que um lançamento absurdo — tipicamente um erro de
    OCR que leu 1.234,56 como 123456,00 — não quebre a formatação da interface
    nem o eixo de um gráfico.
    """
    if limite <= 0:
        raise ValueError(f"limite deve ser positivo, recebido {limite}")

    percentual = (faturamento / limite) * Decimal("100")
    return _arredondar(min(percentual, Decimal("999")))


def calcular_resumo(
    vendas: Decimal,
    compras: Decimal,
    limite: Decimal = LIMITE_ANUAL_MEI,
    limiar_alerta: Decimal = LIMIAR_ALERTA,
) -> ResumoFiscal:
    """Compõe o retrato fiscal do ano a partir dos totais por tipo.

    Recebe os totais já agregados em vez da lista de transações: a agregação é
    responsabilidade do banco, que faz isso melhor, e manter a assinatura assim
    deixa o domínio independente de como os dados são armazenados.
    """
    if vendas < 0:
        raise ValueError(f"vendas não pode ser negativo, recebido {vendas}")
    if compras < 0:
        raise ValueError(f"compras não pode ser negativo, recebido {compras}")

    faturamento = _arredondar(vendas)
    despesas = _arredondar(compras)
    limite = _arredondar(limite)

    return ResumoFiscal(
        faturamento=faturamento,
        despesas=despesas,
        saldo_liquido=_arredondar(faturamento - despesas),
        limite=limite,
        restante=_arredondar(limite - faturamento),
        excedeu=faturamento > limite,
        percentual_usado=calcular_percentual_usado(faturamento, limite),
        nivel_alerta=classificar_nivel(faturamento, limite, limiar_alerta),
    )


__all__ = [
    "CENTAVO",
    "LIMIAR_ALERTA",
    "LIMITE_ANUAL_MEI",
    "MARGEM_DESENQUADRAMENTO",
    "NivelAlerta",
    "ResumoFiscal",
    "TipoTransacao",
    "calcular_percentual_usado",
    "calcular_resumo",
    "classificar_nivel",
]
