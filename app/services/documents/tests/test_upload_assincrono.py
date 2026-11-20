"""Upload assíncrono (US-18), atrás da flag `ocr-assincrono`.

Cenários Gherkin:
  - Resposta imediata: 202 com id e URL de acompanhamento, sem rodar OCR/Gemini.
  - Falha transitória (Gemini 429) é reprocessada; após 3 tentativas o documento
    fica em "erro".
  - Erro permanente (arquivo corrompido/ausente) não é repetido.
"""

import mongomock
import pytest

from app import main
from app.auditoria import RepositorioAuditoriaMongo
from app.processamento import FalhaTransitoriaGemini
from app.repositorio import RepositorioMongo
from tests.conftest import EMAIL

NOTA = b"NOTA FISCAL\nVALOR TOTAL R$ 1.234,56\nEmissao 17/06/2026\n"


@pytest.fixture
def assincrono(monkeypatch: pytest.MonkeyPatch):
    """Flags `documentos-persistidos` + `ocr-assincrono` ligadas, Mongo fake,
    enfileiramento capturado em vez de publicado."""
    banco = mongomock.MongoClient()["fluxofiscal"]
    repo = RepositorioMongo(banco["documentos"])
    monkeypatch.setattr(main, "_repositorio", repo)
    monkeypatch.setattr(main, "_auditoria", RepositorioAuditoriaMongo(banco["auditoria"]))
    monkeypatch.setattr(main, "MONGO_URL", "mongodb://fake:27017")
    monkeypatch.setattr(
        main,
        "esta_ativa",
        lambda nome, *, padrao=False, **_: nome in ("documentos-persistidos", "ocr-assincrono"),
    )
    fila: list[dict] = []
    monkeypatch.setattr(
        main,
        "enfileirar_processamento",
        lambda doc_id, **kw: fila.append({"documento_id": doc_id, **kw}) or "task-abc",
    )
    repo.fila = fila
    return repo


def enviar(cliente, conteudo=NOTA, nome="nota.txt"):
    return cliente.post(
        "/upload", files={"file": (nome, conteudo, "text/plain")}, data={"email": EMAIL}
    )


class TestRespostaImediata:
    def test_202_com_id_e_url_de_acompanhamento(self, cliente, assincrono, monkeypatch):
        def _nao_processa(*_a, **_k):
            raise AssertionError("o /upload assíncrono não pode rodar a extração")

        monkeypatch.setattr(main.processamento, "processar_arquivo", _nao_processa)

        resp = enviar(cliente)

        assert resp.status_code == 202
        corpo = resp.json()
        assert corpo["estado"] == "recebido"
        assert corpo["acompanhamento_url"] == f"/documents/documentos/{corpo['documento_id']}"
        assert len(assincrono.fila) == 1
        assert assincrono.fila[0]["documento_id"] == corpo["documento_id"]

    def test_documento_nasce_em_recebido(self, cliente, assincrono):
        doc_id = enviar(cliente).json()["documento_id"]
        detalhe = cliente.get(f"/documentos/{doc_id}").json()
        assert detalhe["estado"] == "recebido"
        assert detalhe["historico"][0]["evento"] == "recebido"

    def test_fila_fora_do_ar_vira_503(self, cliente, assincrono, monkeypatch):
        def _falha(*_a, **_k):
            raise RuntimeError("broker fora")

        monkeypatch.setattr(main, "enfileirar_processamento", _falha)

        resp = enviar(cliente)
        assert resp.status_code == 503


class TestProcessamentoInterno:
    def _subir(self, cliente):
        return enviar(cliente).json()["documento_id"]

    def test_worker_conclui_a_extracao(self, cliente, assincrono):
        doc_id = self._subir(cliente)

        resp = cliente.post(f"/_interno/processar/{doc_id}", json={"user_cnpj": None})

        assert resp.status_code == 200
        assert resp.json()["estado"] == "extraido"
        detalhe = cliente.get(f"/documentos/{doc_id}").json()
        assert detalhe["estado"] == "extraido"
        assert detalhe["structured_data"]["value"] == 1234.56

    def test_idempotente_apos_extraido(self, cliente, assincrono):
        doc_id = self._subir(cliente)
        cliente.post(f"/_interno/processar/{doc_id}", json={})
        r2 = cliente.post(f"/_interno/processar/{doc_id}", json={})
        assert r2.status_code == 200
        assert r2.json()["estado"] == "extraido"

    def test_documento_some_entre_marcar_processando_e_concluir_e_vira_404(
        self, cliente, assincrono, monkeypatch
    ):
        """Corrida rara: `concluir_extracao` devolve `dict | None` — sem o
        guard, um `None` aqui quebraria com `TypeError` (500) em vez do 404
        já declarado no contrato desta rota. Encontrado pelo mypy."""
        doc_id = self._subir(cliente)
        monkeypatch.setattr(assincrono, "concluir_extracao", lambda *a, **k: None)

        resp = cliente.post(f"/_interno/processar/{doc_id}", json={})

        assert resp.status_code == 404

    def test_arquivo_ausente_e_erro_permanente(self, cliente, assincrono, pasta_de_upload):
        doc_id = self._subir(cliente)
        for f in pasta_de_upload.iterdir():
            f.unlink()

        resp = cliente.post(f"/_interno/processar/{doc_id}", json={})

        assert resp.status_code == 422
        detalhe = cliente.get(f"/documentos/{doc_id}").json()
        assert detalhe["estado"] == "erro"
        assert detalhe["erro"]["permanente"] is True

    def test_falha_transitoria_pede_retentativa(self, cliente, assincrono, monkeypatch):
        doc_id = self._subir(cliente)

        def _429(*_a, **_k):
            raise FalhaTransitoriaGemini("429")

        monkeypatch.setattr(main.processamento, "processar_arquivo", _429)

        resp = cliente.post(f"/_interno/processar/{doc_id}", json={})
        assert resp.status_code == 503
        # o documento fica em "processando", não em erro — o worker vai retentar
        assert cliente.get(f"/documentos/{doc_id}").json()["estado"] == "processando"

    def test_ultima_tentativa_manda_para_a_fila_morta(self, cliente, assincrono, monkeypatch):
        doc_id = self._subir(cliente)
        monkeypatch.setattr(
            main.processamento,
            "processar_arquivo",
            lambda *a, **k: (_ for _ in ()).throw(FalhaTransitoriaGemini("429")),
        )

        resp = cliente.post(f"/_interno/processar/{doc_id}?ultima_tentativa=true", json={})
        assert resp.status_code == 200
        assert resp.json()["estado"] == "erro"
        detalhe = cliente.get(f"/documentos/{doc_id}").json()
        assert detalhe["erro"]["permanente"] is False

    def test_erro_permanente_nao_reprocessa(self, cliente, assincrono, monkeypatch):
        doc_id = self._subir(cliente)

        def _quebrado(*_a, **_k):
            raise ValueError("arquivo corrompido")

        monkeypatch.setattr(main.processamento, "processar_arquivo", _quebrado)

        resp = cliente.post(f"/_interno/processar/{doc_id}", json={})
        assert resp.status_code == 422
        assert cliente.get(f"/documentos/{doc_id}").json()["erro"]["permanente"] is True

    def test_token_interno_e_exigido_quando_configurado(self, cliente, assincrono, monkeypatch):
        doc_id = self._subir(cliente)
        monkeypatch.setattr(main, "INTERNO_TOKEN", "s3gr3d0")

        semtoken = cliente.post(f"/_interno/processar/{doc_id}", json={})
        assert semtoken.status_code == 401

        comtoken = cliente.post(
            f"/_interno/processar/{doc_id}", json={}, headers={"X-Interno-Token": "s3gr3d0"}
        )
        assert comtoken.status_code == 200


class TestReprocessar:
    def test_documento_em_erro_volta_para_a_fila(self, cliente, assincrono, monkeypatch):
        doc_id = enviar(cliente).json()["documento_id"]
        monkeypatch.setattr(
            main.processamento,
            "processar_arquivo",
            lambda *a, **k: (_ for _ in ()).throw(ValueError("ruim")),
        )
        cliente.post(f"/_interno/processar/{doc_id}", json={})
        assincrono.fila.clear()

        resp = cliente.post(f"/documentos/{doc_id}/reprocessar")

        assert resp.status_code == 200
        assert resp.json()["estado"] == "processando"
        assert len(assincrono.fila) == 1

    def test_reprocessar_so_faz_sentido_em_erro(self, cliente, assincrono):
        doc_id = enviar(cliente).json()["documento_id"]  # estado "recebido"
        assert cliente.post(f"/documentos/{doc_id}/reprocessar").status_code == 409


class TestFlagDesligada:
    def test_sem_a_flag_o_upload_e_sincrono(self, cliente, monkeypatch):
        banco = mongomock.MongoClient()["fluxofiscal"]
        monkeypatch.setattr(main, "_repositorio", RepositorioMongo(banco["documentos"]))
        monkeypatch.setattr(main, "_auditoria", RepositorioAuditoriaMongo(banco["auditoria"]))
        monkeypatch.setattr(main, "MONGO_URL", "mongodb://fake:27017")
        monkeypatch.setattr(
            main, "esta_ativa", lambda nome, *, padrao=False, **_: nome == "documentos-persistidos"
        )

        resp = enviar(cliente)

        assert resp.status_code == 200
        assert resp.json()["estado"] == "extraido"
        assert resp.json()["structured_data"]["value"] == 1234.56
