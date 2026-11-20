"""Projeção materializada mínima e aplicação idempotente de eventos (US-21).

Sem FastAPI de propósito: o consumo de eventos roda numa thread e precisa de
uma sessão de banco, não de um request. A US-23 amplia esta projeção com médias
móveis, ritmo e alertas — aqui é só o total por usuário e ano, o suficiente
para os cenários de idempotência e catch-up da US-21.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import structlog
from sqlalchemy import Column, DateTime, Integer, Numeric, String
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base

logger = structlog.get_logger()

Base = declarative_base()

ANO_PADRAO = datetime.now(UTC).year


class EventoProcessado(Base):
    """Idempotência: um `evento_id` só é aplicado uma vez (ADR-0006)."""

    __tablename__ = "eventos_processados"

    evento_id = Column(String, primary_key=True)
    tipo = Column(String, nullable=False)
    processado_em = Column(DateTime, default=lambda: datetime.now(UTC))


class ResumoInsights(Base):
    """Projeção mínima por usuário e ano. A US-23 amplia."""

    __tablename__ = "resumo_insights"

    usuario_email = Column(String, primary_key=True)
    ano = Column(Integer, primary_key=True)
    total_vendas = Column(Numeric(14, 2), nullable=False, default=0)
    total_compras = Column(Numeric(14, 2), nullable=False, default=0)
    qtd_transacoes = Column(Integer, nullable=False, default=0)
    atualizado_em = Column(DateTime, default=lambda: datetime.now(UTC))


def criar_tabelas(engine, tentativas: int = 5, espera: int = 2) -> None:
    for n in range(1, tentativas + 1):
        try:
            Base.metadata.create_all(bind=engine)
            return
        except OperationalError:
            if n == tentativas:
                raise
            time.sleep(espera)


def _ano_de(dados: dict) -> int:
    data = str(dados.get("tx_date") or "")
    return int(data[:4]) if data[:4].isdigit() else ANO_PADRAO


def _resumo(db, email: str, ano: int) -> ResumoInsights:
    linha = db.get(ResumoInsights, (email, ano))
    if linha is None:
        linha = ResumoInsights(usuario_email=email, ano=ano)
        db.add(linha)
    return linha


def _aplicar_valor(linha: ResumoInsights, valor: float, tx_type: str, sinal: int) -> None:
    if tx_type == "venda":
        linha.total_vendas = float(linha.total_vendas or 0) + sinal * valor
    else:
        linha.total_compras = float(linha.total_compras or 0) + sinal * valor
    linha.atualizado_em = datetime.now(UTC)


def projetar(linha: ResumoInsights, tipo: str, dados: dict) -> None:
    if tipo == "transacao.criada":
        _aplicar_valor(linha, float(dados["valor"]), dados["tx_type"], +1)
        linha.qtd_transacoes = (linha.qtd_transacoes or 0) + 1
    elif tipo == "transacao.removida":
        _aplicar_valor(linha, float(dados["valor"]), dados["tx_type"], -1)
        linha.qtd_transacoes = max(0, (linha.qtd_transacoes or 0) - 1)
    elif tipo == "transacao.atualizada":
        _aplicar_valor(linha, float(dados["antes"]["valor"]), dados["antes"]["tx_type"], -1)
        _aplicar_valor(linha, float(dados["depois"]["valor"]), dados["depois"]["tx_type"], +1)


def aplicar_transacao(linha: ResumoInsights, valor: float, tipo: str) -> None:
    """Aplica uma transação 'crua' à projeção — a reconstrução (US-23) parte da
    lista de transações do Limits, não de eventos, e replica a mesma soma."""
    _aplicar_valor(linha, float(valor), tipo, +1)
    linha.qtd_transacoes = (linha.qtd_transacoes or 0) + 1


def resumo_para(db, email: str, ano: int) -> ResumoInsights:
    """Linha da projeção do usuário/ano, criada e anexada à sessão se faltar."""
    return _resumo(db, email, ano)


def zerar_usuario(db, email: str, ano: int) -> None:
    """Remove a projeção do usuário/ano. A reconstrução chama isto antes de
    refazer, para que uma fórmula corrigida não some sobre o total antigo."""
    linha = db.get(ResumoInsights, (email, ano))
    if linha is not None:
        db.delete(linha)


def emails_com_projecao(db, ano: int | None = None) -> list[str]:
    """E-mails distintos que já têm projeção — o alvo da conciliação e da
    reconstrução em massa."""
    consulta = db.query(ResumoInsights.usuario_email)
    if ano is not None:
        consulta = consulta.filter(ResumoInsights.ano == ano)
    return sorted({linha[0] for linha in consulta.all()})


def aplicar_evento(session_factory, envelope: dict) -> None:
    """Idempotente e atômico: marca o `evento_id` e ajusta a projeção na mesma
    transação. Reentrega para no `db.get` do evento_id."""
    with session_factory() as db:
        if db.get(EventoProcessado, envelope["evento_id"]) is not None:
            return
        db.add(EventoProcessado(evento_id=envelope["evento_id"], tipo=envelope["tipo"]))

        dados = envelope["dados"]
        email = dados.get("email")
        if email:
            projetar(_resumo(db, email, _ano_de(dados)), envelope["tipo"], dados)
        db.commit()
    logger.info("evento.aplicado", tipo=envelope["tipo"], evento_id=envelope["evento_id"])
