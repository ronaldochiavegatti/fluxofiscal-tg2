"""Persistência de documentos no MongoDB (US-20, ADR-0005).

Atrás da flag `documentos-persistidos`. Com ela desligada (padrão), o Documents
segue sem banco: os metadados vivem só na resposta HTTP e no localStorage do
navegador, como antes.

A coleção `documentos` guarda o ciclo de vida de cada arquivo. O índice único
sobre `(usuario_email, arquivo.hash_sha256)` entrega a deduplicação de reenvio
como efeito colateral — o mesmo arquivo, do mesmo usuário, não é reprocessado
nem cobrado de novo.

O que NÃO vai para o Mongo (ADR-0005): transação financeira, saldo de tokens,
usuário — esses ficam no PostgreSQL do Limits/Billing.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

ESTADOS = ("recebido", "processando", "extraido", "confirmado", "descartado", "erro")


def agora() -> datetime:
    return datetime.now(UTC)


def novo_documento(
    *,
    email: str,
    nome_original: str,
    chave_armazenamento: str,
    tamanho_bytes: int,
    tipo_mime: str,
    hash_sha256: str,
    ocr_texto: str,
    ocr_motor: str,
    extracao_metodo: str,
    extracao_modelo: str | None,
    campos: dict,
    confianca: float,
) -> dict:
    """Monta o registro do documento no formato do ADR-0005."""
    ts = agora()
    return {
        "_id": str(uuid.uuid4()),
        "usuario_email": email,
        "arquivo": {
            "nome_original": nome_original,
            "chave_armazenamento": chave_armazenamento,
            "tamanho_bytes": tamanho_bytes,
            "tipo_mime": tipo_mime,
            "hash_sha256": hash_sha256,
        },
        "estado": "extraido",
        "ocr": {"motor": ocr_motor, "texto": ocr_texto},
        "extracao": {
            "metodo": extracao_metodo,
            "modelo": extracao_modelo,
            "campos": campos,
            "confianca": confianca,
        },
        "transacao_limits_id": None,
        "historico": [{"evento": "extraido", "em": ts}],
        "criado_em": ts,
        "atualizado_em": ts,
    }


def novo_documento_pendente(
    *,
    email: str,
    nome_original: str,
    chave_armazenamento: str,
    tamanho_bytes: int,
    tipo_mime: str,
    hash_sha256: str,
    user_cnpj: str | None = None,
) -> dict:
    """Registro de um documento que ainda não foi processado (US-18).

    O `/upload` assíncrono grava isto e responde 202; o worker preenche a
    extração depois. Mesmo formato do ADR-0005, com `estado: "recebido"` e a
    seção `extracao` vazia.
    """
    ts = agora()
    return {
        "_id": str(uuid.uuid4()),
        "usuario_email": email,
        "arquivo": {
            "nome_original": nome_original,
            "chave_armazenamento": chave_armazenamento,
            "tamanho_bytes": tamanho_bytes,
            "tipo_mime": tipo_mime,
            "hash_sha256": hash_sha256,
        },
        "estado": "recebido",
        "usuario_cnpj": user_cnpj,
        "ocr": {"motor": None, "texto": ""},
        "extracao": {"metodo": None, "modelo": None, "campos": {}, "confianca": 0.0},
        "erro": None,
        "transacao_limits_id": None,
        "historico": [{"evento": "recebido", "em": ts}],
        "criado_em": ts,
        "atualizado_em": ts,
    }


def nova_repeticao(original: dict) -> dict:
    """Registro para salvar de novo um arquivo que já foi confirmado (#93).

    O usuário viu o aviso de nota repetida e decidiu continuar: a segunda
    venda precisa de linha própria no histórico, senão o faturamento mostra
    duas transações e o histórico uma nota só. O arquivo é o mesmo (mesma
    chave no armazenamento); só o hash ganha um sufixo, porque o índice único
    `dedup_hash` não aceita dois registros com o mesmo hash. `por_hash`
    continua achando o original, que é o que o reenvio deve encontrar.
    """
    ts = agora()
    novo_id = str(uuid.uuid4())
    arquivo = dict(original["arquivo"])
    arquivo["hash_sha256"] = f"{arquivo['hash_sha256']}:repeticao:{novo_id}"
    return {
        "_id": novo_id,
        "usuario_email": original["usuario_email"],
        "arquivo": arquivo,
        "estado": "extraido",
        "ocr": original["ocr"],
        "extracao": original["extracao"],
        "transacao_limits_id": None,
        "historico": [{"evento": "repeticao", "em": ts, "de": original["_id"]}],
        "criado_em": ts,
        "atualizado_em": ts,
    }


def hash_do_arquivo(doc: dict) -> str:
    """Hash do conteúdo, sem o sufixo de `nova_repeticao`."""
    return str(doc["arquivo"]["hash_sha256"]).split(":", 1)[0]


@runtime_checkable
class RepositorioDocumentos(Protocol):
    def por_hash(self, email: str, hash_sha256: str) -> dict | None: ...
    def por_id(self, doc_id: str) -> dict | None: ...
    def salvar(self, documento: dict) -> dict: ...
    def listar(self, email: str, limite: int = 100) -> list[dict]: ...
    def apagar_do_usuario(self, email: str) -> int: ...
    def confirmados_com_valor_e_data(
        self, email: str, *, valor: float, data: str, excluir_id: str
    ) -> list[dict]: ...
    def marcar_processando(self, doc_id: str) -> dict | None: ...
    def concluir_extracao(
        self,
        doc_id: str,
        *,
        ocr_texto: str,
        ocr_motor: str,
        metodo: str,
        modelo: str | None,
        campos: dict,
        confianca: float,
    ) -> dict | None: ...
    def marcar_confirmado(
        self,
        doc_id: str,
        *,
        campos: dict,
        transacao_limits_id: int | None,
        repeticao_de: list[str] | None = None,
    ) -> dict | None: ...
    def corrigir_confirmacao(self, doc_id: str, *, campos: dict) -> dict | None: ...
    def apagar(self, doc_id: str) -> dict | None: ...
    def usam_o_arquivo(self, chave_armazenamento: str) -> int: ...
    def marcar_erro(self, doc_id: str, *, motivo: str, permanente: bool) -> dict | None: ...


class RepositorioMongo:
    def __init__(self, colecao):
        self._c = colecao
        # Único parcial sobre o hash — é o que faz a deduplicação (ADR-0005).
        self._c.create_index(
            [("usuario_email", 1), ("arquivo.hash_sha256", 1)],
            unique=True,
            name="dedup_hash",
        )
        self._c.create_index([("usuario_email", 1), ("criado_em", -1)], name="por_usuario")
        self._c.create_index("estado", name="por_estado")

    def por_hash(self, email: str, hash_sha256: str) -> dict | None:
        return self._c.find_one({"usuario_email": email, "arquivo.hash_sha256": hash_sha256})

    def por_id(self, doc_id: str) -> dict | None:
        return self._c.find_one({"_id": doc_id})

    def salvar(self, documento: dict) -> dict:
        try:
            self._c.insert_one(documento)
        except Exception as erro:
            # Corrida: outro request gravou o mesmo hash entre o por_hash e aqui.
            # O índice único barra o segundo; devolvemos o que já está lá.
            if _e_duplicidade(erro):
                existente = self.por_hash(
                    documento["usuario_email"], documento["arquivo"]["hash_sha256"]
                )
                if existente:
                    return existente
            raise
        return documento

    def listar(self, email: str, limite: int = 100) -> list[dict]:
        cursor = self._c.find({"usuario_email": email}).sort("criado_em", -1).limit(limite)
        return list(cursor)

    def apagar_do_usuario(self, email: str) -> int:
        """Usado pelo reset da demo: sem isto, o histórico continuava listando
        documentos cujos arquivos e transações o reset já tinha apagado."""
        return self._c.delete_many({"usuario_email": email}).deleted_count

    def confirmados_com_valor_e_data(
        self, email: str, *, valor: float, data: str, excluir_id: str
    ) -> list[dict]:
        """Notas já confirmadas com o mesmo valor e a mesma data (#93).

        Compara com o que o usuário confirmou, não com a extração: uma nota
        corrigida de R$ 1.200 para R$ 1.250 é uma nota de R$ 1.250. O CNPJ fica
        para quem chama, porque o formato gravado varia (com e sem máscara).
        """
        cursor = (
            self._c.find(
                {
                    "usuario_email": email,
                    "estado": "confirmado",
                    "_id": {"$ne": excluir_id},
                    "confirmacao.campos.value": valor,
                    "confirmacao.campos.date": data,
                }
            )
            .sort("criado_em", -1)
            .limit(10)
        )
        return list(cursor)

    # --- transições de estado do processamento assíncrono (US-18) ---

    def _transicao(self, doc_id: str, *, campos: dict, evento: str) -> dict | None:
        ts = agora()
        self._c.update_one(
            {"_id": doc_id},
            {
                "$set": {**campos, "atualizado_em": ts},
                "$push": {"historico": {"evento": evento, "em": ts}},
            },
        )
        return self.por_id(doc_id)

    def marcar_processando(self, doc_id: str) -> dict | None:
        return self._transicao(doc_id, campos={"estado": "processando"}, evento="processando")

    def concluir_extracao(
        self,
        doc_id: str,
        *,
        ocr_texto: str,
        ocr_motor: str,
        metodo: str,
        modelo: str | None,
        campos: dict,
        confianca: float,
    ) -> dict | None:
        return self._transicao(
            doc_id,
            campos={
                "estado": "extraido",
                "erro": None,
                "ocr": {"motor": ocr_motor, "texto": ocr_texto},
                "extracao": {
                    "metodo": metodo,
                    "modelo": modelo,
                    "campos": campos,
                    "confianca": confianca,
                },
            },
            evento="extraido",
        )

    def marcar_confirmado(
        self,
        doc_id: str,
        *,
        campos: dict,
        transacao_limits_id: int | None,
        repeticao_de: list[str] | None = None,
    ) -> dict | None:
        """A extração original fica intacta em `extracao`; o que o usuário
        confirmou (com correções) vai para `confirmacao`. `repeticao_de` lista
        as notas já salvas que o aviso de repetição apontou (#93) — o usuário
        confirmou mesmo assim, e o histórico sinaliza."""
        return self._transicao(
            doc_id,
            campos={
                "estado": "confirmado",
                "confirmacao": {"campos": campos, "transacao_limits_id": transacao_limits_id},
                "repeticao_de": repeticao_de or [],
            },
            evento="confirmado",
        )

    def corrigir_confirmacao(self, doc_id: str, *, campos: dict) -> dict | None:
        """Correção depois de salva (#95): troca só os campos confirmados; a
        transação no Limits e a extração original ficam como estão."""
        return self._transicao(doc_id, campos={"confirmacao.campos": campos}, evento="corrigido")

    def apagar(self, doc_id: str) -> dict | None:
        """Remove o registro e devolve como ele estava (#96)."""
        return self._c.find_one_and_delete({"_id": doc_id})

    def usam_o_arquivo(self, chave_armazenamento: str) -> int:
        """Quantos registros apontam para o arquivo. A repetição de um arquivo
        idêntico (#93) reaproveita a mesma chave: apagar uma das notas não
        pode levar o arquivo da outra."""
        return self._c.count_documents({"arquivo.chave_armazenamento": chave_armazenamento})

    def marcar_erro(self, doc_id: str, *, motivo: str, permanente: bool) -> dict | None:
        return self._transicao(
            doc_id,
            campos={"estado": "erro", "erro": {"motivo": motivo, "permanente": permanente}},
            evento="erro",
        )


def _e_duplicidade(erro: Exception) -> bool:
    nome = type(erro).__name__
    return nome == "DuplicateKeyError" or "E11000" in str(erro)
