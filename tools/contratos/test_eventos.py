"""Testes do contrato do envelope de eventos (US-47).

Cenário da história:
- todo evento publicado carrega ``versao``;
- consumidor que não reconhece a versão registra ``WARNING`` sem quebrar.
"""

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import eventos  # noqa: E402


class TestCriarEnvelope:
    def test_evento_sempre_carrega_versao(self):
        env = eventos.criar_envelope(
            "transacao.criada", {"valor": 10}, produtor="limits", chave_particao="m@x"
        )
        assert env["versao"] == eventos.VERSAO_ATUAL
        assert set(eventos.CAMPOS_OBRIGATORIOS) <= set(env)

    def test_gera_id_e_timestamp(self):
        env = eventos.criar_envelope(
            "transacao.criada", {}, produtor="limits", chave_particao="m@x"
        )
        assert env["evento_id"]
        assert env["ocorrido_em"].endswith("Z")

    def test_trace_id_entra_quando_fornecido(self):
        env = eventos.criar_envelope(
            "transacao.criada", {}, produtor="limits", chave_particao="m@x", trace_id="00-abc-01"
        )
        assert env["trace_id"] == "00-abc-01"

    def test_tipo_sem_ponto_e_recusado(self):
        with pytest.raises(eventos.EnvelopeInvalido):
            eventos.criar_envelope("transacao", {}, produtor="limits", chave_particao="m@x")

    def test_dados_e_copiado_nao_referenciado(self):
        origem = {"valor": 1}
        env = eventos.criar_envelope(
            "transacao.criada", origem, produtor="limits", chave_particao="m@x"
        )
        origem["valor"] = 999
        assert env["dados"]["valor"] == 1


class TestValidarEnvelope:
    def _valido(self):
        return eventos.criar_envelope(
            "transacao.criada", {}, produtor="limits", chave_particao="m@x"
        )

    def test_envelope_sem_versao_e_invalido(self):
        env = self._valido()
        del env["versao"]
        with pytest.raises(eventos.EnvelopeInvalido, match="versao"):
            eventos.validar_envelope(env)

    def test_versao_booleana_e_invalida(self):
        env = self._valido()
        env["versao"] = True
        with pytest.raises(eventos.EnvelopeInvalido):
            eventos.validar_envelope(env)

    def test_nao_dicionario_e_invalido(self):
        with pytest.raises(eventos.EnvelopeInvalido):
            eventos.validar_envelope("[]")


class TestLerEnvelope:
    def _envelope(self, versao):
        env = eventos.criar_envelope(
            "transacao.criada", {"x": 1}, produtor="limits", chave_particao="m@x"
        )
        env["versao"] = versao
        return env

    def test_versao_conhecida_passa_direto(self):
        env = self._envelope(1)
        assert eventos.ler_envelope(env, versoes_conhecidas={1, 2}) is env

    def test_versao_desconhecida_registra_warning_e_devolve_none(self, caplog):
        env = self._envelope(7)
        with caplog.at_level(logging.WARNING, logger="contratos.eventos"):
            resultado = eventos.ler_envelope(env, versoes_conhecidas={1})
        assert resultado is None
        assert "versao_desconhecida" in caplog.text
        assert "versao=7" in caplog.text

    def test_versao_desconhecida_nao_levanta(self):
        # o consumidor desatualizado não pode derrubar o barramento
        assert eventos.ler_envelope(self._envelope(99), versoes_conhecidas={1}) is None

    def test_envelope_malformado_levanta(self):
        with pytest.raises(eventos.EnvelopeInvalido):
            eventos.ler_envelope({"tipo": "x.y"}, versoes_conhecidas={1})

    def test_usa_o_registrador_fornecido(self, caplog):
        log = logging.getLogger("consumidor.insights")
        with caplog.at_level(logging.WARNING, logger="consumidor.insights"):
            eventos.ler_envelope(self._envelope(5), versoes_conhecidas={1}, registrador=log)
        assert "consumidor.insights" in caplog.text
