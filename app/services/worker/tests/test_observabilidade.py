"""Cobre a observabilidade slim do worker (US-09, US-12)."""

import pytest

from app import observability as obs


def test_mascara_email_cnpj_e_ocr():
    evento = obs.mask_sensitive_data(
        None,
        "info",
        {
            "email": "marcia@exemplo.com",
            "cnpj": "12.345.678/0001-99",
            "texto": "contato joao@teste.com CNPJ 98.765.432/0001-11",
            "ocr_text": "conteúdo integral da nota",
        },
    )
    assert evento["email"] == "[MASKED_EMAIL]"
    assert evento["cnpj"] == "[MASKED_CNPJ]"
    assert "joao@teste.com" not in evento["texto"]
    assert "98.765.432/0001-11" not in evento["texto"]
    assert evento["ocr_text"] == "[REMOVED_OCR_TEXT]"


def test_tracing_desligado_por_padrao(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OTEL_TRACES_ENABLED", raising=False)
    assert obs.tracing_enabled() is False
    assert obs.setup_tracing() is None


@pytest.fixture
def _provedor_global_isolado():
    from opentelemetry import trace

    anterior = trace._TRACER_PROVIDER
    once = trace._TRACER_PROVIDER_SET_ONCE
    once._done = False
    yield
    once._done = False
    trace._TRACER_PROVIDER = anterior
    once._done = True


@pytest.mark.usefixtures("_provedor_global_isolado")
def test_tracing_liga_com_a_variavel(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OTEL_TRACES_ENABLED", "true")
    obs.setup_tracing()
    try:
        from opentelemetry.instrumentation.celery import CeleryInstrumentor

        assert CeleryInstrumentor().is_instrumented_by_opentelemetry
    finally:
        from opentelemetry.instrumentation.celery import CeleryInstrumentor

        CeleryInstrumentor().uninstrument()
