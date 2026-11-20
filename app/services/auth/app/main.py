from contextlib import asynccontextmanager

import structlog
from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import models, schemas
from .db import Base, SessionLocal, engine
from .flags import setup_flags, shutdown_flags
from .observability import setup_metrics, setup_observability, setup_tracing
from .security import hash_password, verify_password

setup_observability()
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Prepara o esquema antes de o serviço aceitar tráfego.

    Substitui o `@app.on_event("startup")`, que o FastAPI depreciou. Além de
    silenciar o aviso, o gerenciador de contexto deixa explícito onde termina
    a inicialização — e é o que a suíte de testes exercita ao entrar no
    `TestClient` como contexto.
    """
    Base.metadata.create_all(bind=engine)
    setup_flags(app_name="auth")
    yield
    shutdown_flags()


app = FastAPI(title="Auth Service", lifespan=lifespan)

app.add_middleware(CorrelationIdMiddleware, header_name="X-Correlation-Id")

setup_metrics(app, service_name="auth")
setup_tracing(app, service_name="auth", engine=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "auth"}


@app.post(
    "/users",
    response_model=schemas.UserOut,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"description": "E-mail já cadastrado"}},
)
def create_user(user_in: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == user_in.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = models.User(
        email=user_in.email,
        hashed_password=hash_password(user_in.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("usuario.criado", email=user.email, user_id=user.id)
    return user


@app.get("/users", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.query(models.User).all()


@app.post("/login", responses={401: {"description": "Credenciais inválidas"}})
def login(login_data: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == login_data.email).first()

    if not user:
        logger.warning("login.falhou", motivo="usuario_nao_encontrado", email=login_data.email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not verify_password(login_data.password, user.hashed_password):
        logger.warning("login.falhou", motivo="senha_incorreta", email=login_data.email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    logger.info("login.sucesso", email=user.email, user_id=user.id)
    # Por enquanto, só confirmamos o login.
    # Depois aqui vai entrar geração de JWT.
    return {"message": "login ok", "user_id": user.id}
