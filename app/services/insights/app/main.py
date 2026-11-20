"""Insights Service — modelo de leitura (CQRS) do FluxoFiscal (ADR-0009).

Na US-21 ele ganha o **consumo de eventos** do barramento (ADR-0006): consome
`transacao.criada` / `.atualizada` / `.removida` do Redis Streams e mantém a
projeção de `projecao.py`. O consumo é idempotente, então reentrega não duplica
efeito. O Insights NUNCA escreve dado transacional.

Na US-23 ele ganha as duas garantias do ADR-0009 sobre o modelo derivado:

- **reconstrução** (`POST /_interno/reconstruir`) — joga a projeção fora e a
  refaz a partir do Limits, para corrigir fórmula sem migração de dados;
- **conciliação** (`Conciliador` + `POST /_interno/conciliar`) — compara os
  totais com o resumo do Limits e alerta se divergirem além de R$ 0,01.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import structlog
from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session, sessionmaker

from . import acl_limits, conciliacao, eventos, projecao, reconstrucao
from .flags import esta_ativa, setup_flags, shutdown_flags
from .observability import setup_metrics, setup_observability, setup_tracing
from .projecao import EventoProcessado, ResumoInsights

setup_observability()
logger = structlog.get_logger()

DATABASE_URL = "postgresql+psycopg2://insights_user:insights_password@insights_db:5432/insights_db"

engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

ANO_PADRAO = datetime.now(UTC).year


def criar_tabelas() -> None:
    projecao.criar_tabelas(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def aplicar_evento(envelope: dict) -> None:
    projecao.aplicar_evento(SessionLocal, envelope)


def eventos_ligados() -> bool:
    # US-21: `FORCAR_EVENTOS_OUTBOX=true` liga sem Unleash (CI), no espírito de
    # `OTEL_TRACES_ENABLED`.
    if os.getenv("FORCAR_EVENTOS_OUTBOX", "").lower() == "true":
        return True
    return esta_ativa("eventos-outbox", padrao=False)


_consumidor = eventos.Consumidor(aplicar=aplicar_evento)
_conciliador = conciliacao.Conciliador(
    session_factory=lambda: SessionLocal(),
    acl_factory=lambda: acl_limits.ClienteLimits(),
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    criar_tabelas()
    setup_flags(app_name="insights")
    if eventos_ligados():
        _consumidor.iniciar()
        # A conciliação só faz sentido quando há projeção sendo alimentada.
        _conciliador.iniciar()
    yield
    _conciliador.parar()
    _consumidor.parar()
    shutdown_flags()


app = FastAPI(title="Insights Service", lifespan=lifespan)

app.add_middleware(CorrelationIdMiddleware, header_name="X-Correlation-Id")

setup_metrics(app, service_name="insights")
setup_tracing(app, service_name="insights", engine=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "insights"}


@app.get("/resumo/{email}")
def resumo(email: EmailStr, ano: int | None = None, db: Session = Depends(get_db)):
    """Projeção do usuário, derivada dos eventos. Para o número exato na hora, o
    dashboard continua lendo o Limits (ADR-0009)."""
    ano = ano or ANO_PADRAO
    linha = db.get(ResumoInsights, (email, ano))
    if linha is None:
        return {
            "email": email,
            "ano": ano,
            "total_vendas": 0.0,
            "total_compras": 0.0,
            "qtd_transacoes": 0,
            "atualizado_em": None,
        }
    return {
        "email": email,
        "ano": ano,
        "total_vendas": float(linha.total_vendas),
        "total_compras": float(linha.total_compras),
        "qtd_transacoes": linha.qtd_transacoes,
        "atualizado_em": linha.atualizado_em.isoformat() if linha.atualizado_em else None,
    }


@app.get("/_interno/status")
def status_consumo(db: Session = Depends(get_db)):
    """Evidência do consumo: quantos eventos foram processados e o backlog."""
    processados = db.query(func.count(EventoProcessado.evento_id)).scalar() or 0
    pendentes = _consumidor.pendentes() if eventos_ligados() else 0
    return {"eventos_processados": processados, "eventos_pendentes": pendentes}


class ReconstruirPedido(BaseModel):
    email: EmailStr | None = None
    ano: int | None = None


class ConciliarPedido(BaseModel):
    ano: int | None = None


@app.post("/_interno/reconstruir")
def reconstruir_projecao(pedido: ReconstruirPedido | None = None):
    """Comando administrativo do ADR-0009: refaz a projeção a partir do Limits.
    Sem corpo, refaz todos os usuários com projeção, no ano corrente."""
    pedido = pedido or ReconstruirPedido()
    with acl_limits.ClienteLimits() as acl:
        refeitos = reconstrucao.reconstruir(SessionLocal, acl, email=pedido.email, ano=pedido.ano)
    logger.info("reconstrucao.disparada", alvos=len(refeitos))
    return {"reconstruidos": refeitos, "quantidade": len(refeitos)}


@app.post("/_interno/conciliar")
def conciliar_projecao(pedido: ConciliarPedido | None = None):
    """Roda a conciliação sob demanda — o mesmo caminho da tarefa noturna
    (`Conciliador`), para diagnóstico e para o job de integração da CI."""
    pedido = pedido or ConciliarPedido()
    with acl_limits.ClienteLimits() as acl:
        divergencias = conciliacao.conciliar(SessionLocal, acl, ano=pedido.ano)
    logger.info("conciliacao.disparada", divergencias=len(divergencias))
    return {
        "divergencias": [d.como_dict() for d in divergencias],
        "quantidade": len(divergencias),
        "ok": not divergencias,
    }
