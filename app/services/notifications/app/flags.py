"""Feature flags via Unleash (US-15, ADR-0008).

Toda flag usada no código tem, no inventário (`docs/feature-flags.yaml`), um
`padrao_seguro` — e ele é SEMPRE o comportamento antigo e conhecido. Esta
regra vale independentemente do Unleash estar de pé:

- Sem `UNLEASH_URL` configurada (suíte de testes, ambiente mínimo), o cliente
  nem chega a ser criado: nenhuma tentativa de rede acontece, e toda chamada
  cai direto no padrão do chamador.
- Com o Unleash indisponível ou inalcançável, o SDK oficial já resolve para o
  `fallback_function` sem levantar (confirmado contra um Unleash real e um
  endpoint inalcançável). O `try/except` aqui é redundância defensiva: nunca
  ERROR, no máximo WARNING, e a aplicação segue servindo.
"""

import contextlib
import os

import structlog

logger = structlog.get_logger()

_client = None


def flags_enabled() -> bool:
    return bool(os.getenv("UNLEASH_URL"))


def setup_flags(app_name: str):
    """Inicializa o cliente Unleash uma vez por processo.

    Chamado no `lifespan` do serviço, não na importação do módulo — assim a
    suíte de testes, que não define `UNLEASH_URL`, nunca tenta abrir conexão.
    """
    global _client
    # Captura numa variável local (em vez de reusar `flags_enabled()`) para o
    # mypy enxergar que `url` não é `None` no construtor abaixo — `os.getenv`
    # duas vezes devolveria `str | None` de novo e o narrowing se perderia.
    url = os.getenv("UNLEASH_URL")
    if not url:
        return None

    from UnleashClient import UnleashClient

    token = os.getenv("UNLEASH_API_TOKEN", "")
    _client = UnleashClient(
        url=url,
        app_name=os.getenv("UNLEASH_APP_NAME", app_name),
        environment=os.getenv("UNLEASH_ENVIRONMENT", "development"),
        custom_headers={"Authorization": token} if token else {},
    )
    try:
        _client.initialize_client()
    except Exception:
        logger.warning("unleash.falha_na_inicializacao")
    return _client


def esta_ativa(nome: str, *, padrao: bool, contexto: dict | None = None) -> bool:
    """Avalia uma feature flag com fallback seguro.

    `contexto` carrega, quando fizer sentido, `userId` (o e-mail do MEI) para
    liberação percentual estável: o mesmo usuário recebe sempre a mesma
    variante, porque o Unleash deriva a decisão de um hash determinístico do
    valor de `userId` (estratégia `flexibleRollout`, ADR-0008).
    """
    if _client is None:
        return padrao
    try:
        return _client.is_enabled(nome, context=contexto or {}, fallback_function=lambda *_: padrao)
    except Exception:
        logger.warning("unleash.avaliacao_falhou", flag=nome)
        return padrao


def shutdown_flags() -> None:
    global _client
    if _client is not None:
        with contextlib.suppress(Exception):
            _client.destroy()
        _client = None
