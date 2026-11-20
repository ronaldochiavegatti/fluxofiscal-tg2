"""Cobre o rastreamento distribuído e o mascaramento de dados sensíveis
adicionados na Onda 1 (US-09, US-12).

O rastreamento fica inerte por padrão. Estes testes exercitam tanto o caminho
desligado (o que roda na CI e no Compose comum) quanto o caminho ligado, com um
exportador em memória para não depender de coletor nem de rede.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app import observability as obs


def test_tracing_desligado_por_padrao(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OTEL_TRACES_ENABLED", raising=False)
    assert obs.tracing_enabled() is False
    assert obs.setup_tracing(FastAPI(), "svc") is None


@pytest.mark.parametrize("valor", ["true", "1", "yes", "on", "TRUE"])
def test_tracing_liga_com_variavel(monkeypatch: pytest.MonkeyPatch, valor: str):
    monkeypatch.setenv("OTEL_TRACES_ENABLED", valor)
    assert obs.tracing_enabled() is True


@pytest.fixture
def provedor_global_isolado():
    """Permite chamar `setup_tracing` (que fixa o TracerProvider global do
    processo) sem contaminar o resto da suíte."""
    from opentelemetry import trace

    anterior = trace._TRACER_PROVIDER
    once = trace._TRACER_PROVIDER_SET_ONCE
    once._done = False
    yield
    once._done = False
    trace._TRACER_PROVIDER = anterior
    once._done = True


def _desinstrumentar(app) -> None:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.uninstrument_app(app)

    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().uninstrument()
    except ImportError:
        pass

    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().uninstrument()
    except ImportError:
        pass


@pytest.mark.usefixtures("provedor_global_isolado")
def test_setup_tracing_liga_instrumentacao(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OTEL_TRACES_ENABLED", "true")
    try:
        from sqlalchemy import create_engine

        engine = create_engine("sqlite://")
    except ImportError:  # serviço sem SQLAlchemy (documents)
        engine = None

    app = FastAPI()
    provider = obs.setup_tracing(app, "svc-teste", engine=engine)
    try:
        assert provider is not None
        assert provider.resource.attributes["service.name"] == "svc-teste"
        assert getattr(app, "_is_instrumented_by_opentelemetry", False) is True
    finally:
        _desinstrumentar(app)


def test_provider_carrega_nome_do_servico(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
    provider = obs.build_tracer_provider("servico-x")
    assert provider.resource.attributes["service.name"] == "servico-x"


def test_instrumentacao_gera_span_por_requisicao():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    app = FastAPI()

    @app.get("/eco")
    def eco():
        return {"ok": True}

    obs.instrument_app(app, provider, engine=None)
    try:
        with TestClient(app) as cliente:
            assert cliente.get("/eco").status_code == 200
        spans = exporter.get_finished_spans()
        assert spans, "a requisição deveria ter gerado ao menos um span"
        assert any(s.attributes.get("http.route") == "/eco" for s in spans)
    finally:
        _desinstrumentar(app)


def test_log_carrega_trace_id_do_span_ativo():
    provider = TracerProvider()
    tracer = provider.get_tracer("teste")
    with tracer.start_as_current_span("op"):
        evento = obs.add_trace_context(None, "info", {"evento": "x"})
    assert len(evento["trace_id"]) == 32
    assert len(evento["span_id"]) == 16


def test_log_sem_span_usa_correlation_id(monkeypatch: pytest.MonkeyPatch):
    token = obs.correlation_id.set("corr-123")
    try:
        evento = obs.add_trace_context(None, "info", {"evento": "x"})
    finally:
        obs.correlation_id.reset(token)
    assert evento["trace_id"] == "corr-123"
    assert evento["correlation_id"] == "corr-123"
    assert "span_id" not in evento


def test_mascara_email_e_cnpj_no_log():
    evento = obs.mask_sensitive_data(
        None,
        "info",
        {
            "email": "marcia@exemplo.com",
            "cnpj": "12.345.678/0001-99",
            "texto": "contato joao@teste.com CNPJ 12.345.678/0001-99",
            "ocr_text": "conteúdo integral da nota",
        },
    )
    assert evento["email"] == "[MASKED_EMAIL]"
    assert evento["cnpj"] == "[MASKED_CNPJ]"
    assert "joao@teste.com" not in evento["texto"]
    assert "12.345.678/0001-99" not in evento["texto"]
    assert evento["ocr_text"] == "[REMOVED_OCR_TEXT]"
