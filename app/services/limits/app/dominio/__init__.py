"""Núcleo de domínio fiscal do MEI.

Este pacote não importa framework, banco de dados nem cliente HTTP. Ele contém
apenas as regras: o que conta para o teto anual, como o nível de alerta é
determinado, como o resumo é composto.

O motivo do isolamento é prático. A regra "só venda conta para o limite" vivia
em três lugares — a consulta do `get_summary`, o filtro do `DashboardPage.tsx`
e as instruções do prompt do agente. Três cópias de uma regra fiscal divergem
com o tempo, e quando divergem o sistema passa a dar orientação errada sobre
desenquadramento, que é a pior falha possível neste domínio.

Ver ADR-0013 e a história US-03.
"""

from .faturamento import (
    LIMIAR_CONCENTRACAO_CLIENTE,
    ConcentracaoCliente,
    MesResumo,
    calcular_concentracao_clientes,
    calcular_serie_mensal,
)
from .limites import (
    LIMIAR_ALERTA,
    LIMITE_ANUAL_MEI,
    MARGEM_DESENQUADRAMENTO,
    NivelAlerta,
    ResumoFiscal,
    TipoTransacao,
    calcular_percentual_usado,
    calcular_resumo,
    classificar_nivel,
)
from .parametros import PARAMETROS_PADRAO, ParametrosFiscais
from .ritmo import (
    DIAS_ABERTURA_RECENTE,
    DIAS_MINIMOS_PARA_PROJETAR,
    LIMIAR_LANCAMENTO_ATIPICO,
    TRANSACOES_MINIMAS_PARA_PROJETAR,
    LimiteAplicavel,
    NivelRitmo,
    Projecao,
    Tendencia,
    calcular_limite_aplicavel,
    calcular_projecao,
)

__all__ = [
    "PARAMETROS_PADRAO",
    "ParametrosFiscais",
    "LIMIAR_ALERTA",
    "LIMITE_ANUAL_MEI",
    "MARGEM_DESENQUADRAMENTO",
    "NivelAlerta",
    "ResumoFiscal",
    "TipoTransacao",
    "calcular_percentual_usado",
    "calcular_resumo",
    "classificar_nivel",
    "DIAS_ABERTURA_RECENTE",
    "DIAS_MINIMOS_PARA_PROJETAR",
    "LIMIAR_LANCAMENTO_ATIPICO",
    "TRANSACOES_MINIMAS_PARA_PROJETAR",
    "LimiteAplicavel",
    "NivelRitmo",
    "Projecao",
    "Tendencia",
    "calcular_limite_aplicavel",
    "calcular_projecao",
    "LIMIAR_CONCENTRACAO_CLIENTE",
    "ConcentracaoCliente",
    "MesResumo",
    "calcular_concentracao_clientes",
    "calcular_serie_mensal",
]
