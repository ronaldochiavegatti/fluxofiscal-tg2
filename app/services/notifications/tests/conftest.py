"""Infraestrutura comum dos testes do Notifications.

Como no Insights: as rotas rodam contra SQLite em memória, o `lifespan` roda
como em produção, mas o `create_all` aponta para o motor de teste.
"""

import os

os.environ.pop("UNLEASH_URL", None)

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine, create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import db, main  # noqa: E402


def criar_motor_em_memoria() -> Engine:
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )


@pytest.fixture
def motor(monkeypatch: pytest.MonkeyPatch) -> Engine:
    m = criar_motor_em_memoria()
    monkeypatch.setattr(db, "engine", m)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=m, future=True))
    monkeypatch.setattr(main, "criar_tabelas", lambda: db.Base.metadata.create_all(bind=m))
    return m


@pytest.fixture
def cliente(motor: Engine) -> Iterator[TestClient]:
    with TestClient(main.app) as cliente:
        yield cliente
