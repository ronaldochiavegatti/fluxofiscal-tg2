import io
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated

import structlog
from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import Depends, FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    create_engine,
    func,
    text,
)
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from . import eventos
from .dominio import (
    LIMITE_ANUAL_MEI,
    PARAMETROS_PADRAO,
    ParametrosFiscais,
    TipoTransacao,
    calcular_concentracao_clientes,
    calcular_limite_aplicavel,
    calcular_projecao,
    calcular_resumo,
    calcular_serie_mensal,
)
from .flags import esta_ativa, setup_flags, shutdown_flags
from .observability import setup_metrics, setup_observability, setup_tracing

setup_observability()
logger = structlog.get_logger()

# Mantidos como float para o contrato HTTP, mas derivados do domínio: existe
# uma única definição do teto, e ela vive em app/dominio/limites.py.
MEI_ANNUAL_LIMIT = float(LIMITE_ANUAL_MEI)

# Apenas transações do tipo "venda" (o usuário como emitente/prestador) contam
# como faturamento para o limite anual do MEI. Transações do tipo "compra" (o
# usuário como destinatário/comprador) são despesas e não entram nesse cálculo,
# mas seguem registradas para compor o balancete.
TX_TYPES = tuple(t.value for t in TipoTransacao)
DEFAULT_TX_TYPE = TipoTransacao.VENDA.value

DATABASE_URL = "postgresql+psycopg2://limits_user:limits_password@limits_db:5432/limits_db"

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Estilo declarativo do SQLAlchemy 2.0 (`Mapped`/`mapped_column`), em vez
    do `declarative_base()` legado: o legado devolve uma classe dinâmica que o
    mypy não reconhece como tipo válido, e cada atributo chegava ao código
    como `Column[T]` em vez de `T` — o construtor de `TransactionOut`, por
    exemplo, via incompatibilidade em todo campo. `Mapped[T]` resolve isso
    nativamente, sem plugin nem `# type: ignore`."""


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_email: Mapped[str] = mapped_column(String, index=True, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    tx_date: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    tx_type: Mapped[str] = mapped_column(String, nullable=False, server_default=DEFAULT_TX_TYPE)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    cnpj_cliente: Mapped[str | None] = mapped_column(String, nullable=True)
    """CNPJ do cliente numa venda (US-27). Só preenchido quando o documento
    identificou o destinatário; nunca preenchido para `tx_type == "compra"`
    (ali o CNPJ relevante seria o do fornecedor, fora do escopo desta
    história — "de quais clientes vem meu faturamento" é só sobre venda).
    Cruza a fronteira documents -> limits pela ACL de `traducao.py`
    (ADR-0015, estendida pela ADR-0021)."""


class ConfiguracaoFiscal(Base):
    """Configuração das regras e metas de um usuário (#91).

    Guarda só o que o usuário mudou (`ajustes`), não a cópia de todos os
    parâmetros: assim um parâmetro novo no domínio chega a quem já configurou
    algo com o próprio valor padrão, sem migração. Os decimais vão como texto
    no JSON para não perder precisão."""

    __tablename__ = "configuracao_fiscal"

    user_email: Mapped[str] = mapped_column(String, primary_key=True)
    ajustes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    data_abertura: Mapped[date | None] = mapped_column(Date, nullable=True)
    """Abertura do MEI — define o teto proporcional no ano de abertura."""
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class OutboxEvento(Base):
    """Padrão Outbox (ADR-0006): o evento é gravado na MESMA transação que
    altera a transação de negócio. Um publicador varre `enviado_em IS NULL` e
    manda ao Redis. Ou os dois acontecem, ou nenhum."""

    __tablename__ = "outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tipo: Mapped[str] = mapped_column(String, nullable=False)
    versao: Mapped[int] = mapped_column(Integer, nullable=False, default=eventos.VERSAO_ATUAL)
    envelope: Mapped[dict] = mapped_column(JSON, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    enviado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tentativas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


def ano_corrente() -> int:
    """Ano de referência padrão das consultas anuais.

    Precisa ser função, e não valor padrão do `Query`. Um `Query(default=...)`
    é avaliado uma única vez, na importação do módulo: um serviço que subiu em
    dezembro continuaria respondendo sobre o ano anterior depois da virada,
    até ser reiniciado.
    """
    return datetime.now(UTC).year


def create_tables_with_retry(max_retries: int = 5, delay_seconds: int = 2):
    for attempt in range(1, max_retries + 1):
        try:
            Base.metadata.create_all(bind=engine)
            # Base.metadata.create_all só cria tabelas novas; para bancos já
            # existentes (de antes da coluna tx_type existir), garantimos a
            # coluna via ALTER TABLE idempotente.
            with engine.connect() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE transactions "
                        "ADD COLUMN IF NOT EXISTS tx_type VARCHAR NOT NULL "
                        f"DEFAULT '{DEFAULT_TX_TYPE}'"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE transactions "
                        "ADD COLUMN IF NOT EXISTS cnpj_cliente VARCHAR NULL"
                    )
                )
                conn.commit()
            return
        except OperationalError:
            if attempt == max_retries:
                raise
            time.sleep(delay_seconds)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# US-21: publicação de eventos de domínio via Outbox. Atrás da flag
# `eventos-outbox` (tudo-ou-nada). `FORCAR_EVENTOS_OUTBOX=true` liga sem Unleash
# — é o que a CI usa, no mesmo espírito de `OTEL_TRACES_ENABLED`.
def eventos_ligados() -> bool:
    if os.getenv("FORCAR_EVENTOS_OUTBOX", "").lower() == "true":
        return True
    return esta_ativa("eventos-outbox", padrao=False)


# #91: configuração das regras e metas por usuário. Atrás da flag
# `metricas-configuraveis` (padrão seguro: desligada). Desligada, toda rota usa
# os parâmetros padrão do domínio e ignora a configuração gravada — o
# comportamento de antes, sem nenhuma diferença.
def metricas_configuraveis_ligadas() -> bool:
    return esta_ativa("metricas-configuraveis", padrao=False)


#: Campos de `ParametrosFiscais` que são `Decimal` (o resto é `int` ou `bool`).
CAMPOS_DECIMAIS = frozenset(
    {
        "limite_anual",
        "margem_desenquadramento",
        "limiar_alerta",
        "meta_mensal",
        "limiar_concentracao_cliente",
        "limiar_lancamento_atipico",
        "limiar_atencao_ritmo_realizado",
    }
)


def _ajustes_para_dominio(ajustes: dict) -> dict:
    """JSON gravado (decimais como texto) -> tipos do domínio."""
    return {
        nome: (Decimal(str(valor)) if nome in CAMPOS_DECIMAIS and valor is not None else valor)
        for nome, valor in ajustes.items()
    }


def _ajustes_para_json(ajustes: dict) -> dict:
    return {
        nome: (str(valor) if isinstance(valor, Decimal) else valor)
        for nome, valor in ajustes.items()
    }


def carregar_configuracao(db: Session, email: str) -> ConfiguracaoFiscal | None:
    return db.get(ConfiguracaoFiscal, email)


def parametros_do_usuario(db: Session, email: str) -> ParametrosFiscais:
    """Parâmetros que as regras devem usar para este usuário. Com a flag
    desligada, sem configuração gravada, ou se a gravada ficou inválida (um
    campo removido do domínio, por exemplo), cai no padrão — nunca em 500."""
    if not metricas_configuraveis_ligadas():
        return PARAMETROS_PADRAO
    config = carregar_configuracao(db, email)
    if config is None or not config.ajustes:
        return PARAMETROS_PADRAO
    try:
        return ParametrosFiscais.com_ajustes(_ajustes_para_dominio(config.ajustes))
    except (ValueError, TypeError):
        logger.warning("configuracao.invalida_usando_padrao", email=email)
        return PARAMETROS_PADRAO


def data_abertura_do_usuario(db: Session, email: str, informada: date | None) -> date | None:
    """A data passada na rota vence; sem ela, a configurada (com a flag)."""
    if informada is not None or not metricas_configuraveis_ligadas():
        return informada
    config = carregar_configuracao(db, email)
    return config.data_abertura if config else None


_publicador = eventos.Publicador(session_factory=SessionLocal, modelo_outbox=OutboxEvento)


def emitir_evento(db: Session, tipo: str, dados: dict, *, chave_particao: str) -> None:
    """Grava o envelope na Outbox usando a MESMA sessão da escrita de negócio.
    O `db.commit()` do handler fecha a transação atômica. No-op sem a flag."""
    if not eventos_ligados():
        return
    envelope = eventos.criar_envelope(tipo, dados, produtor="limits", chave_particao=chave_particao)
    db.add(OutboxEvento(tipo=tipo, versao=envelope["versao"], envelope=envelope))


# `Numeric(10, 2)` comporta no máximo 99.999.999,99. Sem esta borda no
# contrato, um valor maior atravessa a validação e estoura no banco: o serviço
# devolve 500 onde deveria devolver 422. Encontrado pela suíte de contrato.
VALOR_MAXIMO = 99_999_999.99

# A coluna `id` é `Integer` (int4 no PostgreSQL) e o ano é filtrado com
# `func.extract`. Inteiro sem borda no contrato chega ao banco e estoura lá,
# virando 500. Com as bordas declaradas, vira 422 — que é a resposta correta
# para entrada fora de faixa. Encontrado pela suíte de contrato.
ID_MAXIMO = 2_147_483_647
ANO_MINIMO = 2000
ANO_MAXIMO = 2100


class TransactionCreate(BaseModel):
    email: EmailStr
    amount: float = Field(gt=0, le=VALOR_MAXIMO)
    tx_date: date
    source: str | None = None
    tx_type: str = DEFAULT_TX_TYPE  # "venda" | "compra"
    cnpj_cliente: str | None = None  # US-27: só relevante para "venda"


class TransactionUpdate(BaseModel):
    amount: float | None = Field(default=None, gt=0, le=VALOR_MAXIMO)
    tx_date: date | None = None
    source: str | None = None
    tx_type: str | None = None
    cnpj_cliente: str | None = None


class TransactionOut(BaseModel):
    id: int
    email: EmailStr
    amount: float
    tx_date: date
    source: str | None
    tx_type: str
    cnpj_cliente: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ParametrosConfig(BaseModel):
    """Os parâmetros das regras como o cliente HTTP os vê. Frações (alerta,
    concentração, atípico, ritmo) vão de 0 a 1; a margem de desenquadramento
    é o fator sobre o teto (1,2 = 20% acima)."""

    limite_anual: float
    limite_proporcional: bool
    margem_desenquadramento: float
    limiar_alerta: float
    meta_mensal: float | None
    limiar_concentracao_cliente: float
    dias_minimos_para_projetar: int
    transacoes_minimas_para_projetar: int
    dias_abertura_recente: int
    limiar_lancamento_atipico: float
    limiar_atencao_ritmo_realizado: float


class ConfiguracaoOut(BaseModel):
    email: EmailStr
    data_abertura: date | None
    parametros: ParametrosConfig
    """Valores em uso: o padrão com os ajustes do usuário por cima."""
    padrao: ParametrosConfig
    """Valores de partida, para a tela mostrar ao lado e permitir voltar."""
    personalizados: list[str]
    """Nomes dos campos que o usuário mudou."""
    ativa: bool
    """`False` com a flag `metricas-configuraveis` desligada: a configuração
    é gravada, mas as regras ainda usam o padrão."""


class ConfiguracaoIn(BaseModel):
    """Atualização parcial: só os campos enviados mudam. `null` num parâmetro
    devolve aquele campo ao padrão; `data_abertura: null` apaga a data."""

    data_abertura: date | None = None
    parametros: dict[str, float | int | bool | None] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class SummaryOut(BaseModel):
    email: EmailStr
    year: int
    total_revenue: float  # soma apenas das transações do tipo "venda"
    total_despesas: float  # soma apenas das transações do tipo "compra"
    saldo_liquido: float  # total_revenue - total_despesas
    annual_limit: float
    remaining: float
    exceeded: bool
    percent_used: float
    alert_level: str  # "ok" | "warning" | "exceeded"
    alert_threshold_percent: float = 80.0
    """A partir de quantos % do teto o `alert_level` vira "warning" (#91)."""


class RitmoOut(BaseModel):
    """US-25/US-28: retrato de ritmo do ano, para o gauge e o painel de ritmo
    do dashboard. `nivel` aqui é o de 6 estados (`dominio.ritmo.NivelRitmo`) —
    combina realizado e projetado, e é diferente do `alert_level` de
    `SummaryOut` (3 estados, só realizado)."""

    email: EmailStr
    year: int
    limite_aplicavel: float
    meses_de_atividade: int | None
    proporcional: bool
    total_vendas: float
    restante: float
    percent_used: float
    nivel: str  # ok | atencao_ritmo | atencao | risco | estourado | desenquadramento
    dias_decorridos: int
    total_dias_ano: int
    taxa_diaria: float
    taxa_diaria_referencia: float
    taxa_diaria_recente: float
    taxa_diaria_90d: float
    indice_ritmo: float | None
    aceleracao: float | None
    tendencia: str  # acelerando | estavel | desacelerando
    projecao_disponivel: bool
    motivo_indisponivel: str | None
    projecao_anual: float | None
    dias_ate_estouro: int | None
    data_prevista_estouro: date | None
    faturamento_seguro_mes: float
    influenciada_por_lancamento_atipico: bool


class PontoSerieAcumulada(BaseModel):
    data: date
    acumulado: float


class MesResumoOut(BaseModel):
    """US-27: um ponto do gráfico "mês a mês"."""

    mes: int
    vendas: float
    despesas: float
    meta: float
    acima_da_meta: bool


class ConcentracaoClienteOut(BaseModel):
    """US-27: um item da lista "origem do faturamento".

    `nome` (razão social) sempre `None` por ora — nenhum serviço extrai ou
    guarda esse dado hoje; a interface usa o `cnpj` formatado como rótulo
    até existir uma fonte confiável de nome (fora do escopo desta história,
    ver ADR-0021)."""

    cnpj: str
    nome: str | None = None
    valor: float
    percentual: float
    alerta: bool


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Prepara o esquema antes de o serviço aceitar tráfego.

    Substitui o `@app.on_event("startup")`, que o FastAPI depreciou. Além de
    silenciar o aviso, o gerenciador de contexto deixa explícito onde termina
    a inicialização — e é o que a suíte de testes exercita ao entrar no
    `TestClient` como contexto.
    """
    create_tables_with_retry()
    setup_flags(app_name="limits")
    if eventos_ligados():
        _publicador.iniciar()
    yield
    _publicador.parar()
    shutdown_flags()


app = FastAPI(title="Limits Service", lifespan=lifespan)

app.add_middleware(CorrelationIdMiddleware, header_name="X-Correlation-Id")

setup_metrics(app, service_name="limits")
setup_tracing(app, service_name="limits", engine=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "limits"}


@app.delete("/reset/{email}")
def reset_user_data(email: EmailStr, db: Session = Depends(get_db)):
    """Apaga TODAS as transações (vendas e compras) do usuário, usado pelo
    botão de reset da demo para permitir testes limpos e repetíveis."""
    if eventos_ligados():
        for tx in db.query(Transaction).filter(Transaction.user_email == email).all():
            emitir_evento(
                db,
                "transacao.removida",
                {
                    "transacao_id": tx.id,
                    "email": tx.user_email,
                    "tx_date": tx.tx_date.isoformat(),
                    "valor": float(tx.amount),
                    "tx_type": tx.tx_type,
                },
                chave_particao=email,
            )
    deleted = db.query(Transaction).filter(Transaction.user_email == email).delete()
    db.commit()
    return {"email": email, "transactions_deleted": deleted}


def _validate_tx_type(tx_type: str):
    if tx_type not in TX_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"tx_type inválido: {tx_type!r}. Use um de {TX_TYPES}.",
        )


@app.post(
    "/transactions",
    response_model=TransactionOut,
    responses={400: {"description": "tx_type fora de 'venda' | 'compra'"}},
)
def create_transaction(payload: TransactionCreate, db: Session = Depends(get_db)):
    _validate_tx_type(payload.tx_type)

    tx = Transaction(
        user_email=payload.email,
        amount=payload.amount,
        tx_date=payload.tx_date,
        source=payload.source,
        tx_type=payload.tx_type,
        # CNPJ do cliente só faz sentido para venda (US-27) — guardar em
        # compra confundiria com o CNPJ do fornecedor, fora de escopo aqui.
        cnpj_cliente=payload.cnpj_cliente if payload.tx_type == "venda" else None,
    )
    db.add(tx)
    db.flush()  # atribui tx.id antes de montar o evento
    emitir_evento(
        db,
        "transacao.criada",
        {
            "transacao_id": tx.id,
            "email": tx.user_email,
            "valor": float(tx.amount),
            "tx_type": tx.tx_type,
            "tx_date": tx.tx_date.isoformat(),
        },
        chave_particao=payload.email,
    )
    db.commit()
    db.refresh(tx)
    logger.info(
        "transacao.criada",
        email=payload.email,
        amount=payload.amount,
        tx_type=payload.tx_type,
        source=payload.source,
    )

    return TransactionOut(
        id=tx.id,
        email=tx.user_email,
        amount=float(tx.amount),
        tx_date=tx.tx_date,
        source=tx.source,
        tx_type=tx.tx_type,
        cnpj_cliente=tx.cnpj_cliente,
    )


@app.patch(
    "/transactions/{tx_id}",
    response_model=TransactionOut,
    responses={
        400: {"description": "tx_type fora de 'venda' | 'compra'"},
        404: {"description": "Transação não encontrada"},
    },
)
def update_transaction(
    tx_id: Annotated[int, Path(ge=1, le=ID_MAXIMO)],
    payload: TransactionUpdate,
    db: Session = Depends(get_db),
):
    """Permite editar uma transação já registrada (ex.: corrigir valor ou data
    extraídos incorretamente de um documento). Os totais do dashboard e do
    agente conversacional refletem a mudança automaticamente, pois ambos
    consultam este serviço em tempo real."""
    tx = db.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    antes = {"valor": float(tx.amount), "tx_type": tx.tx_type}

    if payload.amount is not None:
        # Via `str()`, não `Decimal(payload.amount)` direto: um `float` como
        # 19.99 não é exatamente representável em binário, e `Decimal(19.99)`
        # herdaria esse erro de arredondamento num valor monetário. Mesma
        # convenção usada em toda agregação deste arquivo.
        tx.amount = Decimal(str(payload.amount))
    if payload.tx_date is not None:
        tx.tx_date = payload.tx_date
    if payload.source is not None:
        tx.source = payload.source
    if payload.tx_type is not None:
        _validate_tx_type(payload.tx_type)
        tx.tx_type = payload.tx_type
    if payload.cnpj_cliente is not None:
        tx.cnpj_cliente = payload.cnpj_cliente

    emitir_evento(
        db,
        "transacao.atualizada",
        {
            "transacao_id": tx.id,
            "email": tx.user_email,
            "tx_date": tx.tx_date.isoformat(),
            "antes": antes,
            "depois": {"valor": float(tx.amount), "tx_type": tx.tx_type},
        },
        chave_particao=tx.user_email,
    )
    db.commit()
    db.refresh(tx)
    logger.info("transacao.atualizada", tx_id=tx.id, email=tx.user_email)

    return TransactionOut(
        id=tx.id,
        email=tx.user_email,
        amount=float(tx.amount),
        tx_date=tx.tx_date,
        source=tx.source,
        tx_type=tx.tx_type,
        cnpj_cliente=tx.cnpj_cliente,
    )


@app.delete(
    "/transactions/{tx_id}",
    responses={404: {"description": "Transação não encontrada"}},
)
def delete_transaction(
    tx_id: Annotated[int, Path(ge=1, le=ID_MAXIMO)],
    db: Session = Depends(get_db),
):
    """Apaga um lançamento — usado quando o usuário apaga a nota que o gerou
    (#96). Os totais do painel e do agente mudam na hora, como na edição."""
    tx = db.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    emitir_evento(
        db,
        "transacao.removida",
        {
            "transacao_id": tx.id,
            "email": tx.user_email,
            "tx_date": tx.tx_date.isoformat(),
            "valor": float(tx.amount),
            "tx_type": tx.tx_type,
        },
        chave_particao=tx.user_email,
    )
    db.delete(tx)
    db.commit()
    logger.info("transacao.removida", tx_id=tx_id)
    return {"id": tx_id, "removida": True}


@app.get("/transactions", response_model=list[TransactionOut])
def list_transactions(
    email: EmailStr,
    year: int | None = Query(default=None, ge=ANO_MINIMO, le=ANO_MAXIMO),
    month: int | None = Query(default=None, ge=1, le=12),
    db: Session = Depends(get_db),
):
    """
    Lista transações filtrando por e-mail e, opcionalmente, por ano e mês.
    Útil para montar totais mensais no frontend.
    """
    query = db.query(Transaction).filter(Transaction.user_email == email)

    if year is not None:
        query = query.filter(func.extract("year", Transaction.tx_date) == year)
    if month is not None:
        query = query.filter(func.extract("month", Transaction.tx_date) == month)

    txs = query.order_by(Transaction.tx_date.desc()).all()

    return [
        TransactionOut(
            id=tx.id,
            email=tx.user_email,
            amount=float(tx.amount),
            tx_date=tx.tx_date,
            source=tx.source,
            tx_type=tx.tx_type,
            cnpj_cliente=tx.cnpj_cliente,
        )
        for tx in txs
    ]


@app.get("/summary/{email}", response_model=SummaryOut)
def get_summary(
    email: EmailStr,
    year: int | None = Query(
        default=None,
        ge=ANO_MINIMO,
        le=ANO_MAXIMO,
        description="Ano de referência; padrão é o ano corrente",
    ),
    db: Session = Depends(get_db),
):
    year = year if year is not None else ano_corrente()

    base_filter = [
        Transaction.user_email == email,
        func.extract("year", Transaction.tx_date) == year,
    ]

    # Apenas "venda" conta como faturamento para o limite anual do MEI.
    # "compra" é despesa e não deve inflar esse número, mas é somada à parte
    # para compor o balancete (saldo_liquido).
    total_vendas = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(*base_filter, Transaction.tx_type == "venda")
        .scalar()
    )
    total_compras = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(*base_filter, Transaction.tx_type == "compra")
        .scalar()
    )

    # A partir daqui quem decide é o domínio. O serviço agrega e traduz; a
    # regra fiscal — o que conta para o teto, onde ficam as bordas, quando
    # alertar — mora em app/dominio e é testada sem banco (US-03).
    parametros = parametros_do_usuario(db, email)
    resumo = calcular_resumo(
        vendas=Decimal(str(total_vendas or 0)),
        compras=Decimal(str(total_compras or 0)),
        limite=parametros.limite_anual,
        limiar_alerta=parametros.limiar_alerta,
    )

    return SummaryOut(
        email=email,
        year=year,
        total_revenue=float(resumo.faturamento),
        total_despesas=float(resumo.despesas),
        saldo_liquido=float(resumo.saldo_liquido),
        annual_limit=float(resumo.limite),
        remaining=float(resumo.restante),
        exceeded=resumo.excedeu,
        percent_used=float(resumo.percentual_usado),
        alert_level=resumo.nivel_alerta.value,
        alert_threshold_percent=float(parametros.limiar_alerta * 100),
    )


def _soma_vendas_no_intervalo(db: Session, email: str, inicio: date, fim: date) -> float:
    """Soma de vendas em `[inicio, fim]`, inclusive — usada para as janelas de
    30 e 90 dias do motor de ritmo (US-25/US-26)."""
    return (
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.user_email == email,
            Transaction.tx_type == "venda",
            Transaction.tx_date >= inicio,
            Transaction.tx_date <= fim,
        )
        .scalar()
        or 0
    )


@app.get(
    "/ritmo/{email}",
    response_model=RitmoOut,
    responses={
        400: {"description": "data_abertura não pode ser depois de hoje (ou do fim do ano fechado)"}
    },
)
def get_ritmo(
    email: EmailStr,
    year: int | None = Query(
        default=None,
        ge=ANO_MINIMO,
        le=ANO_MAXIMO,
        description="Ano de referência; padrão é o ano corrente",
    ),
    data_abertura: date | None = Query(
        default=None,
        description=(
            "Abertura do MEI. Sem valor, assume abertura antes do ano de "
            "referência (limite cheio) — o cadastro real chega com a US-34 "
            "(Perfil do MEI)."
        ),
    ),
    db: Session = Depends(get_db),
):
    """Gauge e painel de ritmo do dashboard (US-25), sobre o motor de
    domínio da US-28. Agrega só o necessário para `calcular_projecao`; quem
    decide o nível e a tendência é o domínio, não esta rota."""
    year = year if year is not None else ano_corrente()
    # Ritmo é sobre o ano em curso: para um ano fechado, não há o que projetar
    # — trata como "ano inteiro decorrido" em vez de usar a data real de hoje,
    # que produziria uma contagem de dias sem sentido para um ano passado.
    hoje = datetime.now(UTC).date() if year == ano_corrente() else date(year, 12, 31)
    parametros = parametros_do_usuario(db, email)
    abertura = data_abertura_do_usuario(db, email, data_abertura) or date(year - 1, 1, 1)

    vendas_do_ano = [
        Transaction.user_email == email,
        func.extract("year", Transaction.tx_date) == year,
        Transaction.tx_type == "venda",
    ]
    total_vendas = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(*vendas_do_ano).scalar()
    )
    maior_venda = (
        db.query(func.coalesce(func.max(Transaction.amount), 0)).filter(*vendas_do_ano).scalar()
    )
    qtd_vendas = db.query(func.count(Transaction.id)).filter(*vendas_do_ano).scalar() or 0

    vendas_recentes = _soma_vendas_no_intervalo(db, email, hoje - timedelta(days=30), hoje)
    vendas_90d = _soma_vendas_no_intervalo(db, email, hoje - timedelta(days=90), hoje)

    try:
        projecao = calcular_projecao(
            faturamento_acumulado=Decimal(str(total_vendas or 0)),
            faturamento_ultimos_30_dias=Decimal(str(vendas_recentes)),
            faturamento_ultimos_90_dias=Decimal(str(vendas_90d)),
            qtd_transacoes_ano=int(qtd_vendas),
            maior_transacao_ano=Decimal(str(maior_venda or 0)),
            data_abertura=abertura,
            hoje=hoje,
            parametros=parametros,
        )
    except ValueError as erro:
        # `data_abertura` é parâmetro livre (US-34 ainda não existe) — quem
        # chama pode mandar uma data depois de "hoje". É erro do chamador, não
        # do serviço: 400, não 500. Encontrado pela suíte de contrato.
        raise HTTPException(status_code=400, detail=str(erro)) from erro

    # O percentual usado e o restante seguem a mesma régua do /summary — só
    # que sobre o limite aplicável (cheio ou proporcional), não sempre o cheio.
    resumo = calcular_resumo(
        vendas=Decimal(str(total_vendas or 0)),
        compras=Decimal("0"),
        limite=projecao.limite_aplicavel,
        limiar_alerta=parametros.limiar_alerta,
    )

    return RitmoOut(
        email=email,
        year=year,
        limite_aplicavel=float(projecao.limite_aplicavel),
        meses_de_atividade=projecao.meses_de_atividade,
        proporcional=projecao.meses_de_atividade is not None,
        total_vendas=float(resumo.faturamento),
        restante=float(resumo.restante),
        percent_used=float(resumo.percentual_usado),
        nivel=projecao.nivel.value,
        dias_decorridos=projecao.dias_decorridos,
        total_dias_ano=projecao.total_dias_ano,
        taxa_diaria=float(projecao.taxa_diaria),
        taxa_diaria_referencia=float(projecao.taxa_diaria_referencia),
        taxa_diaria_recente=float(projecao.taxa_diaria_recente),
        taxa_diaria_90d=float(projecao.taxa_diaria_90d),
        indice_ritmo=float(projecao.indice_ritmo) if projecao.indice_ritmo is not None else None,
        aceleracao=float(projecao.aceleracao) if projecao.aceleracao is not None else None,
        tendencia=projecao.tendencia.value,
        projecao_disponivel=projecao.projecao_disponivel,
        motivo_indisponivel=projecao.motivo_indisponivel,
        projecao_anual=float(projecao.projecao_anual)
        if projecao.projecao_anual is not None
        else None,
        dias_ate_estouro=projecao.dias_ate_estouro,
        data_prevista_estouro=projecao.data_prevista_estouro,
        faturamento_seguro_mes=float(projecao.faturamento_seguro_mes),
        influenciada_por_lancamento_atipico=projecao.influenciada_por_lancamento_atipico,
    )


@app.get("/ritmo/{email}/serie", response_model=list[PontoSerieAcumulada])
def get_serie_acumulada(
    email: EmailStr,
    year: int | None = Query(
        default=None,
        ge=ANO_MINIMO,
        le=ANO_MAXIMO,
        description="Ano de referência; padrão é o ano corrente",
    ),
    db: Session = Depends(get_db),
):
    """Curva do acumulado real do ano, um ponto por dia — a área "realizado"
    do gráfico de corrida contra o limite (US-26). A linha de referência e o
    cone de projeção são calculados no cliente, a partir de `GET /ritmo`: são
    só reta e taxas, não precisam de outra viagem ao banco.

    Carrega o último valor conhecido adiante nos dias sem venda, para a área
    ficar contínua em vez de cair a zero entre lançamentos.
    """
    year = year if year is not None else ano_corrente()
    hoje = datetime.now(UTC).date() if year == ano_corrente() else date(year, 12, 31)
    inicio = date(year, 1, 1)

    linhas = (
        db.query(Transaction.tx_date, func.sum(Transaction.amount))
        .filter(
            Transaction.user_email == email,
            func.extract("year", Transaction.tx_date) == year,
            Transaction.tx_type == "venda",
        )
        .group_by(Transaction.tx_date)
        .all()
    )
    por_dia = {tx_date: Decimal(str(soma)) for tx_date, soma in linhas}

    pontos: list[PontoSerieAcumulada] = []
    acumulado = Decimal("0")
    dia = inicio
    while dia <= hoje:
        acumulado += por_dia.get(dia, Decimal("0"))
        pontos.append(PontoSerieAcumulada(data=dia, acumulado=float(acumulado)))
        dia += timedelta(days=1)
    return pontos


@app.get(
    "/mensal/{email}",
    response_model=list[MesResumoOut],
    responses={400: {"description": "data_abertura não pode ser depois do ano de referência"}},
)
def get_mensal(
    email: EmailStr,
    year: int | None = Query(
        default=None,
        ge=ANO_MINIMO,
        le=ANO_MAXIMO,
        description="Ano de referência; padrão é o ano corrente",
    ),
    data_abertura: date | None = Query(
        default=None,
        description=(
            "Abertura do MEI, para a meta considerar o limite proporcional — "
            "mesmo default seguro de /ritmo (limite cheio) sem a US-34."
        ),
    ),
    db: Session = Depends(get_db),
):
    """ "Mês a mês" do dashboard (US-27): vendas e despesas por mês, com a
    meta mensal sobreposta. Doze pontos sempre, mês sem lançamento incluso
    com zero — quem decide isso é `dominio.faturamento.calcular_serie_mensal`."""
    year = year if year is not None else ano_corrente()
    parametros = parametros_do_usuario(db, email)
    abertura = data_abertura_do_usuario(db, email, data_abertura) or date(year - 1, 1, 1)

    linhas = (
        db.query(
            func.extract("month", Transaction.tx_date),
            Transaction.tx_type,
            func.coalesce(func.sum(Transaction.amount), 0),
        )
        .filter(
            Transaction.user_email == email,
            func.extract("year", Transaction.tx_date) == year,
        )
        .group_by(func.extract("month", Transaction.tx_date), Transaction.tx_type)
        .all()
    )

    vendas_por_mes: dict[int, Decimal] = {}
    despesas_por_mes: dict[int, Decimal] = {}
    for mes_bruto, tx_type, total in linhas:
        alvo = vendas_por_mes if tx_type == "venda" else despesas_por_mes
        alvo[int(mes_bruto)] = Decimal(str(total))

    try:
        limite_aplicavel = calcular_limite_aplicavel(
            abertura,
            year,
            limite_cheio=parametros.limite_anual,
            proporcional=parametros.limite_proporcional,
        ).valor
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro
    serie = calcular_serie_mensal(
        vendas_por_mes, despesas_por_mes, limite_aplicavel, meta_mensal=parametros.meta_mensal
    )

    return [
        MesResumoOut(
            mes=ponto.mes,
            vendas=float(ponto.vendas),
            despesas=float(ponto.despesas),
            meta=float(ponto.meta),
            acima_da_meta=ponto.acima_da_meta,
        )
        for ponto in serie
    ]


@app.get("/concentracao/{email}", response_model=list[ConcentracaoClienteOut])
def get_concentracao(
    email: EmailStr,
    year: int | None = Query(
        default=None,
        ge=ANO_MINIMO,
        le=ANO_MAXIMO,
        description="Ano de referência; padrão é o ano corrente",
    ),
    db: Session = Depends(get_db),
):
    """ "Origem do faturamento" do dashboard (US-27): concentração de venda
    por CNPJ do cliente. Só entra venda com `cnpj_cliente` identificado — o
    percentual é sobre esse total identificado, não sobre o faturamento do
    ano inteiro (ver docstring de `calcular_concentracao_clientes`)."""
    year = year if year is not None else ano_corrente()

    linhas = (
        db.query(Transaction.cnpj_cliente, func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.user_email == email,
            Transaction.tx_type == "venda",
            Transaction.cnpj_cliente.isnot(None),
            func.extract("year", Transaction.tx_date) == year,
        )
        .group_by(Transaction.cnpj_cliente)
        .all()
    )
    vendas_por_cnpj = {cnpj: Decimal(str(total)) for cnpj, total in linhas}

    itens = calcular_concentracao_clientes(
        vendas_por_cnpj, limiar=parametros_do_usuario(db, email).limiar_concentracao_cliente
    )

    return [
        ConcentracaoClienteOut(
            cnpj=item.cnpj,
            valor=float(item.valor),
            percentual=float(item.percentual),
            alerta=item.alerta,
        )
        for item in itens
    ]


def _parametros_para_saida(parametros: ParametrosFiscais) -> ParametrosConfig:
    return ParametrosConfig(
        limite_anual=float(parametros.limite_anual),
        limite_proporcional=parametros.limite_proporcional,
        margem_desenquadramento=float(parametros.margem_desenquadramento),
        limiar_alerta=float(parametros.limiar_alerta),
        meta_mensal=float(parametros.meta_mensal) if parametros.meta_mensal is not None else None,
        limiar_concentracao_cliente=float(parametros.limiar_concentracao_cliente),
        dias_minimos_para_projetar=parametros.dias_minimos_para_projetar,
        transacoes_minimas_para_projetar=parametros.transacoes_minimas_para_projetar,
        dias_abertura_recente=parametros.dias_abertura_recente,
        limiar_lancamento_atipico=float(parametros.limiar_lancamento_atipico),
        limiar_atencao_ritmo_realizado=float(parametros.limiar_atencao_ritmo_realizado),
    )


def _montar_configuracao_out(email: str, config: ConfiguracaoFiscal | None) -> ConfiguracaoOut:
    ajustes = _ajustes_para_dominio(config.ajustes) if config else {}
    # Gravado e validado no PUT; se ficou inválido depois (campo do domínio
    # removido), mostra o padrão em vez de 500 — o PUT seguinte corrige.
    try:
        parametros = ParametrosFiscais.com_ajustes(ajustes)
    except (ValueError, TypeError):
        parametros, ajustes = PARAMETROS_PADRAO, {}
    return ConfiguracaoOut(
        email=email,
        data_abertura=config.data_abertura if config else None,
        parametros=_parametros_para_saida(parametros),
        padrao=_parametros_para_saida(PARAMETROS_PADRAO),
        personalizados=sorted(ajustes),
        ativa=metricas_configuraveis_ligadas(),
    )


@app.get("/configuracao/{email}", response_model=ConfiguracaoOut)
def get_configuracao(email: EmailStr, db: Session = Depends(get_db)):
    """Configuração das regras e metas do usuário (#91), com os valores
    padrão ao lado. Quem nunca configurou recebe o padrão inteiro."""
    return _montar_configuracao_out(email, carregar_configuracao(db, email))


@app.put(
    "/configuracao/{email}",
    response_model=ConfiguracaoOut,
    responses={422: {"description": "Parâmetro desconhecido ou fora da faixa permitida"}},
)
def put_configuracao(email: EmailStr, body: ConfiguracaoIn, db: Session = Depends(get_db)):
    """Atualiza parte da configuração. A validação é a do domínio
    (`ParametrosFiscais`): o que ele recusa vira 422 com a mensagem dele, e
    nada é gravado."""
    config = carregar_configuracao(db, email)
    ajustes = _ajustes_para_dominio(config.ajustes) if config else {}

    for nome, valor in body.parametros.items():
        if valor is None:
            ajustes.pop(nome, None)
        elif nome in CAMPOS_DECIMAIS:
            if isinstance(valor, bool):
                raise HTTPException(status_code=422, detail=f"{nome} deve ser numérico")
            ajustes[nome] = Decimal(str(valor))
        else:
            ajustes[nome] = valor

    # O padrão só vale "como padrão": um ajuste igual ao padrão não é
    # personalização e sai da lista (mantém "voltar ao padrão" coerente).
    ajustes = {
        nome: valor
        for nome, valor in ajustes.items()
        if not hasattr(PARAMETROS_PADRAO, nome) or getattr(PARAMETROS_PADRAO, nome) != valor
    }

    try:
        ParametrosFiscais.com_ajustes(ajustes)
    except (ValueError, TypeError) as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from erro

    if config is None:
        config = ConfiguracaoFiscal(user_email=email, ajustes={})
        db.add(config)
    config.ajustes = _ajustes_para_json(ajustes)
    if "data_abertura" in body.model_fields_set:
        config.data_abertura = body.data_abertura
    db.commit()
    db.refresh(config)

    logger.info("configuracao.atualizada", email=email, campos=sorted(ajustes))
    return _montar_configuracao_out(email, config)


@app.delete("/configuracao/{email}", response_model=ConfiguracaoOut)
def delete_configuracao(email: EmailStr, db: Session = Depends(get_db)):
    """Volta tudo ao padrão (inclusive apaga a data de abertura)."""
    config = carregar_configuracao(db, email)
    if config is not None:
        db.delete(config)
        db.commit()
    logger.info("configuracao.restaurada", email=email)
    return _montar_configuracao_out(email, None)


def format_brl(value: float) -> str:
    """Formata um número no padrão brasileiro (milhar '.', decimal ',')."""
    return f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def nome_do_relatorio(email: str, year: int) -> str:
    """Monta o nome do arquivo com o e-mail reduzido a caracteres seguros.

    Cabeçalho HTTP é codificado em latin-1. Endereços internacionalizados são
    válidos para o `EmailStr` e derrubavam a rota com `UnicodeEncodeError` na
    montagem do `Content-Disposition`. Encontrado pela suíte de contrato.
    """
    apelido = re.sub(r"[^A-Za-z0-9._-]", "_", email)[:80]
    return f"relatorio-mei-{apelido}-{year}.pdf"


def build_report_pdf(email: str, year: int, summary: SummaryOut, txs: list[Transaction]) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
    )
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("FiscalFlow &ndash; Relatório Anual do MEI", styles["Title"]))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(f"E-mail: {email}", styles["Normal"]))
    story.append(Paragraph(f"Ano de referência: {year}", styles["Normal"]))
    story.append(
        Paragraph(
            f"Gerado em: {datetime.now(UTC).strftime('%d/%m/%Y %H:%M UTC')}",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 0.6 * cm))

    status_label = {
        "ok": "Dentro do limite",
        "warning": "Alerta de proximidade",
        "exceeded": "Limite ultrapassado",
    }
    summary_data = [
        ["Faturamento acumulado (vendas)", f"R$ {format_brl(summary.total_revenue)}"],
        ["Despesas acumuladas (compras)", f"R$ {format_brl(summary.total_despesas)}"],
        ["Saldo líquido", f"R$ {format_brl(summary.saldo_liquido)}"],
        ["Limite anual do MEI", f"R$ {format_brl(summary.annual_limit)}"],
        ["Valor restante no limite", f"R$ {format_brl(summary.remaining)}"],
        ["% do limite utilizado", f"{summary.percent_used:.1f}%".replace(".", ",")],
        ["Status", status_label.get(summary.alert_level, summary.alert_level)],
    ]
    summary_table = Table(summary_data, colWidths=[8 * cm, 8 * cm])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(summary_table)
    story.append(Spacer(1, 0.8 * cm))

    story.append(Paragraph("Transações do ano", styles["Heading2"]))
    story.append(Spacer(1, 0.2 * cm))

    if not txs:
        story.append(Paragraph("Nenhuma transação registrada neste ano.", styles["Normal"]))
    else:
        tx_type_label = {"venda": "Venda", "compra": "Compra"}
        rows = [["Data", "Tipo", "Valor (R$)", "Origem"]]
        for tx in txs:
            rows.append(
                [
                    tx.tx_date.strftime("%d/%m/%Y"),
                    tx_type_label.get(tx.tx_type, tx.tx_type),
                    format_brl(float(tx.amount)),
                    tx.source or "-",
                ]
            )
        tx_table = Table(rows, colWidths=[3 * cm, 2.5 * cm, 3.5 * cm, 7 * cm], repeatRows=1)
        tx_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("PADDING", (0, 0), (-1, -1), 5),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#f1f5f9")],
                    ),
                ]
            )
        )
        story.append(tx_table)

    doc.build(story)
    return buffer.getvalue()


@app.get(
    "/report/{email}",
    response_class=StreamingResponse,
    # Sem isto o OpenAPI declara application/json para uma rota que devolve um
    # PDF: o contrato publicado descrevia algo que o serviço nunca entregou.
    responses={200: {"description": "Relatório anual", "content": {"application/pdf": {}}}},
)
def get_report_pdf(
    email: EmailStr,
    year: int | None = Query(
        default=None,
        ge=ANO_MINIMO,
        le=ANO_MAXIMO,
        description="Ano de referência; padrão é o ano corrente",
    ),
    db: Session = Depends(get_db),
):
    """Gera um relatório em PDF com o resumo anual e as transações do MEI."""
    year = year if year is not None else ano_corrente()
    summary = get_summary(email=email, year=year, db=db)

    txs = (
        db.query(Transaction)
        .filter(
            Transaction.user_email == email,
            func.extract("year", Transaction.tx_date) == year,
        )
        .order_by(Transaction.tx_date.asc())
        .all()
    )

    pdf_bytes = build_report_pdf(email=email, year=year, summary=summary, txs=txs)

    logger.info("relatorio.pdf_gerado", email=email, year=year, num_transacoes=len(txs))

    filename = nome_do_relatorio(email, year)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
