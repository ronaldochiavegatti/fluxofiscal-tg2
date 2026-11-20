"""Consumidor de Redis Streams do Insights (US-21).

Cenário Gherkin: "Consumidor fora do ar não perde evento" — eventos publicados
enquanto o consumidor está parado são processados quando ele volta; um evento
lido e não confirmado é reprocessado no `drenar_pendentes`.
"""

import json
import logging
import uuid

import fakeredis
import pytest

from app import eventos

STREAM = eventos.STREAM
GRUPO = eventos.GRUPO


@pytest.fixture
def redis_falso():
    return fakeredis.FakeRedis(decode_responses=True)


def _envelope(versao=1, evento_id=None):
    return {
        "evento_id": evento_id or str(uuid.uuid4()),
        "tipo": "transacao.criada",
        "versao": versao,
        "ocorrido_em": "2026-03-10T00:00:00Z",
        "produtor": "limits",
        "chave_particao": "m@x.com",
        "dados": {"email": "m@x.com", "valor": 100.0, "tx_type": "venda"},
    }


def _publicar(r, env):
    r.xadd(STREAM, {"envelope": json.dumps(env)})


class TestFluxoNormal:
    def test_processa_evento_novo_e_confirma(self, redis_falso):
        aplicados = []
        c = eventos.Consumidor(aplicar=aplicados.append, redis_cliente=redis_falso)
        c.preparar()
        _publicar(redis_falso, _envelope())

        assert c.processar_lote() == 1
        assert len(aplicados) == 1
        assert c.pendentes() == 0

    def test_falha_em_aplicar_deixa_o_evento_pendente(self, redis_falso):
        def _explode(_):
            raise RuntimeError("projeção fora")

        c = eventos.Consumidor(aplicar=_explode, redis_cliente=redis_falso)
        c.preparar()
        _publicar(redis_falso, _envelope())

        with pytest.raises(RuntimeError):
            c.processar_lote()
        assert c.pendentes() == 1  # não confirmado -> retentável


class TestConsumidorForaDoAr:
    def test_backlog_publicado_antes_de_subir_e_processado(self, redis_falso):
        # 5 eventos publicados; o grupo nem existe ainda
        ids = [f"e{i}" for i in range(5)]
        for i in ids:
            _publicar(redis_falso, _envelope(evento_id=i))

        aplicados = []
        c = eventos.Consumidor(aplicar=aplicados.append, redis_cliente=redis_falso)
        c.preparar()  # cria o grupo em id 0 -> enxerga tudo
        c.drenar_pendentes()
        while c.processar_lote():
            pass

        assert [e["evento_id"] for e in aplicados] == ids
        assert c.pendentes() == 0

    def test_evento_lido_e_nao_confirmado_e_reprocessado(self, redis_falso):
        aplicados = []
        c = eventos.Consumidor(aplicar=aplicados.append, redis_cliente=redis_falso)
        c.preparar()
        _publicar(redis_falso, _envelope(evento_id="x1"))

        # lê direto, sem passar pelo Consumidor -> fica pendente
        redis_falso.xreadgroup(GRUPO, eventos.CONSUMIDOR, {STREAM: ">"}, count=10)
        assert c.pendentes() == 1

        c.drenar_pendentes()
        assert [e["evento_id"] for e in aplicados] == ["x1"]
        assert c.pendentes() == 0


class TestEnvelope:
    def test_versao_desconhecida_nao_aplica_e_fica_pendente(self, redis_falso, caplog):
        aplicados = []
        c = eventos.Consumidor(aplicar=aplicados.append, redis_cliente=redis_falso)
        c.preparar()
        _publicar(redis_falso, _envelope(versao=99))

        with caplog.at_level(logging.WARNING, logger="insights.eventos"):
            c.processar_lote()

        assert aplicados == []
        assert c.pendentes() == 1
        assert "versao_desconhecida" in caplog.text

    def test_envelope_ilegivel_e_descartado_com_ack(self, redis_falso):
        c = eventos.Consumidor(aplicar=lambda _: None, redis_cliente=redis_falso)
        c.preparar()
        redis_falso.xadd(STREAM, {"envelope": "{lixo"})

        c.processar_lote()
        assert c.pendentes() == 0  # não trava a fila com mensagem podre

    def test_envelope_sem_campo_obrigatorio_e_descartado(self, redis_falso):
        c = eventos.Consumidor(aplicar=lambda _: None, redis_cliente=redis_falso)
        c.preparar()
        redis_falso.xadd(STREAM, {"envelope": json.dumps({"tipo": "x.y", "versao": 1})})

        c.processar_lote()
        assert c.pendentes() == 0
