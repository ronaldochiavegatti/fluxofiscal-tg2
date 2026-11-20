"""Enfileiramento de tarefas Celery (US-18).

O `documents` **produz** a tarefa `processar_documento`; quem a executa é o
`worker`. Aqui não se importa nada do worker: `send_task` só precisa do nome da
tarefa e do broker. A tarefa em si vive em `worker/app/tarefas.py`.
"""

from __future__ import annotations

import os

from celery import Celery

BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/1")

# Cliente só-produtor. Sem `backend` — o documents não lê resultado; acompanha o
# documento pelo estado no Mongo.
_fila = Celery("documents-produtor", broker=BROKER_URL)
_fila.conf.update(task_serializer="json", accept_content=["json"], timezone="UTC")

NOME_TAREFA = "processar_documento"
FILA = "ocr"


def enfileirar_processamento(
    documento_id: str,
    *,
    chave_armazenamento: str,
    ext: str,
    user_cnpj: str | None = None,
) -> str:
    """Publica a tarefa e devolve o id dela. Levanta se o broker está fora."""
    resultado = _fila.send_task(
        NOME_TAREFA,
        kwargs={
            "documento_id": documento_id,
            "chave_armazenamento": chave_armazenamento,
            "ext": ext,
            "user_cnpj": user_cnpj,
        },
        queue=FILA,
        # Fast-fail: o `/upload` precisa responder 202 em menos de 500 ms. Se o
        # broker está fora, é melhor um 503 na hora do que retentar bloqueando.
        retry=False,
    )
    return resultado.id
