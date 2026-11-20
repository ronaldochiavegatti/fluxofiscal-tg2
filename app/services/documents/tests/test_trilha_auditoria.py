"""Trilha de auditoria pelas rotas do Documents (US-22).

Cenários Gherkin:
  - Origem do valor é rastreável: extraído R$ 1.200, corrigido para R$ 1.250 ->
    o histórico mostra o valor extraído, o método, o valor corrigido e quando.
  - A trilha não pode ser alterada: PUT/PATCH/DELETE num registro -> recusado.
"""

import mongomock
import pytest

from app import main
from app.auditoria import RepositorioAuditoriaMongo
from app.repositorio import RepositorioMongo
from tests.conftest import EMAIL

NOTA = b"NOTA FISCAL\nVALOR TOTAL R$ 1.200,00\nEmissao 17/06/2026\n"


@pytest.fixture
def persistido(monkeypatch: pytest.MonkeyPatch):
    banco = mongomock.MongoClient()["fluxofiscal"]
    monkeypatch.setattr(main, "_repositorio", RepositorioMongo(banco["documentos"]))
    monkeypatch.setattr(main, "_auditoria", RepositorioAuditoriaMongo(banco["auditoria"]))
    monkeypatch.setattr(main, "MONGO_URL", "mongodb://fake:27017")
    monkeypatch.setattr(
        main, "esta_ativa", lambda nome, *, padrao=False, **_: nome == "documentos-persistidos"
    )
    return main._auditoria


def _upload(cliente):
    return cliente.post(
        "/upload", files={"file": ("nota.txt", NOTA, "text/plain")}, data={"email": EMAIL}
    ).json()


def _confirmar(cliente, doc_id, amount=1250.0):
    return cliente.post(
        "/confirm",
        json={
            "email": EMAIL,
            "amount": amount,
            "tx_date": "2026-06-17",
            "tx_type": "venda",
            "documento_id": doc_id,
        },
    )


class TestRastreabilidade:
    def test_upload_registra_a_extracao(self, cliente, persistido):
        doc_id = _upload(cliente)["documento_id"]

        resp = cliente.get(f"/documentos/{doc_id}/auditoria")
        assert resp.status_code == 200
        registros = resp.json()["registros"]
        assert len(registros) == 1
        assert registros[0]["acao"] == "documento.extraido"
        assert registros[0]["depois"]["campos"]["value"] == 1200.0
        assert registros[0]["depois"]["metodo"] == "regex"

    def test_confirmacao_registra_a_correcao(self, cliente, persistido, limits_falso):
        doc_id = _upload(cliente)["documento_id"]
        _confirmar(cliente, doc_id, amount=1250.0)

        registros = cliente.get(f"/documentos/{doc_id}/auditoria").json()["registros"]
        assert [r["acao"] for r in registros] == ["documento.extraido", "documento.confirmado"]
        correcao = registros[1]
        assert correcao["antes"]["campos"]["value"] == 1200.0  # valor extraído
        assert correcao["antes"]["metodo"] == "regex"  # método
        assert correcao["depois"]["value"] == 1250.0  # valor corrigido
        assert correcao["depois"]["transacao_limits_id"] == 1
        assert correcao["em"]  # quando

    def test_integridade_reporta_cadeia_intacta(self, cliente, persistido, limits_falso):
        doc_id = _upload(cliente)["documento_id"]
        _confirmar(cliente, doc_id)
        assert cliente.get("/auditoria/integridade").json()["integra"] is True

    def test_listar_a_trilha_do_usuario(self, cliente, persistido):
        _upload(cliente)
        lista = cliente.get("/auditoria", params={"email": EMAIL}).json()
        assert len(lista) == 1
        assert lista[0]["por"] == EMAIL


class TestImutabilidade:
    @pytest.mark.parametrize("metodo", ["PUT", "PATCH", "DELETE"])
    def test_alterar_um_registro_e_recusado(self, cliente, persistido, metodo):
        doc_id = _upload(cliente)["documento_id"]
        registro_id = cliente.get(f"/documentos/{doc_id}/auditoria").json()["registros"][0]["_id"]

        resp = cliente.request(metodo, f"/auditoria/{registro_id}", json={"depois": {"value": 1}})
        assert resp.status_code == 405

    def test_integridade_denuncia_registro_adulterado(self, cliente, persistido):
        doc_id = _upload(cliente)["documento_id"]
        # adulteração direta no banco (o que a API não permite)
        persistido._c.update_one({"recurso.id": doc_id}, {"$set": {"depois.campos.value": 9999.0}})
        assert cliente.get("/auditoria/integridade").json()["integra"] is False


class TestSemPersistencia:
    def test_trilha_responde_409_sem_a_flag(self, cliente):
        assert cliente.get("/documentos/qualquer/auditoria").status_code == 409
        assert cliente.get("/auditoria", params={"email": EMAIL}).status_code == 409
