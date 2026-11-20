"""Camada anticorrupção (ACL) do serviço de documents (US-46).

Duas fronteiras são traduzidas explicitamente aqui, em vez de dados de um
contexto vazarem crus para o outro:

1. **Resposta do Gemini -> extração do domínio.** O modelo é uma fonte externa
   não confiável: pode devolver ``amount`` como número, como string com máscara
   brasileira (``"1.234,56"``) ou como lixo. ``traduzir_valor_monetario``
   normaliza para ``float`` positivo ou rejeita (``None``).
2. **Documento -> serviço de Limits.** Só os campos que uma transação precisa
   atravessam. Confiança, método e modelo de extração NÃO cruzam a fronteira:
   uma transação confirmada por um humano é fato, não estimativa.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

# Mesmo teto do modelo ``LimitsTransaction`` em main.py — mantido aqui para a
# tradução poder rejeitar antes de o valor chegar à validação do Pydantic.
VALOR_MAXIMO = 99_999_999.99

# Campos que a tradução documents -> Limits deliberadamente NÃO propaga. Fica
# como constante para o teste de fronteira poder afirmar sobre a lista.
CAMPOS_QUE_NAO_ATRAVESSAM = (
    "confidence",
    "confianca",
    "extraction_method",
    "extracao_metodo",
    "extracao_modelo",
    "modelo",
    "ocr_text",
    "ocr_texto",
)

_SO_NUMERO_E_SEPARADOR = re.compile(r"[^\d.,\-]")


def traduzir_valor_monetario(bruto: object) -> float | None:
    """Converte o ``amount`` devolvido pelo modelo em ``float`` positivo, ou ``None``.

    Aceita número (``int``/``float``) e string com máscara brasileira
    (``"1.234,56"``, ``"R$ 1.234,56"``) ou americana (``"1234.56"``). Rejeita
    (devolve ``None``) valor ausente, não numérico, ``<= 0`` ou acima do teto.
    """
    if bruto is None or isinstance(bruto, bool):
        # ``bool`` é subclasse de ``int``; ``True`` nunca é um valor monetário.
        return None
    if isinstance(bruto, (int, float)):
        return _validar(float(bruto))
    if not isinstance(bruto, str):
        return None

    texto = _SO_NUMERO_E_SEPARADOR.sub("", bruto).strip()
    if not texto or texto in {"-", ".", ","}:
        return None
    try:
        return _validar(float(Decimal(_normalizar_separadores(texto))))
    except (InvalidOperation, ValueError):
        return None


def _normalizar_separadores(texto: str) -> str:
    """Deixa apenas ``.`` como separador decimal.

    Com ``,`` e ``.`` juntos, o que aparecer por último é o decimal
    (``"1.234,56"`` -> ``"1234.56"``; ``"1,234.56"`` -> ``"1234.56"``). Só com
    ``,`` ele é o decimal (``"1234,56"`` -> ``"1234.56"``).
    """
    tem_virgula = "," in texto
    tem_ponto = "." in texto
    if tem_virgula and tem_ponto:
        if texto.rfind(",") > texto.rfind("."):
            return texto.replace(".", "").replace(",", ".")
        return texto.replace(",", "")
    if tem_virgula:
        return texto.replace(",", ".")
    return texto


def _validar(valor: float) -> float | None:
    if valor <= 0 or valor > VALOR_MAXIMO:
        return None
    return round(valor, 2)


def traduzir_para_limits(
    *,
    email: str,
    amount: float,
    tx_date: date | None,
    source: str,
    tx_type: str,
    cnpj_cliente: str | None = None,
) -> dict:
    """Monta o payload da transação para o serviço de Limits.

    A lista de chaves é fechada de propósito: confiança, método e modelo de
    extração ficam do lado de cá da fronteira. Ver ``CAMPOS_QUE_NAO_ATRAVESSAM``.

    ``cnpj_cliente`` (US-27, ADR-0021) é a exceção deliberada e mais recente
    a essa lista: só atravessa quando ``tx_type`` é ``"venda"`` — em
    ``"compra"`` o CNPJ disponível é o do fornecedor (``cnpj_emitente``), que
    não é "de quais clientes vem meu faturamento" e por isso não cruza aqui.
    """
    return {
        "email": email,
        "amount": amount,
        "tx_date": (tx_date or datetime.now(UTC).date()).isoformat(),
        "source": source,
        "tx_type": tx_type if tx_type in ("venda", "compra") else "venda",
        "cnpj_cliente": cnpj_cliente if tx_type == "venda" else None,
    }
