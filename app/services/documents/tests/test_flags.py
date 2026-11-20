"""Cobre o contrato de segurança das feature flags (US-15, ADR-0008):
sem Unleash configurado, ou com o Unleash fora do ar, toda flag cai no padrão
declarado pelo chamador — nunca levanta, nunca vira ERROR.

`esta_ativa` é testada contra um cliente falso (rápido, determinístico); o
comportamento do SDK real diante de um Unleash inalcançável foi verificado à
parte contra um servidor real e um endpoint inalcançável — ele já resolve
para o `fallback_function` sozinho, sem levantar (o `try/except` do módulo é
redundância defensiva).
"""

import sys
import types

import pytest

from app import flags


@pytest.fixture(autouse=True)
def _limpar_cliente_global():
    """Cada teste começa e termina sem cliente global — evita que um teste
    vaze estado para o próximo."""
    flags._client = None
    yield
    flags._client = None


def test_flags_desligadas_sem_unleash_url(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("UNLEASH_URL", raising=False)
    assert flags.flags_enabled() is False
    assert flags.setup_flags(app_name="documents") is None
    # Sem cliente, cai direto no padrão do chamador — nos dois sentidos.
    assert flags.esta_ativa("dashboard-v2", padrao=False) is False
    assert flags.esta_ativa("dashboard-v2", padrao=True) is True


def test_flags_ligam_com_unleash_url(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("UNLEASH_URL", "http://unleash:4242/api")
    assert flags.flags_enabled() is True


class _ClienteFalso:
    """Duplo de teste do UnleashClient real: sem rede, comportamento
    configurável por teste."""

    def __init__(self, valor: bool | None = None, excecao: Exception | None = None):
        self.valor = valor
        self.excecao = excecao
        self.chamadas: list[tuple[str, dict]] = []
        self.inicializado = False
        self.destruido = False

    def initialize_client(self):
        self.inicializado = True

    def is_enabled(self, nome, context=None, fallback_function=None):
        self.chamadas.append((nome, context or {}))
        if self.excecao is not None:
            raise self.excecao
        if self.valor is not None:
            return self.valor
        return fallback_function(nome, context)

    def destroy(self):
        self.destruido = True


def test_esta_ativa_usa_o_cliente_quando_disponivel():
    flags._client = _ClienteFalso(valor=True)
    assert flags.esta_ativa("dashboard-v2", padrao=False) is True


def test_esta_ativa_cai_no_padrao_quando_avaliacao_falha():
    flags._client = _ClienteFalso(excecao=RuntimeError("unleash fora do ar"))
    assert flags.esta_ativa("dashboard-v2", padrao=False) is False
    assert flags.esta_ativa("ops-desligar-gemini", padrao=True) is True


def test_esta_ativa_propaga_o_contexto_para_o_sdk():
    cliente = _ClienteFalso(valor=None)
    flags._client = cliente
    flags.esta_ativa("dashboard-v2", padrao=False, contexto={"userId": "marcia@mei.com"})
    nome, contexto = cliente.chamadas[0]
    assert nome == "dashboard-v2"
    assert contexto == {"userId": "marcia@mei.com"}


def test_setup_flags_inicializa_o_cliente_real_quando_configurado(monkeypatch: pytest.MonkeyPatch):
    """Substitui o pacote UnleashClient por um duplo antes do import tardio em
    setup_flags(), para provar a fiação sem tocar rede."""
    modulo_falso = types.ModuleType("UnleashClient")
    modulo_falso.UnleashClient = lambda **kwargs: _ClienteFalso(valor=True)
    monkeypatch.setitem(sys.modules, "UnleashClient", modulo_falso)
    monkeypatch.setenv("UNLEASH_URL", "http://unleash:4242/api")
    monkeypatch.setenv("UNLEASH_API_TOKEN", "default:development.teste")

    cliente = flags.setup_flags(app_name="documents")

    assert cliente is not None
    assert cliente.inicializado is True
    assert flags.esta_ativa("ops-desligar-gemini", padrao=False) is True

    flags.shutdown_flags()
    assert cliente.destruido is True
    assert flags._client is None


def test_setup_flags_nao_levanta_se_inicializacao_falhar(monkeypatch: pytest.MonkeyPatch):
    class _ClienteQuebrado(_ClienteFalso):
        def initialize_client(self):
            raise ConnectionError("unleash inalcançável")

    modulo_falso = types.ModuleType("UnleashClient")
    modulo_falso.UnleashClient = lambda **kwargs: _ClienteQuebrado()
    monkeypatch.setitem(sys.modules, "UnleashClient", modulo_falso)
    monkeypatch.setenv("UNLEASH_URL", "http://unleash:4242/api")

    # Não deve levantar mesmo com a inicialização quebrada.
    cliente = flags.setup_flags(app_name="documents")
    assert cliente is not None
