"""Tarefas Celery do worker (US-18).

`processar_documento` é a única por enquanto. Ela **não** faz OCR nem chama o
Gemini diretamente — delega ao `documents`, que é o dono desse pipeline, por uma
rota interna (`POST /_interno/processar/{id}`). O papel do worker é a
orquestração assíncrona: tirar o trabalho da requisição do usuário, reagendar
falha transitória com recuo exponencial e, esgotadas as tentativas, deixar o
documento em `erro` (a "fila morta" deste desenho).
"""

from __future__ import annotations

import os
import random

import httpx
import structlog

from .celery_app import app

logger = structlog.get_logger()

DOCUMENTS_BASE_URL = os.getenv("DOCUMENTS_BASE_URL", "http://documents:8000")
INTERNO_TOKEN = os.getenv("INTERNO_TOKEN", "")
MAX_TENTATIVAS = 3


def _headers() -> dict:
    return {"X-Interno-Token": INTERNO_TOKEN} if INTERNO_TOKEN else {}


def _recuo(tentativa: int) -> float:
    """Recuo exponencial com jitter: 2, 4, 8 s (+/- aleatório), teto 60 s."""
    base = min(2 ** (tentativa + 1), 60)
    return base + random.uniform(0, base * 0.25)


@app.task(
    bind=True,
    name="processar_documento",
    queue="ocr",
    acks_late=True,
    max_retries=MAX_TENTATIVAS,
)
def processar_documento(
    self,
    *,
    documento_id: str,
    chave_armazenamento: str,
    ext: str,
    user_cnpj: str | None = None,
) -> dict:
    ultima = self.request.retries >= MAX_TENTATIVAS
    url = f"{DOCUMENTS_BASE_URL}/_interno/processar/{documento_id}"

    try:
        resposta = httpx.post(
            url,
            params={"ultima_tentativa": ultima},
            json={"user_cnpj": user_cnpj},
            headers=_headers(),
            timeout=120.0,
        )
    except httpx.RequestError as erro:
        logger.warning("documento.documents_inacessivel", documento_id=documento_id, erro=str(erro))
        raise self.retry(exc=erro, countdown=_recuo(self.request.retries)) from erro

    if resposta.status_code == 503:
        # Falha transitória do Gemini. A rota já não marcou erro (a não ser que
        # esta fosse a última tentativa, e aí ela devolve 200).
        logger.info("documento.retentar", documento_id=documento_id, tentativa=self.request.retries)
        raise self.retry(countdown=_recuo(self.request.retries))

    if resposta.status_code >= 400:
        # Falha permanente: arquivo ausente/corrompido. O documents já marcou
        # `erro`. Não reagenda — repetir não muda o resultado.
        logger.warning(
            "documento.falha_permanente",
            documento_id=documento_id,
            status=resposta.status_code,
        )
        return {"documento_id": documento_id, "estado": "erro", "permanente": True}

    corpo = resposta.json()
    logger.info("documento.concluido", documento_id=documento_id, estado=corpo.get("estado"))
    return corpo
