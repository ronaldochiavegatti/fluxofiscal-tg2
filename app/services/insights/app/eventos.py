"""Consumo de eventos do barramento — Redis Streams com grupo (US-21, ADR-0006).

O contrato do envelope (`validar_envelope`, `ler_envelope`, ...) é **cópia
literal** de `tools/contratos/eventos.py` — mesma disciplina de `observability.py`
e `flags.py`. Mudou lá, muda aqui e no `limits`.

O que é específico do Insights (o consumidor) fica abaixo da linha: o
`Consumidor`, que lê a stream via grupo de consumidores, drena os pendentes ao
subir e entrega cada envelope a uma função de aplicação.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Callable
from typing import Any

import structlog

# `logger` (stdlib, formatação %s) pertence ao contrato copiado de
# tools/contratos/eventos.py. O código do consumidor usa `_log` (structlog),
# como o resto do serviço.
logger = logging.getLogger("insights.eventos")
_log = structlog.get_logger("insights.consumidor")

# ---------------------------------------------------------------------------
#  Contrato do envelope — cópia de tools/contratos/eventos.py
# ---------------------------------------------------------------------------

VERSAO_ATUAL = 1
VERSOES_CONHECIDAS = {1}

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


def ler_envelope(
    envelope: Any,
    *,
    versoes_conhecidas: set[int] = VERSOES_CONHECIDAS,
    registrador: logging.Logger | None = None,
) -> dict[str, Any] | None:
    """Valida e entrega o envelope, ou ``None`` se o consumidor deve pular.

    - envelope malformado -> ``EnvelopeInvalido`` (defeito do produtor);
    - ``versao`` desconhecida -> ``WARNING`` e ``None``, sem quebrar.
    """
    validar_envelope(envelope)
    log = registrador or logger
    versao = envelope["versao"]
    if versao not in versoes_conhecidas:
        log.warning(
            "evento.versao_desconhecida tipo=%s versao=%s evento_id=%s",
            envelope["tipo"],
            versao,
            envelope["evento_id"],
        )
        return None
    return envelope


# ---------------------------------------------------------------------------
#  Consumidor — Redis Streams com grupo
# ---------------------------------------------------------------------------

STREAM = os.getenv("EVENTOS_STREAM", "fluxofiscal:eventos")
GRUPO = os.getenv("EVENTOS_GRUPO", "insights")
CONSUMIDOR = os.getenv("HOSTNAME", "insights-1")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")


def conectar_redis():
    if not REDIS_URL:
        return None
    try:
        import redis

        return redis.Redis.from_url(REDIS_URL, decode_responses=True)
    except Exception:
        _log.warning("eventos.redis_indisponivel")
        return None


class Consumidor:
    """Lê a stream via grupo. `aplicar(envelope)` é chamado uma vez por evento;
    o `XACK` só acontece se `aplicar` não levantar. Ao subir, drena os
    pendentes do próprio consumidor antes de pegar eventos novos — é o que
    fecha o cenário "consumidor fora do ar não perde evento"."""

    def __init__(
        self,
        aplicar: Callable[[dict], None],
        redis_cliente=None,
        intervalo_bloqueio_ms: int = 2000,
    ):
        self._aplicar = aplicar
        self._redis = redis_cliente or conectar_redis()
        self._bloqueio = intervalo_bloqueio_ms
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None

    # -- ciclo de vida --

    def preparar(self) -> bool:
        if self._redis is None:
            self._redis = conectar_redis()
        if self._redis is None:
            return False
        try:
            # `0` = o grupo enxerga a stream inteira desde o começo. Assim,
            # eventos publicados antes do Insights subir pela primeira vez não
            # se perdem.
            self._redis.xgroup_create(STREAM, GRUPO, id="0", mkstream=True)
        except Exception as erro:
            if "BUSYGROUP" not in str(erro):
                _log.warning("eventos.xgroup_create_falhou", erro=str(erro))
                return False
        return True

    def iniciar(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._parar.clear()
        self._thread = threading.Thread(target=self._loop, name="eventos-consumidor", daemon=True)
        self._thread.start()

    def parar(self) -> None:
        self._parar.set()
        if self._thread:
            self._thread.join(timeout=3)

    # -- processamento --

    def _consumir(self, ident: str, campos: dict) -> None:
        try:
            envelope = json.loads(campos["envelope"])
        except (KeyError, json.JSONDecodeError):
            _log.warning("eventos.envelope_ilegivel", ident=ident)
            self._redis.xack(STREAM, GRUPO, ident)
            return
        try:
            reconhecido = ler_envelope(envelope)
        except EnvelopeInvalido:
            _log.warning("eventos.envelope_invalido", ident=ident)
            self._redis.xack(STREAM, GRUPO, ident)
            return
        if reconhecido is None:  # versão desconhecida: deixa pendente
            return
        self._aplicar(reconhecido)
        self._redis.xack(STREAM, GRUPO, ident)

    def drenar_pendentes(self) -> int:
        """Reprocessa o que este consumidor pegou e não confirmou (id `0`)."""
        processados = 0
        while not self._parar.is_set():
            resposta = self._redis.xreadgroup(GRUPO, CONSUMIDOR, {STREAM: "0"}, count=100)
            entradas = resposta[0][1] if resposta else []
            if not entradas:
                break
            for ident, campos in entradas:
                self._consumir(ident, campos)
                processados += 1
        return processados

    def pendentes(self) -> int:
        """Quantos eventos o grupo ainda não confirmou (XPENDING). Evidência
        do cenário de caos."""
        if self._redis is None:
            return 0
        try:
            resumo = self._redis.xpending(STREAM, GRUPO)
        except Exception:
            return 0
        return int(resumo.get("pending", 0)) if isinstance(resumo, dict) else int(resumo[0])

    def processar_lote(self) -> int:
        resposta = self._redis.xreadgroup(
            GRUPO, CONSUMIDOR, {STREAM: ">"}, count=100, block=self._bloqueio
        )
        entradas = resposta[0][1] if resposta else []
        for ident, campos in entradas:
            self._consumir(ident, campos)
        return len(entradas)

    def _loop(self) -> None:
        if not self.preparar():
            _log.warning("eventos.consumidor_sem_redis")
            return
        self.drenar_pendentes()
        while not self._parar.is_set():
            try:
                self.processar_lote()
            except Exception:
                _log.exception("eventos.consumidor_erro")
                time.sleep(1)
