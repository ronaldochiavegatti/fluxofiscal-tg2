"""Camada anticorrupção entre o Insights e o Limits (US-23, ADR-0015).

O Limits é a fonte da verdade transacional. O Insights lê dele em dois momentos:

- **reconstrução** — a lista de transações do usuário (`GET /transactions`),
  para refazer a projeção do zero;
- **conciliação** — o resumo anual (`GET /summary/{email}`), para comparar com
  o que a projeção materializada acumulou.

Aqui mora a tradução: o vocabulário do Limits (`amount`, `tx_type`,
`total_revenue`, `total_despesas`) entra e sai como o vocabulário do Insights
(`valor`, `tipo`, `total_vendas`, `total_compras`). Nenhuma chave do formato do
Limits vaza para o resto do serviço. Campo desconhecido é ignorado; campo
ausente recebe padrão explícito.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx
import structlog

logger = structlog.get_logger("insights.acl_limits")

LIMITS_BASE_URL = os.getenv("LIMITS_BASE_URL", "http://limits:8000")
TIMEOUT_PADRAO = 5.0


@dataclass(frozen=True)
class TransacaoLimits:
    """Uma transação do Limits, já no vocabulário do Insights."""

    valor: float
    tipo: str  # "venda" | "compra"
    data: str  # ISO-8601 (YYYY-MM-DD)


@dataclass(frozen=True)
class ResumoLimits:
    """O resumo anual do Limits, já no vocabulário do Insights."""

    total_vendas: float
    total_compras: float


class LimitsIndisponivel(RuntimeError):
    """O Limits não respondeu ou respondeu fora do contrato. A reconstrução e a
    conciliação abortam — melhor não fazer nada do que gravar número errado."""


class ClienteLimits:
    """Fala HTTP com o Limits. `cliente_http` é injetável para teste (um
    `httpx.Client` com `MockTransport`)."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        cliente_http: httpx.Client | None = None,
        timeout: float = TIMEOUT_PADRAO,
    ) -> None:
        self._base_url = (base_url or LIMITS_BASE_URL).rstrip("/")
        self._proprio = cliente_http is None
        self._http = cliente_http or httpx.Client(base_url=self._base_url, timeout=timeout)

    def fechar(self) -> None:
        if self._proprio:
            self._http.close()

    def __enter__(self) -> ClienteLimits:
        return self

    def __exit__(self, *_: object) -> None:
        self.fechar()

    # -- leitura --

    def transacoes(self, email: str, ano: int) -> list[TransacaoLimits]:
        """Todas as transações do usuário no ano. `GET /transactions`."""
        bruto = self._get("/transactions", params={"email": email, "year": ano})
        if not isinstance(bruto, list):
            raise LimitsIndisponivel("resposta de /transactions não é uma lista")
        return [
            TransacaoLimits(
                valor=float(item["amount"]),
                tipo=str(item["tx_type"]),
                data=str(item["tx_date"]),
            )
            for item in bruto
        ]

    def resumo(self, email: str, ano: int) -> ResumoLimits:
        """O resumo anual, fonte da verdade dos totais. `GET /summary/{email}`."""
        bruto = self._get(f"/summary/{email}", params={"year": ano})
        if not isinstance(bruto, dict):
            raise LimitsIndisponivel("resposta de /summary não é um objeto")
        try:
            return ResumoLimits(
                total_vendas=float(bruto["total_revenue"]),
                total_compras=float(bruto["total_despesas"]),
            )
        except (KeyError, TypeError, ValueError) as erro:
            raise LimitsIndisponivel(f"resumo do Limits fora do contrato: {erro}") from erro

    # -- interno --

    def _get(self, caminho: str, *, params: dict) -> object:
        try:
            resposta = self._http.get(caminho, params=params)
            resposta.raise_for_status()
            return resposta.json()
        except httpx.HTTPError as erro:
            logger.warning("acl_limits.falha", caminho=caminho, erro=str(erro))
            raise LimitsIndisponivel(str(erro)) from erro
