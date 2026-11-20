import logging
import os
import re

import structlog
from asgi_correlation_id import correlation_id
from prometheus_fastapi_instrumentator import Instrumentator

# Expressões regulares para encontrar padrões sensíveis em strings
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
CNPJ_REGEX = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")


def mask_sensitive_data(logger, method_name, event_dict):
    """
    Processador customizado do structlog para mascarar dados sensíveis
    antes que o log seja emitido. (US-09 e regras gerais de LGPD)
    """
    for key, value in event_dict.items():
        if isinstance(value, str):
            # As duas substituições são encadeadas na mesma string. Antes, cada
            # uma partia do valor original: uma linha com e-mail *e* CNPJ tinha
            # o mascaramento do e-mail descartado pelo do CNPJ, e o e-mail
            # vazava em texto puro (US-09, US-51).
            masked = value
            if EMAIL_REGEX.search(masked):
                masked = EMAIL_REGEX.sub("[EMAIL]", masked)
            if CNPJ_REGEX.search(masked):
                masked = CNPJ_REGEX.sub("[CNPJ]", masked)
            if masked != value:
                event_dict[key] = masked

        # Filtros de chaves explícitas
        if key in ("email", "user_email"):
            # Para chaves de e-mail conhecidas, deixamos apenas a máscara
            event_dict[key] = "[MASKED_EMAIL]"

        if key in ("cnpj", "documento_cnpj"):
            event_dict[key] = "[MASKED_CNPJ]"

        if key in ("ocr_text", "content", "document_content", "texto_integral"):
            event_dict[key] = "[REMOVED_OCR_TEXT]"

    return event_dict


def add_trace_context(logger, method_name, event_dict):
    """Anexa a cada log o identificador de correlação e, quando o rastreamento
    distribuído está ativo (US-12), o `trace_id` e o `span_id` do span atual.

    O `trace_id` em hexadecimal de 32 dígitos é o que liga o log ao rastro no
    Tempo: é ele que o Grafana usa para saltar do painel para o rastro e do
    rastro para as linhas de log daquela requisição. Sem OpenTelemetry ativo,
    o `trace_id` cai para o identificador de correlação gerado no gateway, que
    já basta para seguir uma requisição por `docker compose logs`.
    """
    req_id = correlation_id.get()
    if req_id:
        event_dict.setdefault("correlation_id", req_id)

    trace_id = req_id
    try:
        from opentelemetry import trace

        span_context = trace.get_current_span().get_span_context()
        if span_context.is_valid:
            trace_id = format(span_context.trace_id, "032x")
            event_dict["span_id"] = format(span_context.span_id, "016x")
    except Exception:  # pragma: no cover - OpenTelemetry ausente ou não iniciado
        pass

    if trace_id:
        event_dict["trace_id"] = trace_id
    return event_dict


def setup_observability():
    """Configura o structlog para saída em JSON."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            add_trace_context,
            mask_sensitive_data,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            # No modo produção, queremos JSON:
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Intercepta os logs nativos do Uvicorn/FastAPI e roteia para o structlog
    logging.basicConfig(format="%(message)s", level=logging.INFO)


def setup_metrics(app, service_name: str = "unknown"):
    """Instrumenta o FastAPI com métricas RED para Prometheus (US-10).

    Expõe automaticamente o endpoint GET /metrics com:
    - http_requests_total (contador por método, rota, status)
    - http_request_duration_seconds (histograma por método e rota)
    - http_requests_in_progress (medidor de requisições ativas)

    O rótulo `handler` usa o padrão da rota (ex.: /summary/{email}),
    nunca o caminho concreto, evitando explosão de cardinalidade e
    vazamento de dados pessoais nos rótulos.
    """
    instrumentator = Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        should_respect_env_var=False,
        excluded_handlers=["/health", "/metrics"],
        inprogress_name="http_requests_in_progress",
        inprogress_labels=True,
    )
    instrumentator.instrument(app)
    instrumentator.expose(app, include_in_schema=False, should_gzip=True)


# ---------------------------------------------------------------------------
# Rastreamento distribuído — US-12
# ---------------------------------------------------------------------------
#
# O rastreamento fica INERTE por padrão. Ele só liga quando
# OTEL_TRACES_ENABLED=true, o que acontece apenas com o overlay
# docker-compose.observability.yml (ADR-0007). No Compose comum e na CI não há
# coletor OTLP, então instrumentar seria só custo sem destino.
#
# A propagação do contexto de rastro ATRAVÉS DA FILA (Celery, envelope de
# evento) entra na Onda 3, junto com o próprio processamento assíncrono — antes
# de a fila existir não há o que propagar. Ver docs/observabilidade/README.md §3.


def tracing_enabled() -> bool:
    return os.getenv("OTEL_TRACES_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")


def build_tracer_provider(service_name: str):
    """Monta o TracerProvider com o exportador OTLP/HTTP para o Collector.

    Isolado de `setup_tracing` para poder ser exercitado em teste sem tocar o
    provedor global do processo.
    """
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({"service.name": os.getenv("OTEL_SERVICE_NAME") or service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    return provider


def instrument_app(app, provider, engine=None) -> None:
    """Liga a instrumentação automática de FastAPI, httpx e SQLAlchemy.

    - FastAPI: um span por requisição, com o padrão da rota como nome.
    - httpx: injeta `traceparent` (W3C Trace Context) nas chamadas de saída,
      então o rastro atravessa gateway -> documents -> limits sem código nosso.
    - SQLAlchemy: um span por consulta, para localizar a query lenta.
    """
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(
        app, tracer_provider=provider, excluded_urls="health,metrics"
    )

    # httpx e SQLAlchemy só são instrumentados nos serviços que os usam. O
    # try/except mantém um serviço sem esses pacotes (ex.: auth não fala HTTP
    # com ninguém) livre de dependência que não precisa.
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument(tracer_provider=provider)
    except ImportError:  # pragma: no cover - serviço sem httpx
        pass

    if engine is not None:
        try:
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

            SQLAlchemyInstrumentor().instrument(engine=engine, tracer_provider=provider)
        except ImportError:  # pragma: no cover - serviço sem SQLAlchemy
            pass


def setup_tracing(app, service_name: str = "unknown", engine=None):
    """Configura o rastreamento distribuído do serviço (US-12).

    Devolve o TracerProvider quando liga, ou `None` quando o rastreamento está
    desativado — que é o padrão fora do overlay de observabilidade.
    """
    if not tracing_enabled():
        return None

    from opentelemetry import trace

    provider = build_tracer_provider(service_name)
    trace.set_tracer_provider(provider)
    instrument_app(app, provider, engine=engine)
    return provider
