"""Rotas de armazenamento e acesso a arquivo (US-19).

Os cenários Gherkin da história:
  - Download por URL temporária de 15 min, sem o arquivo passar pelo serviço.
  - URL expirada não abre  -> enforcement é do S3; aqui verificamos ExpiresIn.
  - Caminho não expõe dado pessoal  -> a chave usa hash do e-mail.
"""

import pytest

from app import armazenamento, main
from tests.conftest import EMAIL
from tests.test_armazenamento import _S3Falso


def enviar_txt(cliente, nome="nota.txt"):
    return cliente.post(
        "/upload",
        files={"file": (nome, b"NOTA\nVALOR R$ 10,00\n", "text/plain")},
        data={"email": EMAIL},
    )


# ---------------------------------------------------------------------------
# Flag desligada (padrão) — sistema de arquivos local, como sempre
# ---------------------------------------------------------------------------


class TestModoLocal:
    def test_upload_grava_no_disco_e_declara_o_modo(self, cliente, pasta_de_upload):
        corpo = enviar_txt(cliente).json()

        assert corpo["armazenamento"] == "local"
        assert corpo["chave_armazenamento"] == corpo["stored_filename"]
        assert (pasta_de_upload / corpo["stored_filename"]).is_file()

    def test_url_temporaria_aponta_para_a_rota_local(self, cliente):
        chave = enviar_txt(cliente).json()["chave_armazenamento"]

        resp = cliente.get("/url", params={"chave": chave, "email": EMAIL})

        assert resp.status_code == 200
        assert resp.json() == {
            "url": f"/documents/arquivos/{chave}",
            "expira_em_segundos": 900,
        }

    def test_baixa_o_arquivo_local(self, cliente):
        chave = enviar_txt(cliente).json()["chave_armazenamento"]

        resp = cliente.get(f"/arquivos/{chave}")

        assert resp.status_code == 200
        assert resp.content == b"NOTA\nVALOR R$ 10,00\n"

    def test_url_de_arquivo_inexistente_da_404(self, cliente):
        resp = cliente.get("/url", params={"chave": "nao-existe.txt", "email": EMAIL})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Flag ligada — MinIO (cliente S3 falso)
# ---------------------------------------------------------------------------


@pytest.fixture
def minio_falso(monkeypatch: pytest.MonkeyPatch) -> _S3Falso:
    s3 = _S3Falso()
    monkeypatch.setattr(main, "_minio_cliente", None)
    monkeypatch.setattr(main, "_minio_bucket_pronto", False)
    monkeypatch.setattr(main, "criar_cliente_minio", lambda: s3)
    monkeypatch.setattr(
        main, "esta_ativa", lambda nome, *, padrao=False, **_: nome == "storage-minio"
    )
    return s3


class TestModoMinio:
    def test_upload_manda_pro_minio_com_criptografia_e_limpa_o_local(
        self, cliente, minio_falso, pasta_de_upload
    ):
        corpo = enviar_txt(cliente).json()

        assert corpo["armazenamento"] == "minio"
        # chave = <hash-email>/<ano>/<mes>/<uuid>.txt — sem e-mail em texto
        assert corpo["chave_armazenamento"].startswith(armazenamento.hash_email(EMAIL) + "/")
        assert "marcia" not in corpo["chave_armazenamento"]
        assert minio_falso.puts[0]["ServerSideEncryption"] == "AES256"
        # a cópia local usada para o OCR foi removida
        assert not (pasta_de_upload / corpo["stored_filename"]).exists()

    def test_url_pre_assinada_de_15_minutos(self, cliente, minio_falso):
        chave = enviar_txt(cliente).json()["chave_armazenamento"]

        resp = cliente.get("/url", params={"chave": chave, "email": EMAIL})

        assert resp.status_code == 200
        assert resp.json()["expira_em_segundos"] == 900
        assert minio_falso.presigns[0]["expira"] == 900
        assert "http://minio:9000/" in resp.json()["url"]

    def test_chave_de_outro_email_e_negada(self, cliente, minio_falso):
        chave = enviar_txt(cliente).json()["chave_armazenamento"]

        resp = cliente.get("/url", params={"chave": chave, "email": "douglas@outro.com"})

        assert resp.status_code == 403
