"""Infraestrutura comum dos testes do Billing.

O serviço é apontado para um SQLite em memória, em vez de a dependência
`get_db` ser sobrescrita. Assim o `lifespan` roda como roda em produção e a
criação do esquema fica dentro do que o teste verifica.
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
        # banco em memória novo e vazio.
        poolclass=StaticPool,
        future=True,
    )


def apontar_para(mp: pytest.MonkeyPatch, motor: Engine) -> None:
    mp.setattr(main, "engine", motor)
    mp.setattr(main, "SessionLocal", sessionmaker(autocommit=False, autoflush=False, bind=motor))


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    apontar_para(monkeypatch, criar_motor_em_memoria())

    with TestClient(main.app) as cliente:
        yield cliente
