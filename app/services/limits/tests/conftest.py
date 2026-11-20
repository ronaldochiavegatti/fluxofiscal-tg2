"""Infraestrutura comum dos testes do Limits.

Os testes de rota rodam contra SQLite em memória: são rápidos o bastante para
serem executados a cada salvamento e não exigem Docker. O que o SQLite não
prova — como `func.extract` e `Numeric(10, 2)` se comportam de verdade — tem
suíte própria em `test_integracao_postgres.py`, que sobe um PostgreSQL 16.

A escolha aqui é apontar o próprio módulo para o banco de teste, em vez de
sobrescrever a dependência `get_db`. Assim o `lifespan` do serviço roda como
roda em produção, e um erro na criação do esquema aparece no teste em vez de
ficar mascarado.
"""

import os

# Defesa contra um UNLEASH_URL vazado do shell do desenvolvedor (US-15): sem
# isto a suíte tentaria abrir conexão de verdade a cada lifespan.
os.environ.pop("UNLEASH_URL", None)

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine, create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import main  # noqa: E402


def criar_motor_em_memoria() -> Engine:
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        # StaticPool mantém uma única conexão: sem ele, cada sessão abriria um
        # banco em memória novo e vazio, e nada do que um teste grava seria
        # visto pela requisição seguinte.
        poolclass=StaticPool,
        future=True,
    )


def apontar_para(mp: pytest.MonkeyPatch, motor: Engine) -> None:
    """Redireciona o módulo do serviço para o motor de teste."""
    mp.setattr(main, "engine", motor)
    mp.setattr(main, "SessionLocal", sessionmaker(autocommit=False, autoflush=False, bind=motor))
    # A rotina de produção emite `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`,
    # sintaxe que o SQLite não conhece. O esquema criado é o mesmo; o caminho
    # real é exercitado contra PostgreSQL em test_integracao_postgres.py.
    mp.setattr(
        main,
        "create_tables_with_retry",
        lambda: main.Base.metadata.create_all(bind=motor),
    )


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    apontar_para(monkeypatch, criar_motor_em_memoria())

    with TestClient(main.app) as cliente:
        yield cliente


@pytest.fixture
def registrar(cliente: TestClient):
    """Atalho para o caso mais repetido: gravar uma transação e devolvê-la."""

    def _registrar(
        email: str,
        valor: float,
        data: str,
        tipo: str = "venda",
        cnpj_cliente: str | None = None,
    ) -> dict:
        resposta = cliente.post(
            "/transactions",
            json={
                "email": email,
                "amount": valor,
                "tx_date": data,
                "tx_type": tipo,
                "cnpj_cliente": cnpj_cliente,
            },
        )
        assert resposta.status_code == 200, resposta.text
        return resposta.json()

    return _registrar
