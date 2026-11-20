"""Publicação de eventos via Outbox no Limits (US-21).

Cenário Gherkin: "Publicação é atômica com a escrita" — o evento
`transacao.criada` é gravado na MESMA transação do banco, e o publicador o
envia ao Redis Streams em seguida.
"""

import json

import fakeredis
import pytest

from app import eventos, main

EMAIL = "marcia@mei.com.br"


@pytest.fixture
def com_eventos(monkeypatch):
    """Liga a publicação de eventos (a flag normalmente decide isso)."""
    monkeypatch.setattr(main, "eventos_ligados", lambda: True)


@pytest.fixture
def redis_falso():
    return fakeredis.FakeRedis(decode_responses=True)


def _outbox(cliente):
    with main.SessionLocal() as db:
        return db.query(main.OutboxEvento).order_by(main.OutboxEvento.id).all()


class TestOutboxNaEscrita:
    def test_criar_transacao_grava_o_evento(self, cliente, com_eventos):
        cliente.post(
            "/transactions",
            json={"email": EMAIL, "amount": 1000.0, "tx_date": "2026-03-10", "tx_type": "venda"},
        )
        linhas = _outbox(cliente)
        assert len(linhas) == 1
        assert linhas[0].tipo == "transacao.criada"
        assert linhas[0].enviado_em is None
        env = linhas[0].envelope
        assert env["versao"] == 1
        assert env["produtor"] == "limits"
        assert env["dados"]["valor"] == 1000.0
        assert env["dados"]["email"] == EMAIL

    def test_atualizar_grava_antes_e_depois(self, cliente, com_eventos):
        tx = cliente.post(
            "/transactions",
            json={"email": EMAIL, "amount": 100.0, "tx_date": "2026-03-10", "tx_type": "venda"},
        ).json()
        cliente.patch(f"/transactions/{tx['id']}", json={"amount": 250.0})

        criada, atualizada = _outbox(cliente)
        assert atualizada.tipo == "transacao.atualizada"
        assert atualizada.envelope["dados"]["antes"]["valor"] == 100.0
        assert atualizada.envelope["dados"]["depois"]["valor"] == 250.0

    def test_reset_grava_uma_remocao_por_transacao(self, cliente, com_eventos):
        for _ in range(3):
            cliente.post(
                "/transactions",
                json={"email": EMAIL, "amount": 10.0, "tx_date": "2026-03-10", "tx_type": "venda"},
            )
        cliente.delete(f"/reset/{EMAIL}")

        remocoes = [linha for linha in _outbox(cliente) if linha.tipo == "transacao.removida"]
        assert len(remocoes) == 3

    def test_sem_a_flag_nada_vai_para_a_outbox(self, cliente):
        cliente.post(
            "/transactions",
            json={"email": EMAIL, "amount": 1.0, "tx_date": "2026-03-10", "tx_type": "venda"},
        )
        assert _outbox(cliente) == []


class TestAtomicidade:
    def test_falha_ao_montar_o_evento_desfaz_a_transacao(self, cliente, com_eventos, monkeypatch):
        def _quebra(*a, **k):
            raise eventos.EnvelopeInvalido("boom")

        monkeypatch.setattr(main.eventos, "criar_envelope", _quebra)

        with pytest.raises(eventos.EnvelopeInvalido):
            cliente.post(
                "/transactions",
                json={"email": EMAIL, "amount": 500.0, "tx_date": "2026-03-10", "tx_type": "venda"},
            )

        # o `db.commit()` nunca aconteceu: nem a transação nem o evento ficaram
        assert cliente.get("/transactions", params={"email": EMAIL}).json() == []
        assert _outbox(cliente) == []


class TestPublicador:
    def test_varre_a_outbox_e_publica_no_stream(self, cliente, com_eventos, redis_falso):
        for i in range(2):
            cliente.post(
                "/transactions",
                json={
                    "email": EMAIL,
                    "amount": 100.0 + i,
                    "tx_date": "2026-03-10",
                    "tx_type": "venda",
                },
            )

        publicador = eventos.Publicador(
            session_factory=main.SessionLocal,
            modelo_outbox=main.OutboxEvento,
            redis_cliente=redis_falso,
        )
        assert publicador.varrer() == 2

        mensagens = redis_falso.xrange(eventos.STREAM)
        assert len(mensagens) == 2
        assert json.loads(mensagens[0][1]["envelope"])["tipo"] == "transacao.criada"

        # marcadas como enviadas; segunda varredura é no-op
        assert all(linha.enviado_em is not None for linha in _outbox(cliente))
        assert publicador.varrer() == 0

    def test_redis_fora_do_ar_nao_perde_evento(self, cliente, com_eventos):
        cliente.post(
            "/transactions",
            json={"email": EMAIL, "amount": 42.0, "tx_date": "2026-03-10", "tx_type": "venda"},
        )
        # publicador sem redis: a linha continua na outbox para a próxima varredura
        publicador = eventos.Publicador(
            session_factory=main.SessionLocal, modelo_outbox=main.OutboxEvento, redis_cliente=None
        )
        publicador._redis = None
        assert publicador.varrer() == 0
        assert _outbox(cliente)[0].enviado_em is None


class TestContratoDoEnvelope:
    def test_envelope_tem_todos_os_campos_obrigatorios(self):
        env = eventos.criar_envelope(
            "transacao.criada", {"x": 1}, produtor="limits", chave_particao="m@x"
        )
        assert set(eventos.CAMPOS_OBRIGATORIOS) <= set(env)
        assert env["versao"] == 1

    def test_tipo_sem_ponto_e_recusado(self):
        with pytest.raises(eventos.EnvelopeInvalido):
            eventos.criar_envelope("semponto", {}, produtor="limits", chave_particao="x")

    def test_validar_recusa_envelope_sem_versao(self):
        env = eventos.criar_envelope("a.b", {}, produtor="limits", chave_particao="x")
        del env["versao"]
        with pytest.raises(eventos.EnvelopeInvalido, match="versao"):
            eventos.validar_envelope(env)
