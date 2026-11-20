"""Envia ao serviço de Cobrança o consumo medido de cada chamada ao Gemini.

Primeira etapa do ADR-0012, decidida no ADR-0024. O módulo é copiado, igual,
no serviço de Documentos e no Orquestrador do Agente (não há pacote Python
compartilhado; mudança aqui = aplicar nos dois).

- Desligado por padrão: só envia com a flag `billing-tokens-reais` ligada.
- Melhor esforço e fora do caminho da requisição: o envio roda numa thread
  de um pool pequeno. Se o billing estiver fora, o registro se perde com um
  WARNING, e a extração ou o chat seguem como se nada tivesse acontecido.
- Não envia conteúdo: só e-mail, rótulos da operação e contagens de tokens.
"""

import os
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor

import httpx
import structlog

from .flags import esta_ativa

logger = structlog.get_logger()

BILLING_BASE_URL = os.getenv("BILLING_BASE_URL", "http://billing:8000")
FLAG = "billing-tokens-reais"

_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="consumo")


def ativo() -> bool:
    return esta_ativa(FLAG, padrao=False)


def _enviar(corpo: dict) -> None:
    try:
        httpx.post(f"{BILLING_BASE_URL}/usage", json=corpo, timeout=3.0).raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning(
            "billing.registro_consumo_falhou",
            operacao=corpo["operacao"],
            erro=type(exc).__name__,
        )


def registrar(
    email: str | None,
    servico: str,
    operacao: str,
    modelo: str,
    tokens_entrada: int | None,
    tokens_saida: int | None,
    contar_entrada: Callable[[], int] | None = None,
) -> Future | None:
    """Agenda o envio de um registro de consumo e devolve o `Future` (os
    testes esperam por ele; o código de produção ignora).

    `contar_entrada` serve às chamadas de embedding, cuja resposta não traz
    contagem de tokens: a contagem é feita na thread, pelo endpoint
    `count_tokens` da API, sem atrasar a requisição do usuário.
    """
    if not email or not ativo():
        return None

    def tarefa() -> None:
        entrada = tokens_entrada
        if contar_entrada is not None:
            try:
                entrada = contar_entrada()
            except Exception as exc:  # contagem é acessória: registra e desiste
                logger.warning(
                    "billing.contagem_tokens_falhou", operacao=operacao, erro=type(exc).__name__
                )
                return
        _enviar(
            {
                "email": email,
                "servico": servico,
                "operacao": operacao,
                "modelo": modelo,
                "tokens_entrada": int(entrada or 0),
                "tokens_saida": int(tokens_saida or 0),
            }
        )

    return _pool.submit(tarefa)
