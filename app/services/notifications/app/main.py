"""Notifications Service — feed de avisos in-app do FluxoFiscal.

Contexto genérico "Notificação" da arquitetura (ADR-0006, tabela de eventos):
consome `alerta.disparado` do barramento e mantém um feed persistente por
usuário, com estado de lido, dispensa lembrada e teto diário.

Este é o **esqueleto** da preparação da Onda 4 (ADR-0019): sobe, responde
`/health`, expõe métricas e traz a fiação comum (observabilidade US-09/US-12,
feature flags US-15, banco). O consumidor de eventos e as regras do feed entram
nas US-29 / US-29b / US-29c, sobre esta base.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import criar_tabelas, engine
from .flags import setup_flags, shutdown_flags
from .observability import setup_metrics, setup_observability, setup_tracing

setup_observability()
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(_: FastAPI):
    criar_tabelas()
    setup_flags(app_name="notifications")
    yield
    shutdown_flags()


app = FastAPI(title="Notifications Service", lifespan=lifespan)

app.add_middleware(CorrelationIdMiddleware, header_name="X-Correlation-Id")

setup_metrics(app, service_name="notifications")
setup_tracing(app, service_name="notifications", engine=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "notifications"}
