"""Aplicação de eventos na projeção (US-21) — idempotência e matemática.

Cenário Gherkin: "Reentrega não duplica efeito" — o mesmo evento aplicado de
novo não muda a projeção.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import projecao

EMAIL = "marcia@mei.com.br"


@pytest.fixture
def sessao():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
    )
    projecao.Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, future=True)


def _envelope(tipo="transacao.criada", *, evento_id=None, **dados):
    base = {"email": EMAIL, "valor": 1000.0, "tx_type": "venda", "tx_date": "2026-03-10"}
    return {
        "evento_id": evento_id or str(uuid.uuid4()),
        "tipo": tipo,
        "versao": 1,
        "ocorrido_em": datetime.now(UTC).isoformat(),
        "produtor": "limits",
        "chave_particao": EMAIL,
        "dados": {**base, **dados},
    }


def _resumo(sessao, ano=2026):
    with sessao() as db:
        return db.get(projecao.ResumoInsights, (EMAIL, ano))


class TestMatematica:
    def test_venda_soma_em_vendas(self, sessao):
        projecao.aplicar_evento(sessao, _envelope(valor=1500.0))
        linha = _resumo(sessao)
        assert float(linha.total_vendas) == 1500.0
        assert float(linha.total_compras) == 0.0
        assert linha.qtd_transacoes == 1

    def test_compra_soma_em_compras(self, sessao):
        projecao.aplicar_evento(sessao, _envelope(valor=200.0, tx_type="compra"))
        linha = _resumo(sessao)
        assert float(linha.total_compras) == 200.0
        assert linha.qtd_transacoes == 1

    def test_remocao_desfaz(self, sessao):
        projecao.aplicar_evento(sessao, _envelope(valor=1000.0))
        projecao.aplicar_evento(sessao, _envelope("transacao.removida", valor=1000.0))
        linha = _resumo(sessao)
        assert float(linha.total_vendas) == 0.0
        assert linha.qtd_transacoes == 0

    def test_atualizacao_troca_o_valor_sem_mexer_na_contagem(self, sessao):
        projecao.aplicar_evento(sessao, _envelope(valor=1000.0))
        projecao.aplicar_evento(
            sessao,
            _envelope(
                "transacao.atualizada",
                antes={"valor": 1000.0, "tx_type": "venda"},
                depois={"valor": 1250.0, "tx_type": "venda"},
            ),
        )
        linha = _resumo(sessao)
        assert float(linha.total_vendas) == 1250.0
        assert linha.qtd_transacoes == 1

    def test_atualizacao_pode_mudar_venda_para_compra(self, sessao):
        projecao.aplicar_evento(sessao, _envelope(valor=500.0, tx_type="venda"))
        projecao.aplicar_evento(
            sessao,
            _envelope(
                "transacao.atualizada",
                antes={"valor": 500.0, "tx_type": "venda"},
                depois={"valor": 500.0, "tx_type": "compra"},
            ),
        )
        linha = _resumo(sessao)
        assert float(linha.total_vendas) == 0.0
        assert float(linha.total_compras) == 500.0

    def test_ano_vem_da_data_da_transacao(self, sessao):
        projecao.aplicar_evento(sessao, _envelope(valor=100.0, tx_date="2025-11-02"))
        assert _resumo(sessao, ano=2026) is None
        assert float(_resumo(sessao, ano=2025).total_vendas) == 100.0


class TestIdempotencia:
    def test_mesmo_evento_duas_vezes_nao_soma_de_novo(self, sessao):
        env = _envelope(valor=1000.0)
        projecao.aplicar_evento(sessao, env)
        projecao.aplicar_evento(sessao, env)

        linha = _resumo(sessao)
        assert float(linha.total_vendas) == 1000.0
        assert linha.qtd_transacoes == 1
        with sessao() as db:
            assert db.query(projecao.EventoProcessado).count() == 1

    def test_eventos_distintos_ambos_aplicados(self, sessao):
        projecao.aplicar_evento(sessao, _envelope(valor=100.0))
        projecao.aplicar_evento(sessao, _envelope(valor=200.0))
        assert float(_resumo(sessao).total_vendas) == 300.0
        assert _resumo(sessao).qtd_transacoes == 2
