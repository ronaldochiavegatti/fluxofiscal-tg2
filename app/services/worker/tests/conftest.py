import os

# Sem UNLEASH_URL nem broker real: a suíte roda o Celery em modo eager
# (tarefa executa no próprio processo, sem Redis).
os.environ.pop("UNLEASH_URL", None)
os.environ.setdefault("CELERY_BROKER_URL", "memory://")
os.environ.setdefault("CELERY_RESULT_BACKEND", "cache+memory://")

import pytest  # noqa: E402

from app import celery_app  # noqa: E402


@pytest.fixture(autouse=True)
def _eager():
    """Executa as tarefas no processo do teste, de forma síncrona."""
    celery_app.app.conf.task_always_eager = True
    celery_app.app.conf.task_eager_propagates = True
    yield
    celery_app.app.conf.task_always_eager = False
