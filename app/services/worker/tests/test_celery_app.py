"""Teste de fumaça do esqueleto do worker (preparação da Onda 3).

Garante que a aplicação Celery está configurada como o ADR-0003 pede — três
filas por perfil de carga, retentativa com recuo exponencial, sem pickle — e
que a tarefa `ping` do healthcheck funciona.
"""

from app import celery_app
from app.observability import mask_sensitive_data


def test_ping_responde_pong():
    assert celery_app.ping.delay().get() == "pong"


def test_tem_as_tres_filas():
    filas = {q.name for q in celery_app.app.conf.task_queues}
    assert filas == {"ocr", "llm", "manutencao"}


def test_retentativa_configurada():
    conf = celery_app.app.conf
    assert conf.task_max_retries == 3
    assert conf.retry_backoff is True
    assert conf.retry_jitter is True
    assert conf.task_default_retry_delay == 2


def test_nao_usa_pickle():
    conf = celery_app.app.conf
    assert conf.task_serializer == "json"
    assert conf.accept_content == ["json"]


def test_log_mascara_dado_pessoal():
    evento = mask_sensitive_data(
        None,
        "info",
        {"email": "marcia@exemplo.com", "texto": "CNPJ 12.345.678/0001-99"},
    )
    assert evento["email"] == "[MASKED_EMAIL]"
    assert "12.345.678/0001-99" not in evento["texto"]
