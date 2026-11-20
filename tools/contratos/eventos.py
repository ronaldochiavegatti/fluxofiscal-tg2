#!/usr/bin/env python3
"""Contrato do envelope de eventos do barramento (US-47, sobre o ADR-0006).

O barramento de eventos (Redis Streams + Outbox) entra na US-21. Este módulo
fixa **o contrato do envelope** antes disso, para que produtor e consumidor
concordem desde o primeiro evento:

- todo evento carrega ``versao`` — versionado desde o dia um;
- um consumidor que recebe uma ``versao`` que não conhece registra ``WARNING``
  e **ignora o evento**, em vez de quebrar. Assim o produtor pode evoluir o
  formato sem derrubar consumidores que ainda não subiram.

Envelope (ADR-0006)::

    {
        "evento_id": "uuid",
        "tipo": "transacao.criada",
        "versao": 1,
        "ocorrido_em": "2026-08-22T13:00:00Z",
        "produtor": "limits",
        "trace_id": "00-...-01",
        "chave_particao": "mei@exemplo.com",
        "dados": {},
    }
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("contratos.eventos")

VERSAO_ATUAL = 1

# Ordem fixada: o envelope é comparado campo a campo em teste de contrato.
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
    """Monta um envelope válido. ``evento_id`` e ``ocorrido_em`` são gerados aqui."""
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
    """Levanta ``EnvelopeInvalido`` se faltar campo obrigatório — ``versao`` inclusive."""
    if not isinstance(envelope, dict):
        raise EnvelopeInvalido(f"envelope deve ser um objeto, recebido: {type(envelope).__name__}")
    faltando = [campo for campo in CAMPOS_OBRIGATORIOS if campo not in envelope]
    if faltando:
        raise EnvelopeInvalido(f"envelope sem campo(s) obrigatório(s): {', '.join(faltando)}")
    if not isinstance(envelope["versao"], int) or isinstance(envelope["versao"], bool):
        raise EnvelopeInvalido("campo 'versao' deve ser inteiro")
    if not isinstance(envelope["dados"], dict):
        raise EnvelopeInvalido("campo 'dados' deve ser um objeto")


def ler_envelope(
    envelope: Any,
    *,
    versoes_conhecidas: set[int],
    registrador: logging.Logger | None = None,
) -> dict[str, Any] | None:
    """Valida e entrega o envelope ao consumidor, ou ``None`` se ele deve pular.

    - envelope malformado -> ``EnvelopeInvalido`` (defeito do produtor, não engole);
    - ``versao`` desconhecida -> ``WARNING`` e ``None`` (consumidor desatualizado,
      não é erro — o evento fica na stream para quando o consumidor subir).
    """
    validar_envelope(envelope)
    log = registrador or logger
    versao = envelope["versao"]
    if versao not in versoes_conhecidas:
        log.warning(
            "evento.versao_desconhecida tipo=%s versao=%s evento_id=%s conhecidas=%s",
            envelope["tipo"],
            versao,
            envelope["evento_id"],
            sorted(versoes_conhecidas),
        )
        return None
    return envelope
