import os
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx
import structlog
from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types
from pgvector.sqlalchemy import Vector
from pydantic import BaseModel, EmailStr
from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine, func, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from . import consumo
from .acl import RetratoFiscal, traduzir_resumo_limits
from .flags import setup_flags, shutdown_flags
from .metrics import rag_similaridade_melhor, registrar_custo_gemini
from .observability import setup_metrics, setup_observability, setup_tracing

setup_observability()
logger = structlog.get_logger()

# --------------------------------------------------------------------
# Configurações básicas / URLs dos microsserviços
# --------------------------------------------------------------------

LIMITS_BASE_URL = os.getenv("LIMITS_BASE_URL", "http://limits:8000")
DOCUMENTS_BASE_URL = os.getenv("DOCUMENTS_BASE_URL", "http://documents:8000")
BILLING_BASE_URL = os.getenv("BILLING_BASE_URL", "http://billing:8000")

# --------------------------------------------------------------------
# Configuração da LLM (Gemini)
# --------------------------------------------------------------------

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
EMBEDDING_DIM = 768

gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# --------------------------------------------------------------------
# Banco de dados vetorial (pgvector) para RAG real
# --------------------------------------------------------------------

DATABASE_URL = "postgresql+psycopg2://agent_user:agent_password@agent_db:5432/agent_db"

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class KnowledgeChunk(Base):
    """Base de conhecimento geral sobre regras do MEI (RAG compartilhado)."""

    __tablename__ = "knowledge_chunks"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String, nullable=False)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(EMBEDDING_DIM), nullable=True)


class DocumentChunk(Base):
    """Texto extraído dos documentos confirmados pelo usuário (RAG por usuário)."""

    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, index=True)
    user_email = Column(String, index=True, nullable=False)
    source_filename = Column(String, nullable=True)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(EMBEDDING_DIM), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


def create_tables_with_retry(max_retries: int = 8, delay_seconds: int = 2):
    for attempt in range(1, max_retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()
            Base.metadata.create_all(bind=engine)
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


# --------------------------------------------------------------------
# Embeddings (Gemini)
# --------------------------------------------------------------------


def embed_text(
    text_value: str, email: str | None = None, operacao: str = "embedding"
) -> list[float] | None:
    """Gera o vetor de embedding de um texto usando o modelo Gemini de embeddings.
    Retorna None se o Gemini não estiver configurado ou a chamada falhar (modo demo).

    Com `email`, a chamada é registrada no billing (ADR-0024, por flag). A
    resposta de embedding não traz contagem de tokens; a contagem é feita em
    segundo plano pelo `count_tokens` da API. Sem `email` (semeadura da base
    de regras), o custo é da plataforma e não entra no extrato de ninguém."""
    if gemini_client is None or not text_value.strip():
        return None
    try:
        result = gemini_client.models.embed_content(
            model=GEMINI_EMBEDDING_MODEL,
            contents=text_value[:8000],
            config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIM),
        )
        embeddings = result.embeddings
        if not embeddings or embeddings[0].values is None:
            return None
        vetor = list(embeddings[0].values)
    except Exception:
        return None
    cliente, texto = gemini_client, text_value[:8000]
    consumo.registrar(
        email,
        "agent-orchestrator",
        operacao,
        GEMINI_EMBEDDING_MODEL,
        None,
        0,
        contar_entrada=lambda: (
            cliente.models.count_tokens(model=GEMINI_EMBEDDING_MODEL, contents=texto).total_tokens
            or 0
        ),
    )
    return vetor


def chunk_text(text_value: str, max_chars: int = 900) -> list[str]:
    text_value = text_value.strip()
    if not text_value:
        return []
    chunks = []
    for i in range(0, len(text_value), max_chars):
        piece = text_value[i : i + max_chars].strip()
        if piece:
            chunks.append(piece)
    return chunks


# --------------------------------------------------------------------
# Base de conhecimento (seed) sobre regras do MEI
# --------------------------------------------------------------------

MEI_KNOWLEDGE_SEED = [
    (
        "Receita Federal / Portal do Empreendedor",
        "Limite anual de faturamento do MEI",
        "O limite de faturamento do MEI em 2026 é de R$ 81.000,00 por ano (cerca de R$ "
        "6.750,00 por mês), valor mantido desde 2018. Para MEIs abertos no meio do ano, o "
        "limite é proporcional aos meses de atividade: por exemplo, uma abertura em julho "
        "tem limite de aproximadamente R$ 40.500,00 naquele ano.",
    ),
    (
        "Receita Federal / CGSN",
        "Consequências de ultrapassar o limite anual",
        "Se o MEI ultrapassar o limite anual em até 20% (ou seja, até R$ 97.200,00), ele paga "
        "um DAS complementar sobre o valor excedente e é migrado para Microempresa (ME) a "
        "partir de janeiro do ano seguinte. Se ultrapassar em mais de 20%, o desenquadramento "
        "é retroativo a 1º de janeiro do ano em que o limite foi excedido (LC 123/2006, "
        "art. 18-A; Resolução CGSN nº 140/2018, art. 115), com cobrança de impostos, multa e "
        "juros como Microempresa sobre todo o período retroativo.",
    ),
    (
        "Resolução CGSN nº 183/2025",
        "Rendimentos recebidos no CPF contam para o limite",
        "Desde a Resolução CGSN nº 183/2025, rendimentos recebidos no CPF do titular "
        "referentes à mesma atividade econômica do MEI também contam para o cálculo do "
        "limite de faturamento do CNPJ, e não apenas os valores recebidos diretamente pela "
        "empresa.",
    ),
    (
        "Receita Federal / Simples Nacional",
        "DAS: guia mensal do MEI",
        "O DAS (Documento de Arrecadação do Simples Nacional) é o boleto mensal de "
        "impostos do MEI, com vencimento todo dia 20. Ele reúne a contribuição do INSS e, "
        "dependendo da atividade exercida, o ICMS (comércio e indústria) ou o ISS (serviços) "
        "em valor fixo mensal.",
    ),
    (
        "Receita Federal / Simples Nacional",
        "DASN-SIMEI: declaração anual obrigatória",
        "Todo MEI deve entregar a Declaração Anual Simplificada (DASN-SIMEI) até o dia 31 de "
        "maio de cada ano, referente ao faturamento do ano anterior, mesmo que não tenha "
        "faturado nada. A entrega em atraso gera multa de 2% ao mês sobre os tributos "
        "declarados, limitada a 20%, com valor mínimo de R$ 50,00.",
    ),
    (
        "Portal do Empreendedor",
        "Outras causas de perda do enquadramento como MEI",
        "Além de ultrapassar o limite de faturamento, o MEI perde o enquadramento se "
        "contratar mais de um funcionário, abrir filial, se tornar sócio de outra empresa ou "
        "passar a exercer atividade econômica não permitida para o MEI.",
    ),
    (
        "Receita Federal (dados de fiscalização, 2024)",
        "Fiscalização cruzada de dados",
        "A Receita Federal cruza dados de notas fiscais emitidas, maquininhas de cartão, "
        "e-Financeira e marketplaces para identificar MEIs que ultrapassaram o limite de "
        "faturamento; somente em 2024, mais de 570 mil MEIs foram desenquadrados por excesso "
        "de faturamento.",
    ),
    (
        "Portal do Simples Nacional",
        "Pedido de desenquadramento voluntário",
        "Desde março de 2025, o próprio MEI pode solicitar o desenquadramento diretamente "
        "pelo Portal do Simples Nacional, sem precisar de um contador, com até três pedidos "
        "permitidos.",
    ),
    (
        "Receita Federal / Simples Nacional",
        "Apenas vendas contam para o limite anual do MEI",
        "O limite anual de R$ 81.000,00 do MEI é calculado apenas sobre o faturamento com "
        "vendas de produtos ou prestação de serviços (notas fiscais emitidas pelo próprio "
        "MEI). Compras feitas pelo MEI, como aquisição de mercadorias, insumos ou material de "
        "uso, são despesas do negócio e não contam para esse limite, embora devam ser "
        "registradas para o controle financeiro e o cálculo do lucro.",
    ),
]


def seed_knowledge_base():
    """Insere os itens de MEI_KNOWLEDGE_SEED que ainda não existem na base
    (idempotente por título), permitindo adicionar novos fatos à base de
    conhecimento em deploys futuros sem duplicar os que já foram inseridos.

    Trecho já existente mas sem vetor é vetorizado de novo: a primeira subida
    sem `GEMINI_API_KEY` grava a base com `embedding` nulo, e a busca filtra
    nulos — sem este reparo, ligar a chave depois nunca tornaria a base
    visível ao RAG. Trecho cujo texto mudou no código é atualizado e
    re-vetorizado, para que uma correção chegue à base já populada."""
    db = SessionLocal()
    try:
        existing = {chunk.title: chunk for chunk in db.query(KnowledgeChunk).all()}
        for source, title, content in MEI_KNOWLEDGE_SEED:
            chunk = existing.get(title)
            if chunk is not None:
                # Texto corrigido no código (ex.: R2, retroação a 1º de janeiro)
                # precisa substituir o gravado e ser vetorizado de novo; senão a
                # base continuaria servindo a versão errada ao RAG.
                if chunk.content != content or chunk.source != source:
                    chunk.content = content
                    chunk.source = source
                    chunk.embedding = embed_text(f"{title}. {content}")
                elif chunk.embedding is None:
                    chunk.embedding = embed_text(f"{title}. {content}")
                continue
            embedding = embed_text(f"{title}. {content}")
            db.add(
                KnowledgeChunk(
                    source=source,
                    title=title,
                    content=content,
                    embedding=embedding,
                )
            )
        db.commit()
    finally:
        db.close()


# --------------------------------------------------------------------
# Recuperação (retrieval) via similaridade de cosseno (pgvector)
# --------------------------------------------------------------------


def retrieve_knowledge(
    db: Session, query_embedding: list[float], top_k: int = 3
) -> list[KnowledgeChunk]:
    if not query_embedding:
        return []
    # O cosine_distance devolve a distância (1 - similaridade).
    # Para registrar a similaridade, calculamos 1 - distância
    results = (
        db.query(
            KnowledgeChunk,
            KnowledgeChunk.embedding.cosine_distance(query_embedding).label("distance"),
        )
        .filter(KnowledgeChunk.embedding.isnot(None))
        .order_by("distance")
        .limit(top_k)
        .all()
    )

    if results:
        best_distance = results[0].distance
        rag_similaridade_melhor.labels(tipo_base="regras_mei").observe(1 - float(best_distance))

    return [r[0] for r in results]


def retrieve_document_chunks(
    db: Session, email: str, query_embedding: list[float], top_k: int = 3
) -> list[DocumentChunk]:
    if not query_embedding:
        return []
    results = (
        db.query(
            DocumentChunk,
            DocumentChunk.embedding.cosine_distance(query_embedding).label("distance"),
        )
        .filter(DocumentChunk.user_email == email, DocumentChunk.embedding.isnot(None))
        .order_by("distance")
        .limit(top_k)
        .all()
    )

    if results:
        best_distance = results[0].distance
        rag_similaridade_melhor.labels(tipo_base="documentos").observe(1 - float(best_distance))

    return [r[0] for r in results]


# --------------------------------------------------------------------
# FastAPI app
# --------------------------------------------------------------------


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Prepara o esquema antes de o serviço aceitar tráfego.

    Substitui o `@app.on_event("startup")`, que o FastAPI depreciou. Além de
    silenciar o aviso, o gerenciador de contexto deixa explícito onde termina
    a inicialização — e é o que a suíte de testes exercita ao entrar no
    `TestClient` como contexto.
    """
    create_tables_with_retry()
    seed_knowledge_base()
    setup_flags(app_name="agent-orchestrator")
    yield
    shutdown_flags()


app = FastAPI(title="Agent Orchestrator Service", lifespan=lifespan)

app.add_middleware(CorrelationIdMiddleware, header_name="X-Correlation-Id")

setup_metrics(app, service_name="agent-orchestrator")
setup_tracing(app, service_name="agent-orchestrator", engine=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------


class ChatRequest(BaseModel):
    email: EmailStr
    message: str


class ChatResponse(BaseModel):
    reply: str
    sources: list[str] = []


class IndexDocumentRequest(BaseModel):
    email: EmailStr
    source_filename: str | None = None
    content: str


class IndexDocumentResponse(BaseModel):
    chunks_indexed: int


# --------------------------------------------------------------------
# Healthcheck
# --------------------------------------------------------------------


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "agent-orchestrator",
        "rag_enabled": gemini_client is not None,
    }


@app.delete("/reset/{email}")
def reset_user_data(email: EmailStr, db: Session = Depends(get_db)):
    """Remove os trechos de documentos indexados para o RAG do usuário
    (DocumentChunk). A base de conhecimento geral sobre regras do MEI
    (KnowledgeChunk) é preservada, pois não é dado do usuário."""
    deleted = db.query(DocumentChunk).filter(DocumentChunk.user_email == email).delete()
    db.commit()
    return {"email": email, "document_chunks_deleted": deleted}


# --------------------------------------------------------------------
# Indexação de documentos confirmados (alimenta o RAG por usuário)
# --------------------------------------------------------------------


@app.post("/index-document", response_model=IndexDocumentResponse)
def index_document(payload: IndexDocumentRequest, db: Session = Depends(get_db)):
    pieces = chunk_text(payload.content)
    if not pieces:
        return IndexDocumentResponse(chunks_indexed=0)

    indexed = 0
    for piece in pieces:
        embedding = embed_text(piece, email=payload.email, operacao="embedding_indexacao")
        db.add(
            DocumentChunk(
                user_email=payload.email,
                source_filename=payload.source_filename,
                content=piece,
                embedding=embedding,
            )
        )
        if embedding is not None:
            indexed += 1
    db.commit()
    logger.info(
        "rag.documento_indexado",
        email=payload.email,
        source_filename=payload.source_filename,
        chunks=indexed,
    )
    return IndexDocumentResponse(chunks_indexed=indexed)


# --------------------------------------------------------------------
# Integração com LIMITS
# --------------------------------------------------------------------


def get_limits_summary(email: str) -> dict[str, Any]:
    url = f"{LIMITS_BASE_URL}/summary/{email}"
    try:
        resp = httpx.get(url, timeout=5.0)
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Erro ao conectar ao serviço de limites: {e}",
        ) from e

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Erro ao obter resumo de limites: {resp.text}",
        )

    return resp.json()


# --------------------------------------------------------------------
# Construção de prompt para o Gemini (com contexto recuperado via RAG)
# --------------------------------------------------------------------


def formatar_brl(valor: float) -> str:
    """Valor em reais no padrão brasileiro: "R$ 81.000,00".

    O `:,.2f` do Python produz "81,000.00" (padrão americano), e o modelo
    repetia esse formato na resposta. Não usa `locale` para não depender do
    locale instalado no contêiner."""
    sinal = "-" if valor < 0 else ""
    americano = f"{abs(valor):,.2f}"
    return f"{sinal}R$ " + americano.replace(",", "_").replace(".", ",").replace("_", ".")


def build_prompt(
    retrato: RetratoFiscal,
    user_message: str,
    email: str,
    knowledge_hits: list[KnowledgeChunk],
    document_hits: list[DocumentChunk],
) -> str:
    # US-46: o prompt lê o `RetratoFiscal` (modelo interno do agente), nunca o
    # dict cru do Limits. Campo novo no resumo não chega aqui; campo que sumiu
    # já virou padrão na tradução. O texto abaixo não conhece o formato do Limits.
    year = retrato.ano
    total_revenue = retrato.faturamento_vendas
    total_despesas = retrato.despesas_compras
    saldo_liquido = retrato.saldo_liquido
    annual_limit = retrato.limite_anual
    remaining = retrato.falta_para_o_limite
    exceeded = retrato.ultrapassou
    alert_level = retrato.nivel_alerta
    percent_used = retrato.percentual_usado

    excedeu_str = "sim" if exceeded else "não"

    alert_instruction = ""
    if alert_level == "exceeded":
        alert_instruction = (
            "\nATENÇÃO: o usuário JÁ ULTRAPASSOU o limite anual do MEI. "
            "Comece a resposta alertando isso com clareza, antes de qualquer outra orientação."
        )
    elif alert_level == "warning":
        alert_instruction = (
            f"\nATENÇÃO: o usuário já usou {percent_used:.1f}% do limite anual do MEI "
            f"(faixa de alerta, {retrato.limiar_alerta_percentual:.0f}% ou mais). "
            "Avise proativamente sobre a proximidade do teto, "
            "mesmo que a pergunta dele seja sobre outro assunto."
        )

    knowledge_block = ""
    if knowledge_hits:
        items = "\n".join(f"- ({k.source}) {k.title}: {k.content}" for k in knowledge_hits)
        knowledge_block = (
            f"\nBase de conhecimento sobre regras do MEI (recuperada por similaridade):\n{items}\n"
        )

    documents_block = ""
    if document_hits:
        items = "\n".join(
            f"- (arquivo: {d.source_filename or 'desconhecido'}) {d.content}" for d in document_hits
        )
        documents_block = f"\nTrechos de documentos enviados pelo próprio usuário (recuperados por similaridade):\n{items}\n"

    prompt = f"""
Você é um assistente fiscal especializado em MEI no Brasil.

Você está atendendo o usuário com e-mail: {email}.

Dados financeiros atuais do MEI (já separados por tipo de operação):
- Ano analisado: {year}
- Faturamento acumulado no ano (SOMA APENAS DAS VENDAS): {formatar_brl(total_revenue)}
- Despesas acumuladas no ano (SOMA APENAS DAS COMPRAS): {formatar_brl(total_despesas)}
- Saldo líquido (vendas menos compras): {formatar_brl(saldo_liquido)}
- Limite anual do MEI (aplica-se apenas às vendas): {formatar_brl(annual_limit)}
- Valor que ainda falta para atingir o limite: {formatar_brl(remaining)}
- Já ultrapassou o limite anual?: {excedeu_str}
{alert_instruction}
{knowledge_block}
{documents_block}

Mensagem do usuário:
\"\"\"{user_message}\"\"\"

Tarefas:
1. Responda à pergunta do usuário usando, sempre que relevante, a base de conhecimento e os
   trechos de documentos fornecidos acima como fonte de verdade (não invente regras que não
   estejam lá ou nos dados financeiros informados).
2. Se a base de conhecimento tiver uma regra diretamente relevante para a pergunta, cite-a
   explicitamente na resposta.
3. Dê orientações práticas e objetivas, em linguagem simples.
4. Se a base de conhecimento, os trechos de documentos e os dados financeiros acima não
   trouxerem a informação necessária para responder, diga claramente que a base de regras
   consultada não traz essa informação. Não complete a resposta com conhecimento geral:
   indique que o usuário confirme no Portal do Empreendedor, na Receita Federal ou com um
   contador. Se só parte da pergunta tiver suporte, responda essa parte e diga qual parte
   ficou sem suporte na base.

IMPORTANTE:
- Responda em português brasileiro.
- Não invente valores financeiros diferentes dos fornecidos.
- Escreva valores em reais no padrão brasileiro, como nos dados acima (R$ 1.234,56).
- Não invente regras fiscais que não estejam na base de conhecimento fornecida.
- NUNCA some despesas (compras) ao faturamento. O limite anual do MEI e o "faturamento"
  dizem respeito somente às vendas. Se o usuário perguntar sobre gastos, compras ou despesas,
  responda usando o valor de despesas acumuladas, não o de faturamento.
"""

    return prompt


# --------------------------------------------------------------------
# Chamada ao Gemini
# --------------------------------------------------------------------


def call_gemini(prompt: str, email: str | None = None) -> str:
    if gemini_client is None:
        return (
            "Sou o assistente MEI em modo demonstração. "
            "Os dados de limite foram carregados, mas o modelo Gemini "
            "não está configurado (variável GEMINI_API_KEY ausente)."
        )

    try:
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            entrada = response.usage_metadata.prompt_token_count or 0
            saida = response.usage_metadata.candidates_token_count or 0
            registrar_custo_gemini(
                operacao="chat_geracao",
                modelo=GEMINI_MODEL,
                tokens_entrada=entrada,
                tokens_saida=saida,
            )
            consumo.registrar(
                email, "agent-orchestrator", "chat_geracao", GEMINI_MODEL, entrada, saida
            )
        text_out = getattr(response, "text", None)
        if not text_out:
            return "Não consegui gerar uma resposta adequada com o modelo Gemini."
        return text_out
    except Exception as e:
        return (
            f"Houve um erro ao chamar o modelo Gemini. Detalhes técnicos: {type(e).__name__}: {e}"
        )


# --------------------------------------------------------------------
# Endpoint principal de chat
# --------------------------------------------------------------------


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    """
    Fluxo do agente MEI (RAG real):
    1. Busca resumo financeiro no serviço de limites.
    2. Gera o embedding da pergunta do usuário.
    3. Recupera por similaridade (pgvector) os trechos mais relevantes da base de
       conhecimento sobre regras do MEI e dos documentos do próprio usuário.
    4. Monta um prompt aumentado com esse contexto recuperado.
    5. Chama o modelo Gemini para gerar a resposta.
    """
    summary = get_limits_summary(req.email)
    retrato = traduzir_resumo_limits(summary)

    query_embedding = embed_text(req.message, email=req.email, operacao="embedding_pergunta")
    knowledge_hits = retrieve_knowledge(db, query_embedding, top_k=3) if query_embedding else []
    document_hits = (
        retrieve_document_chunks(db, req.email, query_embedding, top_k=3) if query_embedding else []
    )

    prompt = build_prompt(
        retrato=retrato,
        user_message=req.message,
        email=req.email,
        knowledge_hits=knowledge_hits,
        document_hits=document_hits,
    )

    reply_text = call_gemini(prompt, email=req.email)

    sources = [f"{k.title} ({k.source})" for k in knowledge_hits]
    sources += [f"Documento: {d.source_filename}" for d in document_hits if d.source_filename]

    logger.info(
        "chat.resposta_gerada",
        email=req.email,
        knowledge_hits=len(knowledge_hits),
        document_hits=len(document_hits),
        sources_count=len(sources),
    )

    return ChatResponse(reply=reply_text, sources=sources)
