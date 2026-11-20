"""Conciliação da projeção contra o Limits (US-23, ADR-0009).

A projeção materializada é dado duplicado por definição, e dado duplicado
diverge. A mitigação registrada no ADR-0009 é uma verificação noturna que
compara os totais do Insights com o resumo anual do Limits e **alerta** quando
a diferença passa de R$ 0,01 (SLO `conciliacao-projecao`,
`docs/observabilidade/slos.yaml`).

Nesta história o alerta é um `WARNING` estruturado + as métricas de
`metrics.py`. Publicar `alerta.disparado` no barramento (ADR-0006) entra junto
com o motor de alertas da Onda 4, que é quem define severidade e destinatário.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass

import structlog

from . import projecao
from .acl_limits import ClienteLimits, LimitsIndisponivel
from .metrics import (
    conciliacao_divergencia_reais,
    conciliacao_divergencias_total,
    conciliacao_execucoes_total,
)

logger = structlog.get_logger("insights.conciliacao")

TOLERANCIA_REAIS = 0.01
ANO_PADRAO = projecao.ANO_PADRAO

# 24 h. `CONCILIACAO_INTERVALO_S=0` desliga o laço (deixa só a rota manual).
INTERVALO_PADRAO_S = 86_400


@dataclass(frozen=True)
class Divergencia:
    email: str
    ano: int
    campo: str  # "total_vendas" | "total_compras"
    projecao: float
    limits: float

    @property
    def diferenca(self) -> float:
        return round(abs(self.projecao - self.limits), 2)

    def como_dict(self) -> dict:
        return {
            "email": self.email,
            "ano": self.ano,
            "campo": self.campo,
            "projecao": self.projecao,
            "limits": self.limits,
            "diferenca": self.diferenca,
        }


def _comparar(email: str, ano: int, proj, resumo) -> list[Divergencia]:
    pares = (
        ("total_vendas", float(proj.total_vendas), resumo.total_vendas),
        ("total_compras", float(proj.total_compras), resumo.total_compras),
    )
    return [
        Divergencia(email=email, ano=ano, campo=campo, projecao=valor_proj, limits=valor_lim)
        for campo, valor_proj, valor_lim in pares
        if abs(valor_proj - valor_lim) > TOLERANCIA_REAIS
    ]


def conciliar(
    session_factory,
    acl: ClienteLimits,
    *,
    ano: int | None = None,
) -> list[Divergencia]:
    """Compara cada projeção com o resumo do Limits. Devolve as divergências
    acima da tolerância; um Limits indisponível aborta sem falso positivo."""
    ano = ano or ANO_PADRAO
    conciliacao_execucoes_total.inc()

    with session_factory() as db:
        emails = projecao.emails_com_projecao(db, ano)

    divergencias: list[Divergencia] = []
    for email in emails:
        with session_factory() as db:
            proj = db.get(projecao.ResumoInsights, (email, ano))
        if proj is None:
            continue
        try:
            resumo = acl.resumo(email, ano)
        except LimitsIndisponivel:
            logger.warning("conciliacao.limits_indisponivel", email=email, ano=ano)
            continue
        divergencias.extend(_comparar(email, ano, proj, resumo))

    _registrar(divergencias)
    return divergencias


def _registrar(divergencias: list[Divergencia]) -> None:
    pior_por_campo: dict[str, float] = {"total_vendas": 0.0, "total_compras": 0.0}
    for d in divergencias:
        conciliacao_divergencias_total.labels(campo=d.campo).inc()
        pior_por_campo[d.campo] = max(pior_por_campo.get(d.campo, 0.0), d.diferenca)
        logger.warning(
            "conciliacao.divergencia",
            email=d.email,
            ano=d.ano,
            campo=d.campo,
            projecao=d.projecao,
            limits=d.limits,
            diferenca=d.diferenca,
        )
    for campo, pior in pior_por_campo.items():
        conciliacao_divergencia_reais.labels(campo=campo).set(pior)
    if not divergencias:
        logger.info("conciliacao.ok")


# ---------------------------------------------------------------------------
#  Laço noturno — thread no lifespan, no espírito do Publicador do Limits
# ---------------------------------------------------------------------------


def intervalo_s() -> int:
    try:
        return int(os.getenv("CONCILIACAO_INTERVALO_S", str(INTERVALO_PADRAO_S)))
    except ValueError:
        return INTERVALO_PADRAO_S


class Conciliador:
    """Roda `conciliar` a cada `intervalo_s()`. Um erro no meio não derruba a
    thread — loga e tenta de novo na próxima janela."""

    def __init__(self, session_factory, acl_factory, intervalo: int | None = None) -> None:
        self._sessao = session_factory
        self._acl_factory = acl_factory
        self._intervalo = intervalo if intervalo is not None else intervalo_s()
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None

    def _rodada(self) -> None:
        acl = self._acl_factory()
        try:
            conciliar(self._sessao, acl)
        finally:
            fechar = getattr(acl, "fechar", None)
            if callable(fechar):
                fechar()

    def iniciar(self) -> None:
        if self._intervalo <= 0 or (self._thread and self._thread.is_alive()):
            return
        self._parar.clear()
        self._thread = threading.Thread(target=self._loop, name="conciliador", daemon=True)
        self._thread.start()

    def parar(self) -> None:
        self._parar.set()
        if self._thread:
            self._thread.join(timeout=3)

    def _loop(self) -> None:
        while not self._parar.wait(self._intervalo):
            try:
                self._rodada()
            except Exception:
                logger.exception("conciliacao.rodada_falhou")
