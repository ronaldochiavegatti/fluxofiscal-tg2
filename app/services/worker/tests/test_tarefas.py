"""Testes da tarefa `processar_documento` (US-18).

A tarefa não faz OCR: delega ao `documents` por HTTP. O que se verifica aqui é a
orquestração — sucesso, reagendamento de falha transitória, fila morta após 3
tentativas e não-reagendamento de erro permanente.
"""

import httpx
import pytest
from celery.exceptions import Retry

from app import tarefas


class _Resposta:
    def __init__(self, status_code, corpo=None):
        self.status_code = status_code
        self._corpo = corpo or {}

    def json(self):
        return self._corpo


@pytest.fixture
def chamar(monkeypatch):
    """Executa a tarefa capturando o POST ao documents."""
    chamadas = []

    def _rodar(resposta, *, retries=0):
        def _post(url, **kwargs):
            chamadas.append({"url": url, **kwargs})
            if isinstance(resposta, Exception):
                raise resposta
            return resposta

        monkeypatch.setattr(tarefas.httpx, "post", _post)
        return tarefas.processar_documento.apply(
            kwargs={
                "documento_id": "doc-1",
                "chave_armazenamento": "abc.png",
                "ext": ".png",
                "user_cnpj": "12.345.678/0001-95",
            },
            retries=retries,
            throw=True,
        )

    _rodar.chamadas = chamadas
    return _rodar


def test_sucesso_devolve_o_corpo(chamar):
    r = chamar(_Resposta(200, {"documento_id": "doc-1", "estado": "extraido", "metodo": "gemini"}))
    assert r.result["estado"] == "extraido"
    assert chamar.chamadas[0]["url"].endswith("/_interno/processar/doc-1")
    assert chamar.chamadas[0]["json"] == {"user_cnpj": "12.345.678/0001-95"}
    assert chamar.chamadas[0]["params"] == {"ultima_tentativa": False}


def test_falha_transitoria_reagenda(chamar):
    with pytest.raises(Retry):
        chamar(_Resposta(503), retries=0)


def test_erro_permanente_nao_reagenda(chamar):
    r = chamar(_Resposta(422), retries=0)
    assert r.result == {"documento_id": "doc-1", "estado": "erro", "permanente": True}


def test_documents_inacessivel_reagenda(chamar):
    with pytest.raises(Retry):
        chamar(httpx.ConnectError("recusou"))


def test_ultima_tentativa_marca_a_flag(chamar):
    # retries == max: a rota deve receber ultima_tentativa=true e devolver 200
    chamar(
        _Resposta(200, {"documento_id": "doc-1", "estado": "erro", "permanente": False}), retries=3
    )
    assert chamar.chamadas[0]["params"] == {"ultima_tentativa": True}


def test_recuo_e_exponencial():
    assert tarefas._recuo(0) >= 2
    assert tarefas._recuo(1) >= 4
    assert tarefas._recuo(2) >= 8
    assert tarefas._recuo(9) <= 60 * 1.25
