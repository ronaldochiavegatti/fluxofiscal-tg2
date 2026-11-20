"""Fiação do banco do esqueleto (preparação da Onda 4).

Sem modelos declarados, `criar_tabelas` é um no-op seguro e retentável — é só
isso que o esqueleto promete. A US-29c preenche o `Base` e testa o feed.
"""

from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

from app import db


def test_criar_tabelas_sem_modelos_nao_cria_nada():
    motor = create_engine("sqlite://", poolclass=StaticPool, future=True)
    db.criar_tabelas(alvo=motor)
    assert inspect(motor).get_table_names() == []


def test_get_db_entrega_e_fecha_a_sessao():
    gerador = db.get_db()
    sessao = next(gerador)
    assert sessao is not None
    gerador.close()
