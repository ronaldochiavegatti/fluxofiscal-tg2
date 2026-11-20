import contextlib
import hashlib
import os
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import structlog
from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import Body, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from google import genai
from pydantic import BaseModel, EmailStr, Field

from . import consumo, processamento
from .armazenamento import (
    BUCKET_PADRAO,
    VALIDADE_URL_SEGUNDOS,
    ArmazenamentoDeDocumentos,
    ArmazenamentoLocal,
    ArmazenamentoMinio,
    ArquivoAusente,
    criar_cliente_minio,
    garantir_bucket,
    hash_email,
)
from .auditoria import RepositorioAuditoria, RepositorioAuditoriaMongo
from .flags import esta_ativa, setup_flags, shutdown_flags
from .metrics import (
    documentos_processados_total,
    extracao_confianca,
    fotos_recusadas_total,
    registrar_custo_gemini,
)
from .observability import setup_metrics, setup_observability, setup_tracing

# `processamento.py` (US-18) é a base pura da extração — sem FastAPI, para o
# caminho síncrono e a tarefa Celery do worker rodarem o mesmo código. Vários
# nomes são re-exportados porque a suíte e o restante de main.py os referenciam.
from .processamento import (  # noqa: F401
    EXTRACTION_PROMPT,
    IMAGE_EXTS,
    IMAGE_MIME_TYPES,
    FalhaTransitoriaGemini,
    extract_amount_from_text,
    extract_cnpjs,
    extract_date,
    extract_description,
    normalize_cnpj,
    regex_extract,
    sanitize_gemini_result,
    score_confidence,
    suggest_tx_type,
    tipo_mime_de,
)
from .qualidade import DICAS, MENSAGENS, avaliar_foto
from .repositorio import (
    RepositorioDocumentos,
    RepositorioMongo,
    hash_do_arquivo,
    nova_repeticao,
    novo_documento,
    novo_documento_pendente,
)
from .tarefas import enfileirar_processamento
from .traducao import traduzir_para_limits

setup_observability()
logger = structlog.get_logger()

# O diretório é configurável para que a suíte de testes possa apontá-lo para
# um temporário. O padrão continua sendo o volume declarado no Compose, então
# nada muda em execução.
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/data/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

LIMITS_BASE_URL = os.getenv("LIMITS_BASE_URL", "http://limits:8000")
AGENT_BASE_URL = os.getenv("AGENT_BASE_URL", "http://agent:8000")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

MINIO_BUCKET = os.getenv("MINIO_BUCKET", BUCKET_PADRAO)

# Cliente MinIO criado sob demanda, na primeira gravação com a flag ligada.
# `_minio_bucket_pronto` garante que garantir_bucket() roda uma vez por processo.
_minio_cliente = None
_minio_bucket_pronto = False


def obter_armazenamento() -> ArmazenamentoDeDocumentos:
    """Escolhe o destino do arquivo pela flag `storage-minio` (ADR-0008).

    Padrão desligado = sistema de arquivos local, comportamento de sempre. A
    estratégia da flag é tudo-ou-nada, então não há contexto de usuário.
    """
    global _minio_cliente, _minio_bucket_pronto

    if not esta_ativa("storage-minio", padrao=False):
        return ArmazenamentoLocal(UPLOAD_DIR)

    if _minio_cliente is None:
        _minio_cliente = criar_cliente_minio()
    if not _minio_bucket_pronto:
        garantir_bucket(_minio_cliente, MINIO_BUCKET)
        _minio_bucket_pronto = True
    return ArmazenamentoMinio(_minio_cliente, MINIO_BUCKET)


MONGO_URL = os.getenv("MONGO_URL", "")
MONGO_DB = os.getenv("MONGO_DB", "fluxofiscal")

# US-18: segredo compartilhado com o worker para a rota interna de
# processamento. Vazio (padrão de dev) = rota aberta, como o resto deste
# serviço de demonstração (ADR-0011).
INTERNO_TOKEN = os.getenv("INTERNO_TOKEN", "")

if TYPE_CHECKING:
    from pymongo import MongoClient

# Anotado por string para não puxar `pymongo` na importação do módulo — só o
# tipo é resolvido, e só em tempo de checagem (`TYPE_CHECKING`); o cliente de
# verdade continua sendo importado tardiamente em `_colecao`, na primeira
# chamada que precisar dele.
_mongo_cliente: "MongoClient | None" = None
_repositorio: RepositorioDocumentos | None = None
_auditoria: RepositorioAuditoria | None = None


def _colecao(nome: str):
    global _mongo_cliente
    if _mongo_cliente is None:
        from pymongo import MongoClient

        _mongo_cliente = MongoClient(MONGO_URL)
    return _mongo_cliente[MONGO_DB][nome]


def obter_repositorio() -> RepositorioDocumentos | None:
    """Devolve o repositório de documentos quando a flag `documentos-persistidos`
    está ligada, ou `None` — e aí o Documents segue sem banco, como antes.

    Estratégia da flag: liberação percentual. Sem contexto de usuário aqui
    porque a decisão de persistir é do servidor; o rollout gradual acontece na
    camada que consome a lista no frontend.
    """
    global _repositorio

    if not esta_ativa("documentos-persistidos", padrao=False) or not MONGO_URL:
        return None

    if _repositorio is None:
        _repositorio = RepositorioMongo(_colecao("documentos"))
    return _repositorio


def obter_auditoria() -> RepositorioAuditoria | None:
    """Trilha de auditoria (US-22). Vive na mesma condição do repositório —
    sem Mongo não há onde registrar. `None` faz o registro virar no-op."""
    global _auditoria

    if obter_repositorio() is None:
        return None
    if _auditoria is None:
        _auditoria = RepositorioAuditoriaMongo(_colecao("auditoria"))
    return _auditoria


def _trace_id() -> str | None:
    from asgi_correlation_id import correlation_id

    return correlation_id.get()


def _auditar(acao: str, *, por: str, recurso_id: str, antes: dict | None, depois: dict) -> None:
    """Registra na trilha, se houver trilha. Nunca derruba o fluxo principal:
    a auditoria não pode ser o motivo de um upload falhar."""
    trilha = obter_auditoria()
    if trilha is None:
        return
    try:
        trilha.registrar(
            por=por,
            acao=acao,
            recurso_id=recurso_id,
            antes=antes,
            depois=depois,
            trace_id=_trace_id(),
        )
    except Exception:
        logger.warning("auditoria.falha_ao_registrar", acao=acao, recurso_id=recurso_id)


_CAMPOS_FISCAIS = ("value", "date", "cnpj_emitente", "cnpj_destinatario", "description")


def _snapshot_extracao(metodo: str, estruturado: dict) -> dict:
    """O que a extração produziu — o "antes" da correção humana."""
    return {
        "metodo": metodo,
        "confianca": estruturado.get("confidence"),
        "campos": {k: estruturado.get(k) for k in _CAMPOS_FISCAIS},
    }


def _resposta_do_documento(doc: dict, *, duplicado: bool) -> dict:
    """Monta a resposta de /upload a partir de um registro do Mongo — usada
    tanto no reenvio reconhecido quanto logo após persistir um novo."""
    campos = dict(doc["extracao"]["campos"])
    campos["confidence"] = doc["extracao"]["confianca"]
    return {
        "documento_id": doc["_id"],
        "duplicado": duplicado,
        "estado": doc["estado"],
        "original_filename": doc["arquivo"]["nome_original"],
        "stored_filename": doc["arquivo"]["chave_armazenamento"].rsplit("/", 1)[-1],
        "size_bytes": doc["arquivo"]["tamanho_bytes"],
        "armazenamento": "minio" if "/" in doc["arquivo"]["chave_armazenamento"] else "local",
        "chave_armazenamento": doc["arquivo"]["chave_armazenamento"],
        "ocr_text": doc["ocr"]["texto"],
        "extracted_amount": campos.get("value"),
        "extraction_method": doc["extracao"]["metodo"],
        "limits_transaction": None,
        "structured_data": campos,
    }


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    """Único propósito hoje: iniciar e encerrar o cliente de feature flags.

    O Documents não tem esquema de banco próprio (não guarda estado — quem
    persiste é o Limits), por isso nunca precisou de lifespan até a US-15.
    """
    setup_flags(app_name="documents")
    yield
    shutdown_flags()


app = FastAPI(title="Documents Service", lifespan=lifespan)

app.add_middleware(CorrelationIdMiddleware, header_name="X-Correlation-Id")

setup_metrics(app, service_name="documents")
setup_tracing(app, service_name="documents")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Espelha o limite da coluna `Numeric(10, 2)` do Limits. Sem isto, um valor
# fora de faixa só é recusado lá, e o usuário recebe um 502 opaco no lugar de
# um 422 que diz qual campo está errado.
VALOR_MAXIMO = 99_999_999.99


class LimitsTransaction(BaseModel):
    email: EmailStr
    amount: float = Field(gt=0, le=VALOR_MAXIMO)
    tx_date: date
    source: str | None = None
    tx_type: str = "venda"
    cnpj_cliente: str | None = None  # US-27


class ConfirmDocument(BaseModel):
    email: EmailStr
    amount: float = Field(gt=0, le=VALOR_MAXIMO)
    tx_date: date
    tx_type: str  # "venda" | "compra" - definido/confirmado pelo usuário na revisão
    cnpj_emitente: str | None = None
    cnpj_destinatario: str | None = None
    description: str | None = None
    source_filename: str | None = None
    ocr_text: str | None = None
    # US-22: liga a confirmação ao documento extraído, para a trilha registrar
    # "de R$ X extraído para R$ Y confirmado". Opcional — sem ele a trilha só
    # guarda o valor confirmado.
    documento_id: str | None = None


class CorrecaoDocumento(BaseModel):
    """Correção de uma nota já salva, feita no detalhe do documento (#95)."""

    amount: float = Field(gt=0, le=VALOR_MAXIMO)
    tx_date: date
    tx_type: str
    cnpj_emitente: str | None = None
    cnpj_destinatario: str | None = None
    description: str | None = None


@app.get("/health")
def health():
    return {"status": "ok", "service": "documents", "gemini_extraction": gemini_client is not None}


@app.delete("/reset")
def reset_uploads(email: EmailStr | None = None):
    """Apaga todos os arquivos enviados durante os testes.

    A pasta local é sempre limpa (sobra de quando a flag `storage-minio`
    estava desligada); com a flag ligada, o bucket do MinIO também.

    Com `email` e a flag `documentos-persistidos` ligada, apaga também os
    registros do histórico desse usuário no Mongo — senão a tela de Documentos
    seguia listando notas cujas transações o reset do Limits já removera. A
    trilha de auditoria não é tocada: é encadeada por hash e só cresce."""
    deleted = ArmazenamentoLocal(UPLOAD_DIR).apagar_tudo()
    armazenamento = obter_armazenamento()
    if not isinstance(armazenamento, ArmazenamentoLocal):
        deleted += armazenamento.apagar_tudo()
    resposta: dict[str, int] = {"files_deleted": deleted}
    if email is not None:
        repositorio = obter_repositorio()
        resposta["documentos_apagados"] = (
            repositorio.apagar_do_usuario(email) if repositorio is not None else 0
        )
    return resposta


# -------------------------------
#  EXTRAÇÃO — wrappers finos sobre processamento.py (US-18)
# -------------------------------
#
# O pipeline (OCR, Gemini, regex, sanitização) vive em `processamento.py`. Os
# wrappers abaixo fecham sobre o cliente Gemini de módulo e a métrica de custo,
# mantendo a assinatura que a suíte e o `/upload` já usavam.


def _parse_gemini_json(raw_text: str) -> dict | None:
    return processamento._parse_json(raw_text)


def gemini_extract_from_image_bytes(image_bytes: bytes, mime_type: str) -> dict | None:
    return processamento.gemini_de_imagem(
        gemini_client, GEMINI_MODEL, image_bytes, mime_type, registrar_custo_gemini
    )


def gemini_extract_from_text(text_value: str) -> dict | None:
    return processamento.gemini_de_texto(
        gemini_client, GEMINI_MODEL, text_value, registrar_custo_gemini
    )


def extract_text_from_file(path: Path, ext: str) -> str:
    return processamento.extrair_texto(path, ext)


def pdf_first_page_png_bytes(path: Path) -> bytes | None:
    return processamento.pdf_primeira_pagina_png(path)


# -------------------------------
#  INTEGRAÇÃO COM LIMITS E AGENT (RAG)
# -------------------------------


def send_to_limits(
    email: str,
    amount: float,
    source: str,
    tx_date: date | None = None,
    tx_type: str = "venda",
    cnpj_cliente: str | None = None,
):
    # US-46: a fronteira documents -> Limits passa pela camada de tradução. A
    # lista de campos é fechada lá — confiança, método e modelo da extração não
    # atravessam. `LimitsTransaction` ainda valida (valor > 0, teto, e-mail).
    dados = traduzir_para_limits(
        email=email,
        amount=amount,
        tx_date=tx_date,
        source=source,
        tx_type=tx_type,
        cnpj_cliente=cnpj_cliente,
    )
    payload = LimitsTransaction(**dados)
    resp = httpx.post(
        f"{LIMITS_BASE_URL}/transactions", json=payload.model_dump(mode="json"), timeout=5.0
    )
    if resp.status_code not in (200, 201):
        raise HTTPException(
            status_code=502,
            detail=f"Erro ao registrar transação no serviço de limites: {resp.text}",
        )
    return resp.json()


def atualizar_no_limits(tx_id: int, amount: float, tx_date: date, tx_type: str) -> dict:
    """Correção de uma transação já registrada (#95), pelo PATCH do Limits."""
    resp = httpx.patch(
        f"{LIMITS_BASE_URL}/transactions/{tx_id}",
        json={"amount": amount, "tx_date": tx_date.isoformat(), "tx_type": tx_type},
        timeout=5.0,
    )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Erro ao corrigir a transação no serviço de limites: {resp.text}",
        )
    return resp.json()


def apagar_no_limits(tx_id: int) -> bool:
    """Remove o lançamento da nota apagada (#96). 404 conta como já removido:
    o reset da demo, por exemplo, apaga as transações sem passar por aqui."""
    resp = httpx.delete(f"{LIMITS_BASE_URL}/transactions/{tx_id}", timeout=5.0)
    if resp.status_code == 404:
        return False
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Erro ao apagar a transação no serviço de limites: {resp.text}",
        )
    return True


def index_document_for_rag(email: str, source_filename: str | None, content: str) -> None:
    """Envia o texto do documento confirmado para o Agent Orchestrator indexar
    no RAG por usuário. Não bloqueia o fluxo de confirmação em caso de falha."""
    if not content or not content.strip():
        return
    # Dívida conhecida: a falha é engolida, e o documento confirmado nunca chega
    # ao RAG sem que nada registre a perda. A US-46 troca esta chamada direta
    # por publicação via Outbox, que é o que resolve de fato. Até lá, o
    # comportamento fica explícito aqui em vez de escondido num `except: pass`.
    with contextlib.suppress(httpx.RequestError):
        httpx.post(
            f"{AGENT_BASE_URL}/index-document",
            json={"email": email, "source_filename": source_filename, "content": content},
            timeout=15.0,
        )


# -------------------------------
#  ENDPOINT PRINCIPAL: UPLOAD
# -------------------------------
#
# Sem a flag `ocr-assincrono`: extrai na hora e devolve os campos (comportamento
def _recusa_por_qualidade(conteudo: bytes, email: str) -> JSONResponse | None:
    """Barra foto que não tem como ser lida, antes de gravar o arquivo e de
    chamar o Gemini (#100). Nada é persistido: o usuário tira outra foto."""
    avaliacao = avaliar_foto(conteudo)
    if avaliacao.legivel or avaliacao.motivo is None:
        return None
    fotos_recusadas_total.labels(motivo=avaliacao.motivo).inc()
    logger.info(
        "documento.foto_recusada",
        email=email,
        motivo=avaliacao.motivo,
        nitidez=avaliacao.nitidez,
        razao_nitidez=avaliacao.razao_nitidez,
        brilho=avaliacao.brilho,
        contraste=avaliacao.contraste,
    )
    return JSONResponse(
        status_code=422,
        content={
            "detail": {
                "codigo": "foto_ilegivel",
                "motivo": avaliacao.motivo,
                "mensagem": MENSAGENS[avaliacao.motivo],
                "dica": DICAS[avaliacao.motivo],
                "medidas": avaliacao.como_dict(),
            }
        },
    )


def _so_digitos(cnpj: str | None) -> str:
    return "".join(c for c in (cnpj or "") if c.isdigit())


def _resumo_repeticao(doc: dict, *, mesmo_arquivo: bool) -> dict:
    campos = (doc.get("confirmacao") or {}).get("campos") or {}
    return {
        "documento_id": doc["_id"],
        "nome_original": doc["arquivo"]["nome_original"],
        "mesmo_arquivo": mesmo_arquivo,
        "valor": campos.get("value"),
        "data": campos.get("date"),
        "tx_type": campos.get("tx_type"),
        "enviado_em": doc["criado_em"],
    }


def _repeticoes(
    repositorio: RepositorioDocumentos, doc: dict, campos: dict | None = None
) -> list[dict]:
    """Notas já salvas que parecem ser esta mesma (#93).

    Duas formas de repetir: o mesmo arquivo de novo (o hash já devolveu o
    registro antigo, e ele está confirmado) ou outra foto/PDF da mesma nota,
    reconhecida por valor, data e CNPJ do emitente. Só conta o que foi
    confirmado: um envio abandonado na conferência não entrou no faturamento,
    então reenviar não duplica nada. O usuário decide se segue — duas vendas
    iguais no mesmo dia existem.

    `campos` troca o que é comparado: na confirmação, vale o que o usuário
    confirmou (com correções), não o que a extração leu.
    """
    encontradas = []
    if doc.get("estado") == "confirmado":
        encontradas.append(_resumo_repeticao(doc, mesmo_arquivo=True))
    if campos is None:
        campos = doc["extracao"]["campos"]
    if campos.get("value") is None or not campos.get("date"):
        return encontradas
    cnpj = _so_digitos(campos.get("cnpj_emitente"))
    for outro in repositorio.confirmados_com_valor_e_data(
        doc["usuario_email"],
        valor=float(campos["value"]),
        data=str(campos["date"]),
        excluir_id=doc["_id"],
    ):
        cnpj_outro = _so_digitos(outro["confirmacao"]["campos"].get("cnpj_emitente"))
        # CNPJ ausente de um dos lados não descarta: a leitura pode ter falhado.
        if cnpj and cnpj_outro and cnpj != cnpj_outro:
            continue
        encontradas.append(
            _resumo_repeticao(outro, mesmo_arquivo=hash_do_arquivo(outro) == hash_do_arquivo(doc))
        )
    return encontradas


# de sempre). Com a flag e com `documentos-persistidos` ligada: grava o arquivo,
# cria o registro em "recebido", enfileira a tarefa Celery e responde 202 — o
# usuário não espera o OCR nem o Gemini (US-18).


def _registrador_de_custo(email: str | None):
    """Callback de custo da extração: alimenta a métrica do Prometheus, como
    antes, e o registro de consumo no billing (ADR-0024, por flag)."""

    def registrar(operacao: str, modelo: str, tokens_entrada: int, tokens_saida: int) -> None:
        registrar_custo_gemini(
            operacao=operacao,
            modelo=modelo,
            tokens_entrada=tokens_entrada,
            tokens_saida=tokens_saida,
        )
        consumo.registrar(email, "documents", operacao, modelo, tokens_entrada, tokens_saida)

    return registrar


def _extrair_do_arquivo(
    contents: bytes, ext: str, caminho, user_cnpj: str | None, email: str | None = None
) -> tuple[str, dict, str]:
    """Roda o pipeline de extração. Devolve (ocr_text, structured, metodo).

    Encapsula o que o `/upload` síncrono e a rota interna de processamento
    (chamada pelo worker) precisam em comum.
    """
    extr = processamento.processar_arquivo(
        contents,
        ext,
        caminho=caminho,
        gemini_cliente=gemini_client,
        gemini_modelo=GEMINI_MODEL,
        user_cnpj=user_cnpj,
        ao_registrar_custo=_registrador_de_custo(email),
    )
    documentos_processados_total.labels(metodo=extr.metodo, formato=ext).inc()
    extracao_confianca.labels(metodo=extr.metodo).observe(extr.estruturado["confidence"])
    return extr.ocr_texto, extr.estruturado, extr.metodo


@app.post(
    "/upload",
    responses={
        202: {"description": "Aceito para processamento assíncrono (flag ocr-assincrono)"},
        400: {"description": "Arquivo sem nome"},
        422: {"description": "Foto sem qualidade para leitura (codigo foto_ilegivel)"},
    },
)
async def upload_document(
    file: UploadFile = File(...),
    email: EmailStr = Form(...),
    user_cnpj: str | None = Form(None),
    # #100: o usuário viu o aviso de foto ruim e pediu para ler mesmo assim.
    forcar_leitura: bool = Form(False),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    ext = os.path.splitext(file.filename)[1].lower()
    new_name = f"{uuid.uuid4()}{ext}"
    # Cópia local temporária: o OCR e a conversão de PDF trabalham sobre um
    # caminho de arquivo. Com a flag `storage-minio` ligada, ela é removida no
    # fim; o arquivo canônico passa a ser o objeto no MinIO.
    dest_path = UPLOAD_DIR / new_name

    contents = await file.read()
    hash_sha256 = hashlib.sha256(contents).hexdigest()

    # US-20: reenvio reconhecido. A checagem vem ANTES do OCR e do Gemini —
    # arquivo já visto não é reprocessado nem cobrado de novo.
    repositorio = obter_repositorio()
    if repositorio is not None:
        ja_visto = repositorio.por_hash(email, hash_sha256)
        if ja_visto is not None:
            logger.info("documento.duplicado", email=email, documento_id=ja_visto["_id"])
            return _resposta_do_documento(ja_visto, duplicado=True) | {
                "repeticoes": _repeticoes(repositorio, ja_visto)
            }

    if ext in IMAGE_EXTS and not forcar_leitura:
        recusa = await run_in_threadpool(_recusa_por_qualidade, contents, email)
        if recusa is not None:
            return recusa

    dest_path.write_bytes(contents)

    tipo_mime = tipo_mime_de(ext)

    # US-19: persiste o arquivo no destino escolhido pela flag `storage-minio`.
    armazenamento = obter_armazenamento()
    chave = armazenamento.chave(email, new_name, datetime.now(UTC).date())
    armazenamento.salvar(chave, contents, tipo_mime)

    # US-18: caminho assíncrono. Precisa do repositório (o worker acompanha o
    # documento pelo _id) e da flag `ocr-assincrono`. Grava "recebido",
    # enfileira e responde 202 sem rodar OCR nem Gemini.
    if repositorio is not None and esta_ativa(
        "ocr-assincrono", padrao=False, contexto={"userId": email}
    ):
        montado = novo_documento_pendente(
            email=email,
            nome_original=file.filename,
            chave_armazenamento=chave,
            tamanho_bytes=len(contents),
            tipo_mime=tipo_mime,
            hash_sha256=hash_sha256,
            user_cnpj=user_cnpj,
        )
        doc = repositorio.salvar(montado)
        if doc["_id"] != montado["_id"]:
            # corrida: outro upload igual chegou primeiro
            return _resposta_do_documento(doc, duplicado=True)
        if armazenamento.nome == "minio":
            dest_path.unlink(missing_ok=True)
        try:
            task_id = enfileirar_processamento(
                doc["_id"], chave_armazenamento=chave, ext=ext, user_cnpj=user_cnpj
            )
        except Exception:
            logger.warning("documento.enfileiramento_falhou", documento_id=doc["_id"])
            repositorio.marcar_erro(
                doc["_id"], motivo="não foi possível enfileirar o processamento", permanente=False
            )
            raise HTTPException(
                status_code=503, detail="Fila indisponível, tente novamente"
            ) from None
        logger.info("documento.enfileirado", documento_id=doc["_id"], task_id=task_id)
        return JSONResponse(
            status_code=202,
            content={
                "documento_id": doc["_id"],
                "estado": "recebido",
                "duplicado": False,
                "acompanhamento_url": f"/documents/documentos/{doc['_id']}",
                "original_filename": file.filename,
                "size_bytes": len(contents),
                "chave_armazenamento": chave,
                "armazenamento": armazenamento.nome,
            },
        )

    # OCR + Gemini são bloqueantes e levam segundos; numa rota `async` eles
    # congelariam o event loop inteiro (até o /health). Vão para o threadpool.
    ocr_text, structured, extraction_method = await run_in_threadpool(
        _extrair_do_arquivo, contents, ext, dest_path, user_cnpj, email
    )
    if armazenamento.nome == "minio":
        # O objeto no MinIO é a fonte da verdade; a cópia local era só para o OCR.
        dest_path.unlink(missing_ok=True)

    logger.info(
        "documento.upload",
        email=email,
        filename=file.filename,
        size_bytes=len(contents),
        extraction_method=extraction_method,
        confidence=structured.get("confidence"),
        armazenamento=armazenamento.nome,
    )

    resposta = {
        "original_filename": file.filename,
        "stored_filename": new_name,
        "size_bytes": len(contents),
        "storage_path": str(dest_path),
        "armazenamento": armazenamento.nome,
        "chave_armazenamento": chave,
        "ocr_text": ocr_text,
        "extracted_amount": structured.get("value"),
        "extraction_method": extraction_method,
        "limits_transaction": None,
        "structured_data": structured,
    }

    # US-20: persiste o documento. A resposta ganha `documento_id`, `estado` e
    # `duplicado`. Sem a flag, `repositorio` é None e nada muda.
    if repositorio is not None:
        montado = novo_documento(
            email=email,
            nome_original=file.filename,
            chave_armazenamento=chave,
            tamanho_bytes=len(contents),
            tipo_mime=tipo_mime,
            hash_sha256=hash_sha256,
            ocr_texto=ocr_text,
            ocr_motor="tesseract",
            extracao_metodo=extraction_method,
            extracao_modelo=GEMINI_MODEL if extraction_method == "gemini" else None,
            campos={
                k: structured.get(k)
                for k in ("value", "date", "cnpj_emitente", "cnpj_destinatario", "description")
            },
            confianca=structured["confidence"],
        )
        doc = repositorio.salvar(montado)
        resposta["documento_id"] = doc["_id"]
        resposta["estado"] = doc["estado"]
        # `salvar` devolve um doc pré-existente quando o índice único barra uma
        # corrida — nesse caso o _id não é o que acabamos de gerar.
        resposta["duplicado"] = doc["_id"] != montado["_id"]
        repeticoes = _repeticoes(repositorio, doc)
        resposta["repeticoes"] = repeticoes
        if repeticoes:
            logger.info(
                "documento.repeticao_detectada",
                email=email,
                documento_id=doc["_id"],
                quantidade=len(repeticoes),
            )
        if not resposta["duplicado"]:
            _auditar(
                "documento.extraido",
                por=email,
                recurso_id=doc["_id"],
                antes=None,
                depois=_snapshot_extracao(extraction_method, structured),
            )

    # Nada é gravado no Limits ainda: o usuário revisa e confirma os campos
    # extraídos (ver POST /confirm) antes de a transação ser persistida.
    return resposta


# -------------------------------
#  PROCESSAMENTO ASSÍNCRONO (US-18) — chamado pela tarefa Celery do worker
# -------------------------------


def _conferir_token_interno(token: str | None) -> None:
    if INTERNO_TOKEN and token != INTERNO_TOKEN:
        raise HTTPException(status_code=401, detail="token interno inválido")


def _reenfileirar(doc: dict) -> str:
    chave = doc["arquivo"]["chave_armazenamento"]
    return enfileirar_processamento(
        doc["_id"], chave_armazenamento=chave, ext=Path(chave).suffix.lower(), user_cnpj=None
    )


@app.post(
    "/_interno/processar/{documento_id}",
    include_in_schema=False,
    responses={
        404: {"description": "Documento não encontrado"},
        409: {"description": "Persistência de documentos desligada"},
        422: {"description": "Falha permanente — documento marcado como erro"},
        503: {"description": "Falha transitória — a tarefa deve tentar de novo"},
    },
)
def processar_documento_interno(
    documento_id: str,
    user_cnpj: str | None = Body(default=None, embed=True),
    ultima_tentativa: bool = False,
    x_interno_token: str | None = Header(default=None),
):
    """Roda a extração de um documento já recebido. Idempotente: um documento
    já `extraido` ou `confirmado` volta o estado atual sem reprocessar."""
    _conferir_token_interno(x_interno_token)

    repositorio = obter_repositorio()
    if repositorio is None:
        raise HTTPException(status_code=409, detail="documentos-persistidos desligada")

    doc = repositorio.por_id(documento_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    if doc["estado"] in ("extraido", "confirmado", "descartado"):
        return {"documento_id": documento_id, "estado": doc["estado"]}

    repositorio.marcar_processando(documento_id)
    chave = doc["arquivo"]["chave_armazenamento"]
    ext = Path(chave).suffix.lower()

    try:
        conteudo = obter_armazenamento().ler(chave)
    except ArquivoAusente:
        repositorio.marcar_erro(
            documento_id, motivo="arquivo não encontrado no armazenamento", permanente=True
        )
        raise HTTPException(status_code=422, detail="arquivo ausente") from None

    caminho = UPLOAD_DIR / f"proc-{documento_id}{ext}"
    caminho.write_bytes(conteudo)
    try:
        extr = processamento.processar_arquivo(
            conteudo,
            ext,
            caminho=caminho,
            gemini_cliente=gemini_client,
            gemini_modelo=GEMINI_MODEL,
            user_cnpj=user_cnpj or doc.get("usuario_cnpj"),
            ao_registrar_custo=_registrador_de_custo(doc.get("usuario_email")),
            propagar_falha_transitoria=True,
        )
    except FalhaTransitoriaGemini as erro:
        if ultima_tentativa:
            repositorio.marcar_erro(
                documento_id, motivo=f"Gemini indisponível: {erro}", permanente=False
            )
            return {"documento_id": documento_id, "estado": "erro", "permanente": False}
        raise HTTPException(status_code=503, detail="falha transitória no Gemini") from erro
    except Exception as erro:  # arquivo corrompido, formato inesperado
        repositorio.marcar_erro(documento_id, motivo=str(erro)[:200], permanente=True)
        raise HTTPException(status_code=422, detail="falha permanente no processamento") from erro
    finally:
        caminho.unlink(missing_ok=True)

    documentos_processados_total.labels(metodo=extr.metodo, formato=ext).inc()
    extracao_confianca.labels(metodo=extr.metodo).observe(extr.estruturado["confidence"])

    campos = {
        k: extr.estruturado.get(k)
        for k in ("value", "date", "cnpj_emitente", "cnpj_destinatario", "description")
    }
    atualizado = repositorio.concluir_extracao(
        documento_id,
        ocr_texto=extr.ocr_texto,
        ocr_motor="tesseract",
        metodo=extr.metodo,
        modelo=GEMINI_MODEL if extr.metodo == "gemini" else None,
        campos=campos,
        confianca=extr.estruturado["confidence"],
    )
    if atualizado is None:
        # Corrida rara: o documento sumiu entre `marcar_processando` (início
        # desta função) e agora — mesmo 404 do guard de `doc` acima. Sem esta
        # checagem, `atualizado["estado"]` adiante quebraria com um
        # `TypeError` não tratado (500) em vez do 404 já declarado no
        # contrato desta rota. Encontrado pelo mypy (`dict | None`).
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    _auditar(
        "documento.extraido",
        por=doc["usuario_email"],
        recurso_id=documento_id,
        antes=None,
        depois=_snapshot_extracao(extr.metodo, extr.estruturado),
    )
    logger.info("documento.processado", documento_id=documento_id, metodo=extr.metodo)
    return {"documento_id": documento_id, "estado": atualizado["estado"], "metodo": extr.metodo}


@app.post(
    "/documentos/{documento_id}/reprocessar",
    responses={
        404: {"description": "Documento não encontrado"},
        409: {"description": "Persistência de documentos desligada, ou documento fora de 'erro'"},
    },
)
def reprocessar_documento(documento_id: str):
    """Recoloca na fila um documento que ficou em `erro` (US-18, "tentar de novo")."""
    repositorio = obter_repositorio()
    if repositorio is None:
        raise HTTPException(status_code=409, detail="documentos-persistidos desligada")

    doc = repositorio.por_id(documento_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    if doc["estado"] != "erro":
        raise HTTPException(
            status_code=409, detail=f"documento está em '{doc['estado']}', não 'erro'"
        )

    repositorio.marcar_processando(documento_id)
    try:
        task_id = _reenfileirar(doc)
    except Exception:
        repositorio.marcar_erro(documento_id, motivo="fila indisponível", permanente=False)
        raise HTTPException(status_code=503, detail="Fila indisponível, tente novamente") from None
    return {"documento_id": documento_id, "estado": "processando", "task_id": task_id}


def _chave_valida(chave: str) -> bool:
    """Rejeita chave vazia, com byte nulo ou com `..` — antes de virar Path."""
    return bool(chave) and "\x00" not in chave and ".." not in chave.split("/")


@app.get(
    "/url",
    responses={
        403: {"description": "A chave não pertence a este e-mail"},
        404: {"description": "Arquivo não encontrado"},
    },
)
def url_do_arquivo(chave: str, email: EmailStr):
    """URL temporária para baixar um documento já enviado (US-19).

    Com `storage-minio` ligada, devolve uma URL pré-assinada de 15 minutos, e o
    arquivo não trafega por este serviço — o cliente baixa direto do MinIO.
    """
    if not _chave_valida(chave):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    armazenamento = obter_armazenamento()

    # Checagem de posse possível sem banco (US-20 formaliza): a chave do MinIO
    # começa com o hash do e-mail do dono.
    if armazenamento.nome == "minio" and not chave.startswith(f"{hash_email(email)}/"):
        raise HTTPException(status_code=403, detail="A chave não pertence a este e-mail")

    if not armazenamento.existe(chave):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    return {
        "url": armazenamento.url_temporaria(chave),
        "expira_em_segundos": VALIDADE_URL_SEGUNDOS,
    }


@app.get(
    "/arquivos/{chave:path}",
    response_class=FileResponse,
    responses={
        200: {"content": {"application/octet-stream": {}}, "description": "O arquivo"},
        404: {"description": "Arquivo não encontrado"},
    },
)
def baixar_arquivo_local(chave: str):
    """Serve o arquivo do disco — só faz sentido no modo local (flag desligada).
    No modo MinIO a URL de `/url` já aponta direto para o objeto."""
    raiz = UPLOAD_DIR.resolve()
    try:
        if not _chave_valida(chave):
            raise ValueError
        caminho = (UPLOAD_DIR / chave).resolve()
        if not caminho.is_relative_to(raiz) or not caminho.is_file():
            raise ValueError
    except (ValueError, OSError):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado") from None
    return FileResponse(caminho, media_type="application/octet-stream")


def _resumo_do_documento(doc: dict) -> dict:
    """Item da lista — sem o texto de OCR, que pode ser grande."""
    return {
        "id": doc["_id"],
        "nome_original": doc["arquivo"]["nome_original"],
        "tamanho_bytes": doc["arquivo"]["tamanho_bytes"],
        "tipo_mime": doc["arquivo"]["tipo_mime"],
        "estado": doc["estado"],
        "erro": doc.get("erro"),
        "extracao": {
            "metodo": doc["extracao"]["metodo"],
            "campos": doc["extracao"]["campos"],
            "confianca": doc["extracao"]["confianca"],
        },
        # O que o usuário confirmou (com correções), quando já confirmou.
        "confirmacao": doc.get("confirmacao"),
        # Notas já salvas que o aviso de repetição apontou (#93).
        "repeticao_de": doc.get("repeticao_de") or [],
        "criado_em": doc["criado_em"],
    }


@app.get(
    "/documentos",
    responses={409: {"description": "Persistência de documentos desligada"}},
)
def listar_documentos(email: EmailStr):
    """Histórico de documentos do usuário (US-20). Sobrevive à troca de
    dispositivo porque vive no MongoDB, não no navegador."""
    repositorio = obter_repositorio()
    if repositorio is None:
        raise HTTPException(
            status_code=409,
            detail="A flag documentos-persistidos está desligada neste ambiente",
        )
    return [_resumo_do_documento(d) for d in repositorio.listar(email)]


@app.get(
    "/documentos/{documento_id}",
    responses={
        404: {"description": "Documento não encontrado"},
        409: {"description": "Persistência de documentos desligada"},
    },
)
def obter_documento(documento_id: str):
    repositorio = obter_repositorio()
    if repositorio is None:
        raise HTTPException(status_code=409, detail="A flag documentos-persistidos está desligada")

    doc = repositorio.por_id(documento_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return _detalhe_do_documento(repositorio, doc)


def _detalhe_do_documento(repositorio: RepositorioDocumentos, doc: dict) -> dict:
    return _resposta_do_documento(doc, duplicado=False) | {
        "criado_em": doc["criado_em"],
        "atualizado_em": doc["atualizado_em"],
        "historico": doc["historico"],
        "erro": doc.get("erro"),
        "repeticoes": _repeticoes(repositorio, doc),
        # O detalhe mostra e edita o que foi salvo, não só o que foi lido (#95).
        "confirmacao": doc.get("confirmacao"),
        "repeticao_de": doc.get("repeticao_de") or [],
    }


@app.patch(
    "/documentos/{documento_id}",
    responses={
        400: {"description": "tx_type fora de 'venda' | 'compra'"},
        404: {"description": "Documento não encontrado"},
        409: {"description": "Persistência desligada ou nota ainda não salva"},
        502: {"description": "O serviço de limites recusou a correção"},
    },
)
def corrigir_documento(documento_id: str, payload: CorrecaoDocumento):
    """Corrige uma nota já salva (#95): atualiza a transação no Limits e os
    campos confirmados no Mongo, e registra a correção na trilha.

    Nota só lida (estado "extraido") não passa por aqui: ela ainda não tem
    transação, e salvar pela primeira vez é o POST /confirm.
    """
    repositorio = obter_repositorio()
    if repositorio is None:
        raise HTTPException(status_code=409, detail="A flag documentos-persistidos está desligada")
    doc = repositorio.por_id(documento_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    if doc["estado"] != "confirmado":
        raise HTTPException(
            status_code=409, detail="A nota ainda não foi salva; confirme os dados primeiro"
        )
    if payload.tx_type not in ("venda", "compra"):
        raise HTTPException(
            status_code=400,
            detail=f"tx_type inválido: {payload.tx_type!r}. Use 'venda' ou 'compra'.",
        )

    confirmacao = doc.get("confirmacao") or {}
    tx_id = confirmacao.get("transacao_limits_id")
    # Limits primeiro: se ele recusar, o Mongo não fica dizendo um valor que o
    # faturamento não tem.
    if tx_id:
        atualizar_no_limits(tx_id, payload.amount, payload.tx_date, payload.tx_type)

    campos = {
        "value": payload.amount,
        "date": payload.tx_date.isoformat(),
        "cnpj_emitente": payload.cnpj_emitente,
        "cnpj_destinatario": payload.cnpj_destinatario,
        "description": payload.description,
        "tx_type": payload.tx_type,
    }
    antes = confirmacao.get("campos") or {}
    atualizado = repositorio.corrigir_confirmacao(documento_id, campos=campos) or doc
    _auditar(
        "documento.corrigido",
        por=doc["usuario_email"],
        recurso_id=documento_id,
        antes={
            "metodo": doc["extracao"]["metodo"],
            "confianca": doc["extracao"]["confianca"],
            "campos": {k: antes.get(k) for k in _CAMPOS_FISCAIS},
        },
        depois={**campos, "transacao_limits_id": tx_id},
    )
    logger.info("documento.corrigido", email=doc["usuario_email"], documento_id=documento_id)
    return _detalhe_do_documento(repositorio, atualizado)


@app.delete(
    "/documentos/{documento_id}",
    responses={
        404: {"description": "Documento não encontrado"},
        409: {"description": "Persistência de documentos desligada"},
        502: {"description": "O serviço de limites recusou apagar o lançamento"},
    },
)
def apagar_documento(documento_id: str):
    """Apaga a nota (#96): o lançamento no Limits, o registro e o arquivo.

    Limits primeiro — se ele recusar, nada é apagado e o usuário tenta de novo,
    em vez de ficar com um faturamento que nenhuma nota explica. O arquivo só
    sai se nenhum outro registro (repetição do mesmo arquivo) usa a chave.
    A trilha de auditoria fica: ela é imutável por desenho (ADR-0017).
    """
    repositorio = obter_repositorio()
    if repositorio is None:
        raise HTTPException(status_code=409, detail="A flag documentos-persistidos está desligada")
    doc = repositorio.por_id(documento_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    confirmacao = doc.get("confirmacao") or {}
    tx_id = confirmacao.get("transacao_limits_id")
    transacao_removida = apagar_no_limits(tx_id) if tx_id else False

    repositorio.apagar(documento_id)
    chave = doc["arquivo"]["chave_armazenamento"]
    arquivo_removido = False
    if repositorio.usam_o_arquivo(chave) == 0:
        try:
            obter_armazenamento().apagar(chave)
            arquivo_removido = True
        except Exception:
            logger.warning("documento.arquivo_nao_apagado", documento_id=documento_id)

    campos = confirmacao.get("campos") or doc["extracao"]["campos"]
    _auditar(
        "documento.apagado",
        por=doc["usuario_email"],
        recurso_id=documento_id,
        antes={
            "metodo": doc["extracao"]["metodo"],
            "confianca": doc["extracao"]["confianca"],
            "campos": {k: campos.get(k) for k in _CAMPOS_FISCAIS},
        },
        depois={"transacao_limits_id": tx_id, "transacao_removida": transacao_removida},
    )
    logger.info(
        "documento.apagado",
        email=doc["usuario_email"],
        documento_id=documento_id,
        transacao_removida=transacao_removida,
        arquivo_removido=arquivo_removido,
    )
    return {
        "documento_id": documento_id,
        "transacao_removida": transacao_removida,
        "arquivo_removido": arquivo_removido,
    }


# -------------------------------
#  TRILHA DE AUDITORIA (US-22, ADR-0005/0017)
# -------------------------------


def _trilha_ou_409() -> RepositorioAuditoria:
    trilha = obter_auditoria()
    if trilha is None:
        raise HTTPException(
            status_code=409, detail="Trilha de auditoria indisponível (documentos-persistidos)"
        )
    return trilha


@app.get(
    "/documentos/{documento_id}/auditoria",
    responses={409: {"description": "Trilha de auditoria indisponível"}},
)
def auditoria_do_documento(documento_id: str):
    """ "De onde veio este número": a trilha de um documento, do valor extraído
    até a correção humana."""
    return {
        "documento_id": documento_id,
        "registros": _trilha_ou_409().por_recurso(documento_id),
    }


@app.get(
    "/auditoria",
    responses={409: {"description": "Trilha de auditoria indisponível"}},
)
def listar_auditoria(email: EmailStr):
    return _trilha_ou_409().listar(email)


@app.get(
    "/auditoria/integridade",
    responses={409: {"description": "Trilha de auditoria indisponível"}},
)
def integridade_da_trilha(documento_id: str | None = None):
    """Recalcula a cadeia de hash. `integra: false` significa que algum
    registro foi alterado ou removido fora do fluxo de escrita."""
    return {"integra": _trilha_ou_409().verificar_integridade(documento_id)}


@app.api_route(
    "/auditoria/{registro_id}",
    methods=["PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
def auditoria_e_imutavel(registro_id: str):
    """A trilha é apenas de escrita (ADR-0005). Qualquer tentativa de alterar
    ou remover um registro é recusada — não existe caminho para isso."""
    raise HTTPException(
        status_code=405, detail="A trilha de auditoria é imutável: só escrita e leitura."
    )


@app.post(
    "/confirm",
    responses={
        400: {"description": "tx_type fora de 'venda' | 'compra'"},
        502: {"description": "O serviço de limites recusou o registro"},
    },
)
def confirm_document(payload: ConfirmDocument):
    """
    Confirma (com possíveis correções manuais) os dados extraídos, incluindo o
    tipo de operação (venda ou compra) escolhido/confirmado pelo usuário, e só
    então registra a transação no serviço de Limits. Também indexa o texto do
    documento no RAG do Agent Orchestrator, para consultas futuras do agente.
    """
    if payload.tx_type not in ("venda", "compra"):
        raise HTTPException(
            status_code=400,
            detail=f"tx_type inválido: {payload.tx_type!r}. Use 'venda' ou 'compra'.",
        )

    tx_type_label = "venda" if payload.tx_type == "venda" else "compra"
    limits_tx = send_to_limits(
        email=payload.email,
        amount=payload.amount,
        source=f"upload:{payload.source_filename}" if payload.source_filename else "upload",
        tx_date=payload.tx_date,
        tx_type=payload.tx_type,
        # US-27: numa venda, quem recebeu (destinatário) é o cliente — o
        # emitente é o próprio MEI. Ver `documents/processamento.py`, onde
        # "usuário é emitente -> venda" já fixa essa direção.
        cnpj_cliente=payload.cnpj_destinatario if payload.tx_type == "venda" else None,
    )

    rag_content = payload.ocr_text or payload.description or ""
    if payload.description:
        rag_content = f"Tipo: {tx_type_label}. {payload.description}\n\n{rag_content}"
    index_document_for_rag(payload.email, payload.source_filename, rag_content)

    confirmado = {
        "value": payload.amount,
        "date": payload.tx_date.isoformat(),
        "cnpj_emitente": payload.cnpj_emitente,
        "cnpj_destinatario": payload.cnpj_destinatario,
        "description": payload.description,
        "tx_type": payload.tx_type,
    }

    # US-22: trilha da correção humana. `antes` = o que a extração produziu
    # (buscado no documento, se o id veio junto); `depois` = o que o usuário
    # confirmou, mais o id da transação criada no Limits.
    _auditar_confirmacao(payload, confirmado, limits_tx)

    # Depois da auditoria, que lê a extração original como "antes". Sem esta
    # transição o documento ficava em "extraido" para sempre, e o histórico
    # não distinguia nota confirmada de nota abandonada no meio do fluxo.
    repositorio = obter_repositorio()
    documento_id = payload.documento_id
    if repositorio is not None and payload.documento_id:
        documento_id = _registrar_confirmacao(
            repositorio, payload.documento_id, confirmado, (limits_tx or {}).get("id")
        )

    logger.info(
        "documento.confirmado",
        email=payload.email,
        amount=payload.amount,
        tx_type=payload.tx_type,
        source_filename=payload.source_filename,
    )

    return {
        "limits_transaction": limits_tx,
        "structured_data": confirmado,
        "documento_id": documento_id,
    }


def _registrar_confirmacao(
    repositorio: RepositorioDocumentos,
    documento_id: str,
    confirmado: dict,
    transacao_limits_id: int | None,
) -> str:
    """Marca o documento como confirmado e devolve o id do registro usado.

    Se o usuário passou pelo aviso de repetição (#93), o registro guarda de
    quais notas ele é repetição. Arquivo idêntico a um já confirmado ganha
    registro novo (`nova_repeticao`): sobrescrever o antigo apagaria do
    histórico a primeira venda, que continua no faturamento.
    """
    doc = repositorio.por_id(documento_id)
    if doc is None:
        return documento_id
    repete = [r["documento_id"] for r in _repeticoes(repositorio, doc, confirmado)]
    if doc["estado"] == "confirmado":
        doc = repositorio.salvar(nova_repeticao(doc))
    repositorio.marcar_confirmado(
        doc["_id"],
        campos=confirmado,
        transacao_limits_id=transacao_limits_id,
        repeticao_de=repete,
    )
    if repete:
        logger.info("documento.repeticao_confirmada", documento_id=doc["_id"], de=repete)
    return str(doc["_id"])


def _auditar_confirmacao(
    payload: ConfirmDocument, confirmado: dict, limits_tx: dict | None
) -> None:
    repositorio = obter_repositorio()
    recurso_id = payload.documento_id
    antes = None
    if repositorio is not None and payload.documento_id:
        doc = repositorio.por_id(payload.documento_id)
        if doc is not None:
            antes = _snapshot_extracao(doc["extracao"]["metodo"], _campos_como_estruturado(doc))
    _auditar(
        "documento.confirmado",
        por=payload.email,
        recurso_id=recurso_id or f"upload:{payload.source_filename or 'sem-arquivo'}",
        antes=antes,
        depois={
            **confirmado,
            "transacao_limits_id": (limits_tx or {}).get("id"),
        },
    )


def _campos_como_estruturado(doc: dict) -> dict:
    campos = dict(doc["extracao"]["campos"])
    campos["confidence"] = doc["extracao"]["confianca"]
    return campos
