"""Persistência do Notifications Service (preparação da Onda 4).

O feed in-app das US-29/29b/29c precisa sobreviver a reinício: estado de lido,
dispensa lembrada, teto diário, dedup de alerta no mesmo nível. O esqueleto só
fixa a fiação — engine, sessão e `criar_tabelas`. Os modelos (a linha do feed,
o registro de dispensa) entram com a US-29c, sobre esta base, no espírito de
`insights/app/projecao.py`.
"""

from __future__ import annotations

import os
import time

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://notifications_user:notifications_password@notifications_db:5432/notifications_db",
)

engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)

Base = declarative_base()


def criar_tabelas(alvo=None, tentativas: int = 5, espera: int = 2) -> None:
    """Cria o esquema, com retentativa enquanto o Postgres sobe. Sem modelos
    declarados ainda, é um no-op seguro — a US-29c preenche o `Base`."""
    alvo = alvo or engine
    for n in range(1, tentativas + 1):
        try:
            Base.metadata.create_all(bind=alvo)
            return
        except OperationalError:
            if n == tentativas:
                raise
            time.sleep(espera)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
