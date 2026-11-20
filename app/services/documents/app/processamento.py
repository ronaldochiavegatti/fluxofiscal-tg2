"""Pipeline de extração de nota fiscal — OCR, Gemini e fallback por regex (US-18).

Módulo **puro**: sem FastAPI, sem cliente Gemini de módulo, sem métricas
acopladas. É o mesmo código que roda no `documents` (caminho síncrono) e no
`worker` (tarefa Celery), copiado entre os dois como `observability.py` e
`flags.py` — mudança aqui = aplicar nos dois.

A diferença entre os dois usos é uma só: no `worker`, uma falha transitória do
Gemini (429, 503, timeout) precisa **propagar** para a tarefa reagendar; no
`documents`, ela é engolida e a extração cai no regex, que é degradação
aceitável numa tela de upload. `processar_arquivo(..., propagar_falha_transitoria=)`
controla isso.
"""

from __future__ import annotations

import io
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .traducao import traduzir_valor_monetario

# -------------------------------------------------------------------
#  Formatos
# -------------------------------------------------------------------

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


def tipo_mime_de(ext: str) -> str:
    return IMAGE_MIME_TYPES.get(ext, "application/pdf" if ext == ".pdf" else "text/plain")


class FalhaTransitoriaGemini(Exception):
    """Erro do Gemini que vale a pena tentar de novo: 429, 503, timeout."""


def _e_transitoria(exc: Exception) -> bool:
    codigo = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if codigo in (408, 429, 500, 502, 503, 504):
        return True
    texto = str(exc).lower()
    marcas = ("429", "resource_exhausted", "rate limit", "timeout", "unavailable", "503", "500")
    return any(m in texto for m in marcas)


# -------------------------------------------------------------------
#  OCR (Tesseract) — texto de apoio, auditoria e fallback
# -------------------------------------------------------------------


# Teto do Tesseract por documento. Sem ele, um OCR lento (CPU disputada no
# Docker) segura o upload para sempre. Estourou: pytesseract mata o processo e
# levanta RuntimeError, `extrair_texto` devolve "" e o Gemini segue sozinho.
OCR_TIMEOUT_SEGUNDOS = int(os.getenv("OCR_TIMEOUT_SEGUNDOS", "60"))

# O Tesseract usa OpenMP com uma thread por núcleo; com a CPU do Docker
# disputada pelos outros serviços, isso degrada o OCR de segundos para minutos.
# Uma thread só é a recomendação do próprio Tesseract para rodar em contêiner.
# O subprocesso do pytesseract herda este ambiente.
os.environ.setdefault("OMP_THREAD_LIMIT", "1")


def ocr_de_imagem(caminho: Path) -> str:
    import pytesseract
    from PIL import Image

    with Image.open(caminho) as imagem:
        return pytesseract.image_to_string(imagem, lang="por", timeout=OCR_TIMEOUT_SEGUNDOS)


def ocr_de_pdf_primeira_pagina(caminho: Path) -> str:
    import pytesseract
    from pdf2image import convert_from_path

    paginas = convert_from_path(str(caminho), first_page=1, last_page=1)
    if not paginas:
        return ""
    return pytesseract.image_to_string(paginas[0], lang="por", timeout=OCR_TIMEOUT_SEGUNDOS)


def pdf_primeira_pagina_png(caminho: Path) -> bytes | None:
    try:
        from pdf2image import convert_from_path

        paginas = convert_from_path(str(caminho), first_page=1, last_page=1)
    except Exception:
        # PDF truncado, extensão errada ou poppler ausente. None faz a extração
        # cair no regex — degradação, não erro 500.
        return None
    if not paginas:
        return None
    buf = io.BytesIO()
    paginas[0].save(buf, format="PNG")
    return buf.getvalue()


def extrair_texto(caminho: Path, ext: str) -> str:
    """Texto bruto do arquivo. Nunca levanta: foto ruim é entrada esperada."""
    try:
        if ext in IMAGE_EXTS:
            return ocr_de_imagem(caminho)
        if ext == ".pdf":
            return ocr_de_pdf_primeira_pagina(caminho)
        return caminho.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


# -------------------------------------------------------------------
#  Extração estruturada via Gemini (multimodal) — método principal
# -------------------------------------------------------------------

EXTRACTION_PROMPT = """Você é um extrator de dados de notas fiscais e recibos brasileiros \
(incluindo fotos tiradas por celular, com iluminação e ângulo imperfeitos).

Analise o documento fornecido e extraia exatamente estes campos:
- amount: o valor TOTAL da nota/recibo (o valor final a pagar), como número decimal \
(ex.: 1234.56). Se houver vários valores (subtotal, desconto, total), use o total. Se não \
encontrar nenhum valor, use null.
- date: a data de emissão do documento, no formato AAAA-MM-DD. Se não encontrar, use null.
- cnpj_emitente: o CNPJ de quem EMITIU o documento (o prestador do serviço ou vendedor), \
no formato XX.XXX.XXX/XXXX-XX. Se não encontrar, use null.
- cnpj_destinatario: o CNPJ ou CPF de quem RECEBEU o documento (o cliente/comprador), no \
mesmo formato. Se não encontrar ou o documento não distinguir um destinatário, use null.

Onde ficam os CNPJs nos documentos oficiais:
- DANFE da NF-e: o quadro "IDENTIFICAÇÃO DO EMITENTE" traz só nome e endereço; o CNPJ \
do emitente fica no campo "CNPJ" da linha de "INSCRIÇÃO ESTADUAL", logo abaixo. O \
destinatário fica no quadro "DESTINATÁRIO / REMETENTE".
- DANFE NFC-e (cupom): o CNPJ do emitente fica no topo; o destinatário, na linha \
"CONSUMIDOR".
- DANFSe (NFS-e): o emitente é o "Prestador do Serviço" (quadro "EMITENTE DA NFS-e"); o \
destinatário é o "TOMADOR DO SERVIÇO".
- description: uma descrição curta (até 100 caracteres) do produto ou serviço principal do \
documento. Se não conseguir determinar, use null.

Responda ESTRITAMENTE com um objeto JSON no formato:
{"amount": <número ou null>, "date": <string ou null>, "cnpj_emitente": <string ou null>, "cnpj_destinatario": <string ou null>, "description": <string ou null>}
"""


def _parse_json(texto: str) -> dict | None:
    try:
        dados = json.loads(texto)
    except (json.JSONDecodeError, TypeError):
        return None
    return dados if isinstance(dados, dict) else None


def _chamar_gemini(
    cliente, modelo: str, contents: list, operacao: str, ao_registrar_custo
) -> dict | None:
    from google.genai import types

    try:
        resposta = cliente.models.generate_content(
            model=modelo,
            contents=contents,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
    except Exception as exc:
        if _e_transitoria(exc):
            raise FalhaTransitoriaGemini(str(exc)) from exc
        return None

    if ao_registrar_custo and getattr(resposta, "usage_metadata", None):
        ao_registrar_custo(
            operacao=operacao,
            modelo=modelo,
            tokens_entrada=resposta.usage_metadata.prompt_token_count,
            tokens_saida=resposta.usage_metadata.candidates_token_count,
        )
    return _parse_json(resposta.text)


def gemini_de_imagem(
    cliente, modelo, imagem: bytes, mime: str, ao_registrar_custo=None
) -> dict | None:
    if cliente is None:
        return None
    from google.genai import types

    return _chamar_gemini(
        cliente,
        modelo,
        [types.Part.from_bytes(data=imagem, mime_type=mime), EXTRACTION_PROMPT],
        "extracao_imagem",
        ao_registrar_custo,
    )


def gemini_de_texto(cliente, modelo, texto: str, ao_registrar_custo=None) -> dict | None:
    if cliente is None or not texto.strip():
        return None
    return _chamar_gemini(
        cliente,
        modelo,
        [EXTRACTION_PROMPT, f"Texto do documento:\n{texto[:6000]}"],
        "extracao_texto",
        ao_registrar_custo,
    )


DATE_ISO_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def normalize_cnpj(bruto: str | None) -> str | None:
    if not bruto:
        return None
    digitos = re.sub(r"\D", "", bruto)
    if len(digitos) != 14:
        return None
    return f"{digitos[0:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:14]}"


def sanitize_gemini_result(dados: dict) -> dict:
    # US-46: o `amount` do modelo passa pela camada de tradução (ACL).
    amount = traduzir_valor_monetario(dados.get("amount"))

    data = dados.get("date")
    if not isinstance(data, str) or not DATE_ISO_REGEX.match(data):
        data = None

    cnpj_emitente = (
        normalize_cnpj(dados.get("cnpj_emitente")) if dados.get("cnpj_emitente") else None
    )
    cnpj_destinatario = (
        normalize_cnpj(dados.get("cnpj_destinatario")) if dados.get("cnpj_destinatario") else None
    )

    descricao = dados.get("description")
    descricao = descricao.strip()[:140] or None if isinstance(descricao, str) else None

    return {
        "value": amount,
        "date": data,
        "cnpj_emitente": cnpj_emitente,
        "cnpj_destinatario": cnpj_destinatario,
        "description": descricao,
    }


# -------------------------------------------------------------------
#  Extração por regex (fallback sem Gemini ou em falha)
# -------------------------------------------------------------------

BRL_AMOUNT_REGEX = re.compile(r"\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2}")
CNPJ_REGEX = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
DATE_REGEX = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{4})\b|\b(\d{4}[/-]\d{1,2}[/-]\d{1,2})\b")


def extract_amount_from_text(texto: str) -> float | None:
    achado = re.search(r"R\$\s*(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2})", texto, re.IGNORECASE)
    if achado:
        bruto = achado.group(1)
    else:
        m = BRL_AMOUNT_REGEX.search(texto)
        if not m:
            return None
        bruto = m.group(0)
    try:
        valor = float(Decimal(bruto.replace(".", "").replace(",", ".")))
        return valor if valor > 0 else None
    except InvalidOperation:
        return None


def extract_cnpjs(texto: str) -> tuple[str | None, str | None]:
    achados: list[str] = []
    for m in CNPJ_REGEX.finditer(texto):
        normal = normalize_cnpj(m.group(0))
        if normal and normal not in achados:
            achados.append(normal)
        if len(achados) == 2:
            break
    emitente = achados[0] if len(achados) >= 1 else None
    destinatario = achados[1] if len(achados) >= 2 else None
    return emitente, destinatario


def extract_date(texto: str) -> str | None:
    m = DATE_REGEX.search(texto)
    if not m:
        return None
    partes = m.group(0).replace("\\", "-").replace("/", "-").split("-")
    if len(partes[0]) == 4:
        return f"{partes[0]}-{partes[1].zfill(2)}-{partes[2].zfill(2)}"
    return f"{partes[2]}-{partes[1].zfill(2)}-{partes[0].zfill(2)}"


def extract_description(texto: str, max_len: int = 140) -> str | None:
    linhas = [ln.strip() for ln in texto.splitlines() if ln.strip()]
    if not linhas:
        return None
    for ln in linhas:
        if len(re.sub(r"[\d\.\-/]", "", ln)) > 3:
            return ln[:max_len]
    return linhas[0][:max_len]


def completar_cnpjs_pelo_ocr(estruturado: dict, ocr_texto: str) -> dict:
    """Preenche CNPJ que o LLM deixou nulo com o que o OCR achou no texto.

    No DANFE da NF-e o CNPJ do emitente fica num campo pequeno fora do quadro
    do emitente, e modelos multimodais leves às vezes não o enxergam numa
    página A4 inteira — o Tesseract lê. O OCR só completa o que veio vazio,
    nunca troca o que o modelo respondeu, e não repete o CNPJ que já ocupa o
    outro papel (emitente x destinatário).
    """
    do_ocr = dict(
        zip(("cnpj_emitente", "cnpj_destinatario"), extract_cnpjs(ocr_texto), strict=True)
    )
    for campo, outro in (
        ("cnpj_emitente", "cnpj_destinatario"),
        ("cnpj_destinatario", "cnpj_emitente"),
    ):
        candidato = do_ocr[campo]
        if not estruturado.get(campo) and candidato and candidato != estruturado.get(outro):
            estruturado[campo] = candidato
    return estruturado


def regex_extract(ocr_texto: str) -> dict:
    return {
        "value": extract_amount_from_text(ocr_texto) if ocr_texto else None,
        "date": extract_date(ocr_texto) if ocr_texto else None,
        "cnpj_emitente": (extract_cnpjs(ocr_texto) if ocr_texto else (None, None))[0],
        "cnpj_destinatario": (extract_cnpjs(ocr_texto) if ocr_texto else (None, None))[1],
        "description": extract_description(ocr_texto) if ocr_texto else None,
    }


def score_confidence(estruturado: dict, metodo: str) -> float:
    acertos = sum(1 for k in ("value", "date", "cnpj_emitente") if estruturado.get(k))
    if metodo == "gemini":
        return {3: 0.95, 2: 0.85, 1: 0.6}.get(acertos, 0.3)
    return {0: 0.2, 1: 0.55, 2: 0.75}.get(acertos, 0.9)


def _cnpj_digitos(valor: str | None) -> str | None:
    if not valor:
        return None
    digitos = re.sub(r"\D", "", valor)
    return digitos or None


def suggest_tx_type(
    user_cnpj: str | None, cnpj_emitente: str | None, cnpj_destinatario: str | None
) -> tuple[str | None, bool]:
    """(sugestão, auto_detectado). Usuário é emitente -> venda; destinatário -> compra."""
    meu = _cnpj_digitos(user_cnpj)
    if not meu:
        return None, False
    if meu == _cnpj_digitos(cnpj_emitente):
        return "venda", True
    if meu == _cnpj_digitos(cnpj_destinatario):
        return "compra", True
    return None, False


# -------------------------------------------------------------------
#  Orquestrador
# -------------------------------------------------------------------


@dataclass
class Extracao:
    ocr_texto: str
    estruturado: dict
    metodo: str  # "gemini" | "regex"


def processar_arquivo(
    conteudo: bytes,
    ext: str,
    *,
    caminho: Path,
    gemini_cliente=None,
    gemini_modelo: str = "gemini-3.5-flash-lite",
    user_cnpj: str | None = None,
    ao_registrar_custo=None,
    propagar_falha_transitoria: bool = False,
) -> Extracao:
    """Roda OCR + extração e devolve os campos estruturados já pontuados.

    O arquivo já foi gravado em ``caminho`` (o OCR e a conversão de PDF
    trabalham sobre um caminho). ``conteudo`` são os mesmos bytes, usados para
    a extração multimodal de imagem.
    """
    ext = ext.lower()
    visual = ext in IMAGE_EXTS or ext == ".pdf"

    # Imagem e PDF: o Gemini lê os pixels, não o texto do OCR, então os dois
    # correm em paralelo e o upload leva o mais lento deles, não a soma.
    # Texto puro: o Gemini precisa do texto, que é só ler o arquivo.
    with ThreadPoolExecutor(max_workers=1) as pool:
        futuro_ocr = pool.submit(extrair_texto, caminho, ext)
        if not visual:
            ocr_texto = futuro_ocr.result()
        resultado_gemini = _extrair_com_gemini(
            conteudo,
            ext,
            caminho,
            ocr_texto="" if visual else ocr_texto,
            gemini_cliente=gemini_cliente,
            gemini_modelo=gemini_modelo,
            ao_registrar_custo=ao_registrar_custo,
            propagar_falha_transitoria=propagar_falha_transitoria,
        )
        ocr_texto = futuro_ocr.result()

    if resultado_gemini is not None:
        estruturado = completar_cnpjs_pelo_ocr(sanitize_gemini_result(resultado_gemini), ocr_texto)
        metodo = "gemini"
    else:
        estruturado = regex_extract(ocr_texto)
        metodo = "regex"

    estruturado["confidence"] = score_confidence(estruturado, metodo)
    sugestao, auto = suggest_tx_type(
        user_cnpj, estruturado.get("cnpj_emitente"), estruturado.get("cnpj_destinatario")
    )
    estruturado["tx_type_sugerido"] = sugestao
    estruturado["tx_type_auto_detectado"] = auto

    return Extracao(ocr_texto=ocr_texto, estruturado=estruturado, metodo=metodo)


def _extrair_com_gemini(
    conteudo: bytes,
    ext: str,
    caminho: Path,
    *,
    ocr_texto: str,
    gemini_cliente,
    gemini_modelo: str,
    ao_registrar_custo,
    propagar_falha_transitoria: bool,
) -> dict | None:
    try:
        resultado_gemini = None
        if gemini_cliente is not None:
            if ext in IMAGE_EXTS:
                resultado_gemini = gemini_de_imagem(
                    gemini_cliente,
                    gemini_modelo,
                    conteudo,
                    IMAGE_MIME_TYPES[ext],
                    ao_registrar_custo,
                )
            elif ext == ".pdf":
                png = pdf_primeira_pagina_png(caminho)
                if png:
                    resultado_gemini = gemini_de_imagem(
                        gemini_cliente, gemini_modelo, png, "image/png", ao_registrar_custo
                    )
            else:
                resultado_gemini = gemini_de_texto(
                    gemini_cliente, gemini_modelo, ocr_texto, ao_registrar_custo
                )
    except FalhaTransitoriaGemini:
        if propagar_falha_transitoria:
            raise
        resultado_gemini = None
    return resultado_gemini
