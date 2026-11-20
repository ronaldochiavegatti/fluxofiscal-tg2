"""Worker Celery — executor de tarefas em segundo plano (ADR-0003).

**Esqueleto** (preparação da Onda 3). Define a aplicação Celery, as três filas
por perfil de carga e a política de retentativa. A única tarefa aqui é `ping`,
usada pelo healthcheck. As tarefas de verdade — `processar_documento`,
`gerar_embeddings`, `reindexar_base_conhecimento`, `recalcular_insights`,
`expurgar_documentos` — entram nas US-18 a US-23.
"""

import os

from celery import Celery
from kombu import Queue

from .flags import setup_flags
from .observability import setup_observability, setup_tracing

setup_observability()
setup_tracing()
setup_flags(app_name="worker")

BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/1")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/2")

app = Celery(
    "fluxofiscal",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    # US-18: onde as tarefas de verdade moram. `include` é resolvido depois da
    # criação do app, então não há import circular com `tarefas.py`.
    include=["app.tarefas"],
)

app.conf.update(
    # Filas separadas por perfil de carga (ADR-0003): `ocr` usa CPU,
    # `llm` espera E/S, `manutencao` é para tarefas periódicas.
    task_default_queue="manutencao",
    task_queues=(
        Queue("ocr", routing_key="ocr"),
        Queue("llm", routing_key="llm"),
        Queue("manutencao", routing_key="manutencao"),
    ),
    # Retentativa só para falha transitória; recuo exponencial começando em 2 s.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_default_retry_delay=2,
    task_max_retries=3,
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    # Serialização explícita, sem pickle.
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)


@app.task(name="ping", queue="manutencao")
def ping() -> str:
    """Tarefa trivial exercitada pelo healthcheck e pela suíte de testes."""
    return "pong"
