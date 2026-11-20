"""Camada anticorrupção (ACL) do agente (US-46).

O resumo financeiro devolvido pelo serviço de Limits é um modelo de OUTRO
contexto. Em vez de ``build_prompt`` ler ``summary.get(...)`` cru — o que faz
qualquer campo novo, renomeado ou removido no Limits vazar direto para o prompt
do modelo —, traduzimos a resposta para o ``RetratoFiscal``, que é o modelo que
o agente entende.

Regra da fronteira:

- campo que o ``RetratoFiscal`` não conhece é **ignorado** (mudança no resumo
  não muda o prompt);
- campo que falta recebe um **padrão explícito** (o prompt não quebra).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

NIVEIS_ALERTA = ("ok", "warning", "exceeded")


@dataclass(frozen=True)
class RetratoFiscal:
    """Visão que o agente tem da situação fiscal do MEI. Vocabulário do agente,
    não do Limits — a tradução é o único ponto que conhece os dois."""

    ano: int | None
    faturamento_vendas: float
    despesas_compras: float
    saldo_liquido: float
    limite_anual: float
    falta_para_o_limite: float
    ultrapassou: bool
    nivel_alerta: str
    percentual_usado: float
    limiar_alerta_percentual: float = 80.0
    """A partir de quantos % do teto o MEI está em alerta — configurável pelo
    usuário no Limits (#91). Sem o campo na resposta, o padrão oficial."""


def _numero(valor: Any, padrao: float = 0.0) -> float:
    if isinstance(valor, bool):
        return padrao
    if isinstance(valor, (int, float)):
        return float(valor)
    if isinstance(valor, str):
        try:
            return float(valor.replace(",", "."))
        except ValueError:
            return padrao
    return padrao


def traduzir_resumo_limits(resposta: dict[str, Any]) -> RetratoFiscal:
    """Traduz a resposta de ``GET /limits/summary`` para o ``RetratoFiscal``."""
    faturamento = _numero(resposta.get("total_revenue"))
    despesas = _numero(resposta.get("total_despesas"))
    saldo = _numero(resposta.get("saldo_liquido"), faturamento - despesas)

    nivel = resposta.get("alert_level", "ok")
    if nivel not in NIVEIS_ALERTA:
        nivel = "ok"

    ano = resposta.get("year")

    return RetratoFiscal(
        ano=ano if isinstance(ano, int) and not isinstance(ano, bool) else None,
        faturamento_vendas=faturamento,
        despesas_compras=despesas,
        saldo_liquido=saldo,
        limite_anual=_numero(resposta.get("annual_limit")),
        falta_para_o_limite=_numero(resposta.get("remaining")),
        ultrapassou=bool(resposta.get("exceeded")),
        nivel_alerta=nivel,
        percentual_usado=_numero(resposta.get("percent_used")),
        limiar_alerta_percentual=_numero(resposta.get("alert_threshold_percent"), 80.0),
    )
