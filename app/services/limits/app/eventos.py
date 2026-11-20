"""Publicação de eventos de domínio via Outbox + Redis Streams (US-21, ADR-0006).

O contrato do envelope (`criar_envelope`, `validar_envelope`, ...) é **cópia
literal** de `tools/contratos/eventos.py` — mesma disciplina de `observability.py`
e `flags.py`. Mudou lá, muda aqui e no `insights`. O job "Contrato de eventos"
da CI e `test_eventos.py` de cada serviço guardam o alinhamento.

O que é específico do Limits (o produtor) fica abaixo da linha: o `Publicador`,
que varre a tabela `outbox` e envia ao Redis.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

# `logger` (stdlib, %s) pertence ao contrato copiado de tools/contratos/eventos.py.
# O código do publicador usa `_log` (structlog), como o resto do serviço.
logger = logging.getLogger("limits.eventos")
_log = structlog.get_logger("limits.publicador")

# ---------------------------------------------------------------------------
#  Contrato do envelope — cópia de tools/contratos/eventos.py
# ---------------------------------------------------------------------------

VERSAO_ATUAL = 1

CAMPOS_OBRIGATORIOS = (
    "evento_id",
    "tipo",
    "versao",
    "ocorrido_em",
    "produtor",
    "chave_particao",
    "dados",
)


class EnvelopeInvalido(ValueError):
    """Envelope sem um campo obrigatório ou com campo de tipo errado."""


def criar_envelope(
    tipo: str,
    dados: dict[str, Any],
    *,
    produtor: str,
    chave_particao: str,
    trace_id: str | None = None,
    versao: int = VERSAO_ATUAL,
) -> dict[str, Any]:
    if not tipo or "." not in tipo:
        raise EnvelopeInvalido(f"tipo de evento deve ser 'recurso.acao', recebido: {tipo!r}")
    envelope: dict[str, Any] = {
        "evento_id": str(uuid.uuid4()),
        "tipo": tipo,
        "versao": int(versao),
        "ocorrido_em": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "produtor": produtor,
        "chave_particao": chave_particao,
        "dados": dict(dados),
    }
    if trace_id:
        envelope["trace_id"] = trace_id
    validar_envelope(envelope)
    return envelope


def validar_envelope(envelope: Any) -> None:
    if not isinstance(envelope, dict):
        raise EnvelopeInvalido(f"envelope deve ser um objeto, recebido: {type(envelope).__name__}")
    faltando = [campo for campo in CAMPOS_OBRIGATORIOS if campo not in envelope]
    if faltando:
        raise EnvelopeInvalido(f"envelope sem campo(s) obrigatório(s): {', '.join(faltando)}")
    if not isinstance(envelope["versao"], int) or isinstance(envelope["versao"], bool):
        raise EnvelopeInvalido("campo 'versao' deve ser inteiro")
    if not isinstance(envelope["dados"], dict):
        raise EnvelopeInvalido("campo 'dados' deve ser um objeto")


# ---------------------------------------------------------------------------
#  Produtor — varre a Outbox e publica no Redis Streams
# ---------------------------------------------------------------------------

STREAM = os.getenv("EVENTOS_STREAM", "fluxofiscal:eventos")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")


def conectar_redis():
    """Cliente Redis, ou None se a lib não estiver instalada / URL vazia."""
    if not REDIS_URL:
        return None
    try:
        import redis

        return redis.Redis.from_url(REDIS_URL, decode_responses=True)
    except Exception:
        _log.warning("eventos.redis_indisponivel")
        return None


def publicar_no_stream(redis_cliente, envelope: dict) -> str:
    """XADD do envelope. A stream guarda o JSON num único campo `envelope`."""
    return redis_cliente.xadd(STREAM, {"envelope": json.dumps(envelope)})


class Publicador:
    """Move linhas não enviadas da Outbox para o Redis. Uma varredura é
    atômica por linha: publica, marca `enviado_em`. Se cair no meio, a linha
    não marcada é reenviada — entrega ao-menos-uma-vez, que o consumidor
    idempotente absorve."""

    def __init__(self, session_factory, modelo_outbox, redis_cliente=None, intervalo=0.5):
        self._sessao = session_factory
        self._Outbox = modelo_outbox
        self._redis = redis_cliente or conectar_redis()
        self._intervalo = intervalo
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None

    def varrer(self, limite: int = 100) -> int:
        """Uma passada. Devolve quantos eventos publicou."""
        if self._redis is None:
            self._redis = conectar_redis()
        if self._redis is None:
            return 0

        publicados = 0
        with self._sessao() as db:
            pendentes = (
                db.query(self._Outbox)
                .filter(self._Outbox.enviado_em.is_(None))
                .order_by(self._Outbox.id)
                .limit(limite)
                .all()
            )
            for linha in pendentes:
                try:
                    publicar_no_stream(self._redis, linha.envelope)
                except Exception:
                    linha.tentativas = (linha.tentativas or 0) + 1
                    _log.warning(
                        "eventos.falha_ao_publicar",
                        evento_id=linha.envelope.get("evento_id"),
                    )
                    break
                linha.enviado_em = datetime.now(UTC)
                publicados += 1
            db.commit()
        return publicados

    def iniciar(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._parar.clear()
        self._thread = threading.Thread(target=self._loop, name="outbox-publicador", daemon=True)
        self._thread.start()

    def parar(self) -> None:
        self._parar.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._parar.is_set():
            try:
                self.varrer()
            except Exception:
                _log.exception("eventos.publicador_erro")
            time.sleep(self._intervalo)
