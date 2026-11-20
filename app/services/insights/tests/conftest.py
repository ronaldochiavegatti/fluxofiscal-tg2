"""Infraestrutura comum dos testes do Insights.

Os testes de rota rodam contra SQLite em memória, como no Limits: o `lifespan`
roda como em produção, mas o `create_all` aponta para o motor de teste. O
consumo real do Redis Streams é exercitado com `fakeredis` (US-21) e, ponta a
ponta, no job de integração da CI.
"""

import os

os.environ.pop("UNLEASH_URL", None)

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine, create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import main, projecao  # noqa: E402

EMAIL = "marcia@mei.com.br"


def criar_motor_em_memoria() -> Engine:
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )


def apontar_para(mp: pytest.MonkeyPatch, motor: Engine) -> None:
    mp.setattr(main, "engine", motor)
    mp.setattr(main, "SessionLocal", sessionmaker(autocommit=False, autoflush=False, bind=motor))
    mp.setattr(main, "criar_tabelas", lambda: projecao.Base.metadata.create_all(bind=motor))


@pytest.fixture
def motor(monkeypatch: pytest.MonkeyPatch) -> Engine:
    m = criar_motor_em_memoria()
    apontar_para(monkeypatch, m)
    return m


@pytest.fixture
def cliente(motor: Engine) -> Iterator[TestClient]:
    with TestClient(main.app) as cliente:
        yield cliente


@pytest.fixture
def sessao_factory():
    """Fábrica de sessões sobre um SQLite em memória com o esquema da projeção —
    para os testes de reconstrução e conciliação, que não sobem a app."""
    from sqlalchemy.orm import sessionmaker

    motor = criar_motor_em_memoria()
    projecao.Base.metadata.create_all(bind=motor)
    return sessionmaker(bind=motor, future=True)
