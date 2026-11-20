import math
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, TypedDict

import structlog
from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import Depends, FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, create_engine, func
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from .flags import setup_flags, shutdown_flags
from .observability import setup_metrics, setup_observability, setup_tracing

setup_observability()
logger = structlog.get_logger()

STARTING_TOKEN_BALANCE = 1000


def tokens_ilimitados() -> bool:
    """Modo demonstração: o saldo nunca bloqueia nem é debitado.

    Lido a cada requisição (não na importação) para a suíte alternar o modo
    com `monkeypatch`. O consumo continua registrado em log, então a
    contabilização por ação segue observável mesmo sem cobrança.
    """
    return os.getenv("BILLING_TOKENS_ILIMITADOS", "").lower() in {"1", "true", "sim"}


# A coluna `id` é `Integer` (int4 no PostgreSQL). Sem esta borda no contrato,
# um inteiro maior chega ao banco e estoura lá, virando 500 onde o correto é
# 422. Encontrado pela suíte de contrato.
ID_MAXIMO = 2_147_483_647

# Custo fixo por ação (em tokens). Usado pelo frontend para estimar o custo
# antes de confirmar a ação, e pelo backend para debitar de fato.
TOKEN_COSTS = {
    "document_confirm": 15,
    "chat_message": 5,
}

DATABASE_URL = "postgresql+psycopg2://billing_user:billing_password@billing_db:5432/billing_db"

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_email = Column(String, index=True, nullable=False)
    plan = Column(String, nullable=False, default="free")
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))


class TokenAccount(Base):
    __tablename__ = "token_accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_email = Column(String, unique=True, index=True, nullable=False)
    balance = Column(Integer, nullable=False, default=STARTING_TOKEN_BALANCE)
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


# --------------------------------------------------------------------
# Registro de consumo medido (ADR-0012, primeira etapa no ADR-0024)
# --------------------------------------------------------------------
#
# Documentos e Orquestrador do Agente informam aqui cada chamada ao Gemini,
# com os tokens que a própria API devolveu. O débito continua sendo o fixo de
# TOKEN_COSTS; os créditos proporcionais são calculados e guardados ao lado,
# para comparar os dois modelos de cobrança antes de trocar um pelo outro.


# Tabela de conversão versionada de tokens do fornecedor para créditos da
# plataforma, nos valores propostos no ADR-0012. Mudar um valor = nova versão:
# cada registro guarda a versão com que foi calculado.
class TaxaPorModelo(TypedDict):
    entrada_por_1k: float
    saida_por_1k: float


class TabelaConversao(TypedDict):
    versao: str
    margem: float
    minimo_por_operacao: int
    modelos: dict[str, TaxaPorModelo]
    padrao: TaxaPorModelo


TABELA_CONVERSAO: TabelaConversao = {
    "versao": "2026-11-v1",
    "margem": 1.5,
    "minimo_por_operacao": 1,
    "modelos": {
        "gemini-3.5-flash-lite": {"entrada_por_1k": 1.0, "saida_por_1k": 3.0},
        "gemini-embedding-001": {"entrada_por_1k": 0.1, "saida_por_1k": 0.0},
    },
    # Modelo fora da tabela é cobrado como o modelo gerador, nunca de graça.
    "padrao": {"entrada_por_1k": 1.0, "saida_por_1k": 3.0},
}

# Preço de referência do fornecedor (USD por 1 milhão de tokens) e cotação
# fixa, os mesmos das métricas do Prometheus. Estimativa, não conferida com a
# fatura do provedor.
PRECO_REFERENCIA_USD_POR_MILHAO: dict[str, dict[str, float]] = {
    "gemini-3.5-flash-lite": {"entrada": 0.075, "saida": 0.30},
    "gemini-embedding-001": {"entrada": 0.15, "saida": 0.0},
}
COTACAO_USD_BRL = 5.50


def creditos_proporcionais(modelo: str, tokens_entrada: int, tokens_saida: int) -> int:
    """Créditos que a operação custaria pela tabela de conversão versionada."""
    taxa = TABELA_CONVERSAO["modelos"].get(modelo, TABELA_CONVERSAO["padrao"])
    bruto = (
        tokens_entrada / 1000 * taxa["entrada_por_1k"] + tokens_saida / 1000 * taxa["saida_por_1k"]
    ) * TABELA_CONVERSAO["margem"]
    return max(TABELA_CONVERSAO["minimo_por_operacao"], math.ceil(bruto))


def custo_estimado_brl(modelo: str, tokens_entrada: int, tokens_saida: int) -> float:
    preco = PRECO_REFERENCIA_USD_POR_MILHAO.get(
        modelo, PRECO_REFERENCIA_USD_POR_MILHAO["gemini-3.5-flash-lite"]
    )
    usd = (tokens_entrada * preco["entrada"] + tokens_saida * preco["saida"]) / 1_000_000
    return round(usd * COTACAO_USD_BRL, 8)


class RegistroConsumo(Base):
    __tablename__ = "registros_consumo"

    id = Column(Integer, primary_key=True, index=True)
    user_email = Column(String, index=True, nullable=False)
    servico = Column(String, nullable=False)
    operacao = Column(String, nullable=False)
    modelo = Column(String, nullable=False)
    tokens_entrada = Column(Integer, nullable=False)
    tokens_saida = Column(Integer, nullable=False)
    creditos_proporcionais = Column(Integer, nullable=False)
    custo_estimado_brl = Column(Float, nullable=False)
    versao_tabela = Column(String, nullable=False)
    criado_em = Column(DateTime, default=lambda: datetime.now(UTC))


def create_tables():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class SubscriptionCreate(BaseModel):
    email: EmailStr
    plan: str | None = "free"


class SubscriptionOut(BaseModel):
    id: int
    user_email: EmailStr
    plan: str
    active: bool
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def _declarar_utc(cls, valor: datetime) -> datetime:
        """Declara o fuso do valor lido do banco.

        A coluna é `timestamp` sem fuso e o serviço sempre grava em UTC, mas o
        contrato promete `format: date-time` — RFC 3339, que exige o
        deslocamento. Sem isto, a resposta violava o próprio esquema publicado.
        """
        return valor if valor.tzinfo is not None else valor.replace(tzinfo=UTC)

    # `orm_mode` era o nome da chave no Pydantic v1. No v2 ela passou a ser
    # ignorada em silêncio, e sem `from_attributes` a validação a partir do
    # objeto do SQLAlchemy falha: as duas rotas de assinatura devolviam 500.
    # Defeito encontrado ao escrever a suíte da US-04.
    model_config = ConfigDict(from_attributes=True)


class TokenBalanceOut(BaseModel):
    email: EmailStr
    balance: int
    costs: dict[str, int]
    ilimitado: bool = False


class TokenConsumeIn(BaseModel):
    email: EmailStr
    reason: str  # chave de TOKEN_COSTS, ex.: "document_confirm" ou "chat_message"


class TokenConsumeOut(BaseModel):
    email: EmailStr
    charged: int
    balance: int
    insufficient: bool
    ilimitado: bool = False


# Identificadores curtos e sem caracteres de controle: servem de rótulo no
# extrato e não podem carregar texto livre (nada de conteúdo de nota ou chat).
Rotulo = Annotated[str, Field(min_length=1, max_length=60, pattern=r"^[a-z0-9_.\-]+$")]
Tokens = Annotated[int, Field(ge=0, le=ID_MAXIMO)]


class ConsumoIn(BaseModel):
    email: EmailStr
    servico: Rotulo
    operacao: Rotulo
    modelo: Rotulo
    tokens_entrada: Tokens
    tokens_saida: Tokens


class ConsumoOut(BaseModel):
    id: int
    servico: str
    operacao: str
    modelo: str
    tokens_entrada: int
    tokens_saida: int
    creditos_proporcionais: int
    custo_estimado_brl: float
    versao_tabela: str
    criado_em: datetime

    @field_validator("criado_em")
    @classmethod
    def _declarar_utc(cls, valor: datetime) -> datetime:
        return valor if valor.tzinfo is not None else valor.replace(tzinfo=UTC)

    model_config = ConfigDict(from_attributes=True)


class TotalPorOperacao(BaseModel):
    servico: str
    operacao: str
    modelo: str
    chamadas: int
    tokens_entrada: int
    tokens_saida: int
    creditos_proporcionais: int
    custo_estimado_brl: float


class ExtratoOut(BaseModel):
    email: EmailStr
    versao_tabela: str
    totais: list[TotalPorOperacao]
    registros: list[ConsumoOut]


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Prepara o esquema antes de o serviço aceitar tráfego.

    Substitui o `@app.on_event("startup")`, que o FastAPI depreciou. Além de
    silenciar o aviso, o gerenciador de contexto deixa explícito onde termina
    a inicialização — e é o que a suíte de testes exercita ao entrar no
    `TestClient` como contexto.
    """
    create_tables()
    setup_flags(app_name="billing")
    yield
    shutdown_flags()


app = FastAPI(title="Billing Service", lifespan=lifespan)

app.add_middleware(CorrelationIdMiddleware, header_name="X-Correlation-Id")

setup_metrics(app, service_name="billing")
setup_tracing(app, service_name="billing", engine=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "billing"}


@app.delete("/reset/{email}")
def reset_user_data(email: EmailStr, db: Session = Depends(get_db)):
    """Zera o saldo de tokens do usuário de volta ao valor inicial da demo,
    usado pelo botão de reset para permitir testes limpos e repetíveis."""
    account = db.query(TokenAccount).filter(TokenAccount.user_email == email).first()
    db.query(RegistroConsumo).filter(RegistroConsumo.user_email == email).delete()
    if account is not None:
        account.balance = STARTING_TOKEN_BALANCE
        db.commit()
    else:
        account = TokenAccount(user_email=email, balance=STARTING_TOKEN_BALANCE)
        db.add(account)
        db.commit()
    return {"email": email, "balance": STARTING_TOKEN_BALANCE}


@app.post("/subscriptions", response_model=SubscriptionOut)
def create_subscription(
    body: SubscriptionCreate,
    db: Session = Depends(get_db),
):
    sub = Subscription(
        user_email=body.email,
        plan=body.plan,
        active=True,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


@app.get(
    "/subscriptions/{sub_id}",
    response_model=SubscriptionOut,
    responses={404: {"description": "Assinatura não encontrada"}},
)
def get_subscription(
    sub_id: Annotated[int, Path(ge=1, le=ID_MAXIMO)],
    db: Session = Depends(get_db),
):
    sub = db.get(Subscription, sub_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return sub


def get_or_create_token_account(db: Session, email: str) -> TokenAccount:
    account = db.query(TokenAccount).filter(TokenAccount.user_email == email).first()
    if account is None:
        account = TokenAccount(user_email=email, balance=STARTING_TOKEN_BALANCE)
        db.add(account)
        db.commit()
        db.refresh(account)
    return account


@app.get("/tokens/{email}", response_model=TokenBalanceOut)
def get_token_balance(email: EmailStr, db: Session = Depends(get_db)):
    account = get_or_create_token_account(db, email)
    return TokenBalanceOut(
        email=email, balance=account.balance, costs=TOKEN_COSTS, ilimitado=tokens_ilimitados()
    )


@app.post(
    "/tokens/consume",
    response_model=TokenConsumeOut,
    responses={400: {"description": "Motivo de consumo fora da tabela de custos"}},
)
def consume_tokens(body: TokenConsumeIn, db: Session = Depends(get_db)):
    cost = TOKEN_COSTS.get(body.reason)
    if cost is None:
        raise HTTPException(
            status_code=400, detail=f"Motivo de consumo desconhecido: {body.reason}"
        )

    account = get_or_create_token_account(db, body.email)
    if tokens_ilimitados():
        logger.info("tokens.consumidos_demo", razao=body.reason, tokens=cost)
        return TokenConsumeOut(
            email=body.email,
            charged=0,
            balance=account.balance,
            insufficient=False,
            ilimitado=True,
        )

    insufficient = account.balance < cost
    if not insufficient:
        account.balance -= cost
        db.commit()
        db.refresh(account)
        logger.info(
            "tokens.consumidos",
            email=body.email,
            razao=body.reason,
            tokens=cost,
            saldo=account.balance,
        )
    else:
        logger.warning(
            "tokens.saldo_insuficiente",
            email=body.email,
            razao=body.reason,
            custo=cost,
            saldo=account.balance,
        )

    return TokenConsumeOut(
        email=body.email,
        charged=0 if insufficient else cost,
        balance=account.balance,
        insufficient=insufficient,
    )


@app.post("/usage", response_model=ConsumoOut, status_code=201)
def registrar_consumo(body: ConsumoIn, db: Session = Depends(get_db)):
    """Registra uma chamada ao modelo com os tokens informados pela API.

    Não debita saldo: o débito continua o fixo de `/tokens/consume`. Os
    créditos proporcionais ficam gravados para comparar os dois modelos.
    """
    registro = RegistroConsumo(
        user_email=body.email,
        servico=body.servico,
        operacao=body.operacao,
        modelo=body.modelo,
        tokens_entrada=body.tokens_entrada,
        tokens_saida=body.tokens_saida,
        creditos_proporcionais=creditos_proporcionais(
            body.modelo, body.tokens_entrada, body.tokens_saida
        ),
        custo_estimado_brl=custo_estimado_brl(body.modelo, body.tokens_entrada, body.tokens_saida),
        versao_tabela=TABELA_CONVERSAO["versao"],
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    logger.info(
        "consumo.registrado",
        servico=body.servico,
        operacao=body.operacao,
        modelo=body.modelo,
        tokens_entrada=body.tokens_entrada,
        tokens_saida=body.tokens_saida,
        creditos=registro.creditos_proporcionais,
    )
    return registro


@app.get("/usage/{email}", response_model=ExtratoOut)
def extrato_de_consumo(
    email: EmailStr,
    limite: Annotated[int, Query(ge=1, le=500)] = 100,
    db: Session = Depends(get_db),
):
    """Extrato de consumo: totais por serviço, operação e modelo, e os
    registros mais recentes."""
    filtro = RegistroConsumo.user_email == email
    totais = (
        db.query(
            RegistroConsumo.servico,
            RegistroConsumo.operacao,
            RegistroConsumo.modelo,
            func.count(RegistroConsumo.id),
            func.sum(RegistroConsumo.tokens_entrada),
            func.sum(RegistroConsumo.tokens_saida),
            func.sum(RegistroConsumo.creditos_proporcionais),
            func.sum(RegistroConsumo.custo_estimado_brl),
        )
        .filter(filtro)
        .group_by(RegistroConsumo.servico, RegistroConsumo.operacao, RegistroConsumo.modelo)
        .order_by(RegistroConsumo.servico, RegistroConsumo.operacao)
        .all()
    )
    registros = (
        db.query(RegistroConsumo)
        .filter(filtro)
        .order_by(RegistroConsumo.id.desc())
        .limit(limite)
        .all()
    )
    return ExtratoOut(
        email=email,
        versao_tabela=TABELA_CONVERSAO["versao"],
        totais=[
            TotalPorOperacao(
                servico=t[0],
                operacao=t[1],
                modelo=t[2],
                chamadas=t[3],
                tokens_entrada=t[4] or 0,
                tokens_saida=t[5] or 0,
                creditos_proporcionais=t[6] or 0,
                custo_estimado_brl=round(t[7] or 0.0, 8),
            )
            for t in totais
        ],
        registros=[ConsumoOut.model_validate(r) for r in registros],
    )
