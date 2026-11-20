"""Observabilidade do worker Celery (esqueleto — preparação da Onda 3).

O worker não é um serviço HTTP, então não usa a instrumentação de FastAPI. O
que ele compartilha com os demais é o log estruturado em JSON com mascaramento
de dado pessoal (US-09) e, quando o overlay de observabilidade está ativo, a
instrumentação de Celery que mantém o rastro contínuo através da fila (US-12,
completado na Onda 3).
"""

import logging
import os
import re

import structlog

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
CNPJ_REGEX = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")


def mask_sensitive_data(logger, method_name, event_dict):
    """Mascara e-mail, CNPJ e texto de OCR antes de o log ser emitido."""
    for key, value in event_dict.items():
        if isinstance(value, str):
            masked = value
            if EMAIL_REGEX.search(masked):
                masked = EMAIL_REGEX.sub("[EMAIL]", masked)
            if CNPJ_REGEX.search(masked):
                masked = CNPJ_REGEX.sub("[CNPJ]", masked)
            if masked != value:
                event_dict[key] = masked

        if key in ("email", "user_email"):
            event_dict[key] = "[MASKED_EMAIL]"
        if key in ("cnpj", "documento_cnpj"):
            event_dict[key] = "[MASKED_CNPJ]"
        if key in ("ocr_text", "content", "document_content", "texto_integral"):
            event_dict[key] = "[REMOVED_OCR_TEXT]"

    return event_dict


def setup_observability():
    """Configura o structlog para saída em JSON."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            mask_sensitive_data,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(format="%(message)s", level=logging.INFO)


def tracing_enabled() -> bool:
    return os.getenv("OTEL_TRACES_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")


def setup_tracing() -> None:
    """Liga a instrumentação de Celery quando o overlay de observabilidade
    está ativo. Inerte por padrão (sem coletor OTLP, instrumentar é só custo)."""
    if not tracing_enabled():
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.celery import CeleryInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({"service.name": os.getenv("OTEL_SERVICE_NAME") or "worker"})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    CeleryInstrumentor().instrument(tracer_provider=provider)
