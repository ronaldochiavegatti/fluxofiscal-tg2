"""Infraestrutura comum dos testes do Auth.

O serviço é apontado para um SQLite em memória, em vez de a dependência
`get_db` ser sobrescrita: assim o `lifespan` roda como roda em produção.

O hash é bcrypt de verdade, sem atalho. Trocar o algoritmo por um falso nos
testes tornaria a suíte rápida e inútil — é exatamente o hash que precisa estar
certo. O custo é de alguns décimos de segundo por usuário criado, então os
testes criam poucos.
"""

import os

# Defesa contra um UNLEASH_URL vazado do shell do desenvolvedor: o lifespan do
# serviço chama setup_flags() a cada teste, e sem isto a suíte tentaria abrir
# conexão de verdade em vez de exercitar o caminho sem Unleash (US-15).
os.environ.pop("UNLEASH_URL", None)

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine, create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import main  # noqa: E402

SENHA = "senha-de-teste-123"


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
    mp.setattr(main, "SessionLocal", sessionmaker(autoflush=False, autocommit=False, bind=motor))


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    apontar_para(monkeypatch, criar_motor_em_memoria())

    with TestClient(main.app) as cliente:
        yield cliente
