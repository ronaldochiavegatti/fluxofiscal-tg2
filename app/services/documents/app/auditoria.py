"""Trilha de auditoria — apenas escrita, encadeada por hash (US-22, ADR-0005/0017).

Toda mutação de dado fiscal que passa pelo Documents (a extração de um documento
e a confirmação humana dos campos) vira um registro nesta coleção. O registro
diz **quem** fez, **o quê**, sobre **qual recurso**, **quando**, com qual
`trace_id`, e o **valor anterior** e o **valor novo**.

Imutabilidade: não há método de alteração nem de remoção aqui, e cada registro
carrega o SHA-256 do anterior. Alterar um registro no banco quebra a cadeia a
partir dele — `verificar_integridade()` detecta.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

GENESE = "0" * 64

# "documento.corrigido": correção feita no detalhe da nota depois de salva (#95).
ACOES = (
    "documento.extraido",
    "documento.confirmado",
    "documento.corrigido",
    # Nota apagada pelo usuário (#96): a trilha fica, mesmo sem o documento.
    "documento.apagado",
)


def _agora_iso() -> str:
    # String ISO com precisão de milissegundos: round-trip perfeito pelo Mongo
    # (BSON date perde microssegundos), o que mantém o hash reprodutível.
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _canonico(payload: dict) -> str:
    """JSON estável (chaves ordenadas) para o hash ser reprodutível."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _hash(hash_anterior: str, corpo: dict) -> str:
    return hashlib.sha256(f"{hash_anterior}{_canonico(corpo)}".encode()).hexdigest()


def _corpo_de(registro: dict) -> dict:
    """A parte do registro que entra no hash (tudo menos os campos do próprio
    encadeamento e o _id)."""
    return {
        "seq": registro["seq"],
        "por": registro["por"],
        "acao": registro["acao"],
        "recurso": registro["recurso"],
        "em": registro["em"],
        "trace_id": registro.get("trace_id"),
        "antes": registro.get("antes"),
        "depois": registro["depois"],
    }


def montar_registro(
    *,
    seq: int,
    por: str,
    acao: str,
    recurso_id: str,
    antes: dict | None,
    depois: dict,
    trace_id: str | None,
    hash_anterior: str,
) -> dict:
    if acao not in ACOES:
        raise ValueError(f"ação de auditoria desconhecida: {acao!r}")
    corpo = {
        "seq": seq,
        "por": por,
        "acao": acao,
        "recurso": {"tipo": "documento", "id": recurso_id},
        "em": _agora_iso(),
        "trace_id": trace_id,
        "antes": antes,
        "depois": depois,
    }
    return {
        "_id": str(uuid.uuid4()),
        **corpo,
        "hash_anterior": hash_anterior,
        "hash": _hash(hash_anterior, corpo),
    }


@runtime_checkable
class RepositorioAuditoria(Protocol):
    def registrar(
        self,
        *,
        por: str,
        acao: str,
        recurso_id: str,
        antes: dict | None,
        depois: dict,
        trace_id: str | None,
    ) -> dict: ...
    def por_recurso(self, recurso_id: str) -> list[dict]: ...
    def listar(self, por: str, limite: int = 200) -> list[dict]: ...
    def verificar_integridade(self, recurso_id: str | None = None) -> bool: ...


class RepositorioAuditoriaMongo:
    """Coleção `auditoria` no Mongo. Só expõe escrita e leitura — de propósito."""

    def __init__(self, colecao):
        self._c = colecao
        self._c.create_index("seq", name="ordem", unique=True)
        self._c.create_index([("recurso.id", 1), ("seq", 1)], name="por_recurso")
        self._c.create_index([("por", 1), ("seq", -1)], name="por_usuario")

    def _cabeca(self) -> tuple[int, str]:
        ultimo = self._c.find_one(sort=[("seq", -1)])
        return (ultimo["seq"], ultimo["hash"]) if ultimo else (0, GENESE)

    def registrar(
        self,
        *,
        por: str,
        acao: str,
        recurso_id: str,
        antes: dict | None,
        depois: dict,
        trace_id: str | None,
    ) -> dict:
        seq_anterior, hash_anterior = self._cabeca()
        registro = montar_registro(
            seq=seq_anterior + 1,
            por=por,
            acao=acao,
            recurso_id=recurso_id,
            antes=antes,
            depois=depois,
            trace_id=trace_id,
            hash_anterior=hash_anterior,
        )
        self._c.insert_one(registro)
        return registro

    def por_recurso(self, recurso_id: str) -> list[dict]:
        return list(self._c.find({"recurso.id": recurso_id}).sort("seq", 1))

    def listar(self, por: str, limite: int = 200) -> list[dict]:
        return list(self._c.find({"por": por}).sort("seq", -1).limit(limite))

    def verificar_integridade(self, recurso_id: str | None = None) -> bool:
        """Recalcula a cadeia. Sem `recurso_id`, valida o encadeamento inteiro
        (`hash_anterior` bate e `hash` bate). Com `recurso_id`, valida só o
        `hash` de cada registro daquele recurso."""
        if recurso_id is not None:
            return all(
                _hash(reg["hash_anterior"], _corpo_de(reg)) == reg["hash"]
                for reg in self.por_recurso(recurso_id)
            )

        anterior = GENESE
        for reg in self._c.find().sort("seq", 1):
            if reg["hash_anterior"] != anterior:
                return False
            if _hash(anterior, _corpo_de(reg)) != reg["hash"]:
                return False
            anterior = reg["hash"]
        return True
