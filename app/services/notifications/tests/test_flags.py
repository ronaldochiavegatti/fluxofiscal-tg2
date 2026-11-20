"""Contrato de segurança das feature flags no Notifications (US-15, ADR-0008):
sem Unleash, ou com o Unleash fora do ar, toda flag cai no padrão do chamador —
nunca levanta, nunca vira ERROR. Cópia do teste do Insights, com o nome do
serviço trocado.
"""

import sys
import types

import pytest

from app import flags


@pytest.fixture(autouse=True)
def _limpar_cliente_global():
    flags._client = None
    yield
    flags._client = None


def test_flags_desligadas_sem_unleash_url(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("UNLEASH_URL", raising=False)
    assert flags.flags_enabled() is False
    assert flags.setup_flags(app_name="notifications") is None
    assert flags.esta_ativa("alertas-ritmo-vendas", padrao=False) is False
    assert flags.esta_ativa("alertas-ritmo-vendas", padrao=True) is True


def test_flags_ligam_com_unleash_url(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("UNLEASH_URL", "http://unleash:4242/api")
    assert flags.flags_enabled() is True


class _ClienteFalso:
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
    assert flags.esta_ativa("alertas-ritmo-vendas", padrao=False) is True


def test_esta_ativa_cai_no_padrao_quando_avaliacao_falha():
    flags._client = _ClienteFalso(excecao=RuntimeError("unleash fora do ar"))
    assert flags.esta_ativa("alertas-ritmo-vendas", padrao=False) is False
    assert flags.esta_ativa("ops-modo-somente-leitura", padrao=True) is True


def test_esta_ativa_propaga_o_contexto_para_o_sdk():
    cliente = _ClienteFalso(valor=None)
    flags._client = cliente
    flags.esta_ativa("alertas-ritmo-vendas", padrao=False, contexto={"userId": "marcia@mei.com"})
    nome, contexto = cliente.chamadas[0]
    assert nome == "alertas-ritmo-vendas"
    assert contexto == {"userId": "marcia@mei.com"}


def test_setup_flags_inicializa_o_cliente_real_quando_configurado(monkeypatch: pytest.MonkeyPatch):
    modulo_falso = types.ModuleType("UnleashClient")
    modulo_falso.UnleashClient = lambda **kwargs: _ClienteFalso(valor=True)
    monkeypatch.setitem(sys.modules, "UnleashClient", modulo_falso)
    monkeypatch.setenv("UNLEASH_URL", "http://unleash:4242/api")
    monkeypatch.setenv("UNLEASH_API_TOKEN", "default:development.teste")

    cliente = flags.setup_flags(app_name="notifications")

    assert cliente is not None
    assert cliente.inicializado is True
    assert flags.esta_ativa("ops-modo-somente-leitura", padrao=False) is True

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

    cliente = flags.setup_flags(app_name="notifications")
    assert cliente is not None
