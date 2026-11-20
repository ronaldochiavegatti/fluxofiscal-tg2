"""Infraestrutura comum dos testes do Agent Orchestrator.

O serviço é apontado para um SQLite em memória. As colunas `Vector` são
declaradas normalmente e ficam sempre nulas, porque sem `GEMINI_API_KEY` não há
embedding para gravar — que é exatamente o modo de demonstração que a suíte
precisa exercitar.

O que o SQLite não cobre é a busca por similaridade: `cosine_distance` é do
pgvector e não existe fora do PostgreSQL. Nenhum teste daqui a alcança, porque
o serviço só recupera quando há embedding, e não há. A recuperação real entra
na avaliação do RAG da Onda 6, com conjunto de referência próprio.
"""

import os

os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("UNLEASH_URL", None)  # US-15: idem, sem tentativa de rede no lifespan

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine, create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import main  # noqa: E402

EMAIL = "marcia@mei.com.br"
OUTRO = "douglas@mei.com.br"

RESUMO = {
    "email": EMAIL,
    "year": 2026,
    "total_revenue": 47304.00,
    "total_despesas": 12000.00,
    "saldo_liquido": 35304.00,
    "annual_limit": 81000.00,
    "remaining": 33696.00,
    "exceeded": False,
    "percent_used": 58.4,
    "alert_level": "ok",
}


class RespostaFalsa:
    def __init__(self, status_code: int, corpo: dict | None = None, texto: str = ""):
        self.status_code = status_code
        self._corpo = corpo or {}
        self.text = texto

    def json(self) -> dict:
        return self._corpo


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
    # A rotina de produção emite `CREATE EXTENSION IF NOT EXISTS vector`, que só
    # existe no PostgreSQL. As tabelas são as mesmas.
    mp.setattr(
        main,
        "create_tables_with_retry",
        lambda: main.Base.metadata.create_all(bind=motor),
    )


@pytest.fixture
def limits_falso(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Substitui a consulta ao Limits e registra as URLs chamadas."""
    chamadas: list[str] = []

    def _get(url: str, timeout: float = 5.0):
        chamadas.append(url)
        return RespostaFalsa(200, RESUMO)

    monkeypatch.setattr(main.httpx, "get", _get)
    return chamadas


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    apontar_para(monkeypatch, criar_motor_em_memoria())

    with TestClient(main.app) as cliente:
        yield cliente
