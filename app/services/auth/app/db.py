from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Como estamos em Docker, usamos o nome do serviço postgres: "auth_db"
DATABASE_URL = "postgresql+psycopg2://auth_user:auth_password@auth_db:5432/auth_db"


class Base(DeclarativeBase):
    pass


engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
