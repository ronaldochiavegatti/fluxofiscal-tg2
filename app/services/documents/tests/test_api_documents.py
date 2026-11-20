"""Testes das rotas do Documents.

O serviço tem duas metades bem diferentes. `/upload` extrai e devolve, sem
gravar nada: é a tela de revisão do usuário. `/confirm` é o que persiste, e
persiste em *outro* serviço, por HTTP. Os testes de `/confirm` substituem essa
chamada — deixá-la real transformaria teste de unidade em teste de rede — mas
verificam exatamente o que seria enviado.
"""

import pytest

from app import main
from tests.conftest import EMAIL, _RespostaFalsa

NOTA = (
    "NOTA FISCAL\n"
    "CNPJ: 12.345.678/0001-95\n"
    "CNPJ 98.765.432/0001-10\n"
    "Emissao 17/06/2026\n"
    "Servico de manicure\n"
    "VALOR TOTAL R$ 1.234,56\n"
)


def enviar(cliente, conteudo: str = NOTA, nome: str = "nota.txt", **campos):
    return cliente.post(
        "/upload",
        files={"file": (nome, conteudo.encode("utf-8"), "text/plain")},
        data={"email": EMAIL, **campos},
    )


class TestHealth:
    def test_declara_que_esta_em_modo_demonstracao(self, cliente):
        """Sem chave do Gemini, o `/health` precisa dizer isso.

        É a única forma de o operador saber, olhando de fora, se a extração
        multimodal está ativa ou se o serviço está no caminho por regex.
        """
        corpo = cliente.get("/health").json()

        assert corpo["status"] == "ok"
        assert corpo["service"] == "documents"
        assert corpo["gemini_extraction"] is False


class TestUpload:
    def test_extrai_os_campos_da_nota(self, cliente):
        corpo = enviar(cliente).json()

        assert corpo["extracted_amount"] == 1234.56
        assert corpo["extraction_method"] == "regex"
        assert corpo["structured_data"]["date"] == "2026-06-17"
        assert corpo["structured_data"]["cnpj_emitente"] == "12.345.678/0001-95"

    def test_nao_grava_transacao_nenhuma(self, cliente):
        """O usuário revisa antes: `/upload` só lê, quem persiste é `/confirm`."""
        assert enviar(cliente).json()["limits_transaction"] is None

    def test_guarda_o_arquivo_com_nome_novo(self, cliente, pasta_de_upload):
        """O nome enviado pelo usuário não vira caminho no disco."""
        corpo = enviar(cliente, nome="../../etc/passwd.txt").json()

        assert corpo["original_filename"] == "../../etc/passwd.txt"
        assert corpo["stored_filename"] != "passwd.txt"
        assert (pasta_de_upload / corpo["stored_filename"]).is_file()
        assert len(list(pasta_de_upload.iterdir())) == 1

    def test_informa_o_tamanho_recebido(self, cliente):
        assert enviar(cliente).json()["size_bytes"] == len(NOTA.encode("utf-8"))

    def test_parte_sem_nome_de_arquivo_e_recusada(self, cliente):
        """Sem nome, o multipart deixa de ser arquivo e vira campo de texto.

        A recusa acontece na validação do contrato, antes da rota — o que
        significa que a checagem de `filename` dentro dela é rede de segurança
        para cliente fora do padrão, não o caminho normal.
        """
        resposta = cliente.post(
            "/upload",
            files={"file": ("", b"conteudo", "text/plain")},
            data={"email": EMAIL},
        )

        assert resposta.status_code == 422

    def test_sugere_venda_quando_o_usuario_e_o_emitente(self, cliente):
        corpo = enviar(cliente, user_cnpj="12.345.678/0001-95").json()

        assert corpo["structured_data"]["tx_type_sugerido"] == "venda"
        assert corpo["structured_data"]["tx_type_auto_detectado"] is True

    def test_sem_cnpj_do_usuario_nao_sugere(self, cliente):
        corpo = enviar(cliente).json()

        assert corpo["structured_data"]["tx_type_sugerido"] is None
        assert corpo["structured_data"]["tx_type_auto_detectado"] is False

    def test_arquivo_ilegivel_nao_derruba_a_rota(self, cliente):
        """Foto corrompida, PDF truncado, formato inesperado.

        Por padrão, a barreira de qualidade (#100) recusa a imagem que nem abre
        (422, motivo "invalida"). Se o usuário pede para ler mesmo assim, o
        upload responde com os campos vazios e confiança baixa, para preencher
        à mão — e não com erro 500.
        """
        recusada = cliente.post(
            "/upload",
            files={"file": ("foto.png", b"isto nao e um png", "image/png")},
            data={"email": EMAIL},
        )
        assert recusada.status_code == 422
        assert recusada.json()["detail"]["motivo"] == "invalida"

        resposta = cliente.post(
            "/upload",
            files={"file": ("foto.png", b"isto nao e um png", "image/png")},
            data={"email": EMAIL, "forcar_leitura": "true"},
        )

        assert resposta.status_code == 200
        assert resposta.json()["extracted_amount"] is None
        assert resposta.json()["structured_data"]["confidence"] == 0.2

    def test_ocr_de_imagem_alimenta_a_extracao(self, cliente, monkeypatch):
        """Com o OCR devolvendo texto, o caminho por imagem é o mesmo dos demais."""
        monkeypatch.setattr(main.processamento, "ocr_de_imagem", lambda _: NOTA)

        resposta = cliente.post(
            "/upload",
            files={"file": ("nota.png", b"bytes de imagem", "image/png")},
            # Bytes falsos: pula a barreira de qualidade, que tem testes próprios.
            data={"email": EMAIL, "forcar_leitura": "true"},
        )

        assert resposta.json()["extracted_amount"] == 1234.56

    def test_pdf_usa_a_primeira_pagina(self, cliente, monkeypatch):
        monkeypatch.setattr(main.processamento, "ocr_de_pdf_primeira_pagina", lambda _: NOTA)
        monkeypatch.setattr(main.processamento, "pdf_primeira_pagina_png", lambda _: None)

        resposta = cliente.post(
            "/upload",
            files={"file": ("nota.pdf", b"%PDF-falso", "application/pdf")},
            data={"email": EMAIL},
        )

        assert resposta.json()["extracted_amount"] == 1234.56
        assert resposta.json()["extraction_method"] == "regex"


class TestConfirmacao:
    def _confirmar(self, cliente, **campos):
        corpo = {
            "email": EMAIL,
            "amount": 1234.56,
            "tx_date": "2026-06-17",
            "tx_type": "venda",
            "source_filename": "nota.pdf",
            "ocr_text": NOTA,
            **campos,
        }
        return cliente.post("/confirm", json=corpo)

    def test_registra_a_transacao_no_limits(self, cliente, limits_falso):
        resposta = self._confirmar(cliente)

        assert resposta.status_code == 200
        enviado = next(e for e in limits_falso if e["url"].endswith("/transactions"))
        assert enviado["json"]["amount"] == 1234.56
        assert enviado["json"]["tx_type"] == "venda"
        assert enviado["json"]["tx_date"] == "2026-06-17"
        assert enviado["json"]["source"] == "upload:nota.pdf"

    def test_indexa_o_texto_no_agente(self, cliente, limits_falso):
        self._confirmar(cliente, description="Servico de manicure")

        indexado = next(e for e in limits_falso if e["url"].endswith("/index-document"))
        assert indexado["json"]["email"] == EMAIL
        assert "Tipo: venda" in indexado["json"]["content"]

    def test_tipo_confirmado_pelo_usuario_prevalece(self, cliente, limits_falso):
        """A sugestão automática pode estar errada; a escolha do usuário, não."""
        self._confirmar(cliente, tx_type="compra")

        enviado = next(e for e in limits_falso if e["url"].endswith("/transactions"))
        assert enviado["json"]["tx_type"] == "compra"

    def test_tipo_invalido_e_recusado(self, cliente, limits_falso):
        resposta = self._confirmar(cliente, tx_type="doacao")

        assert resposta.status_code == 400
        assert limits_falso == []

    def test_falha_do_limits_vira_502(self, cliente, monkeypatch):
        """O documento não foi registrado, e o usuário precisa saber disso."""
        monkeypatch.setattr(
            main.httpx,
            "post",
            lambda *a, **k: _RespostaFalsa(500, texto="banco indisponivel"),
        )

        resposta = self._confirmar(cliente)

        assert resposta.status_code == 502

    def test_indexacao_indisponivel_nao_impede_a_confirmacao(self, cliente, monkeypatch):
        """Comportamento atual, e é uma dívida conhecida.

        A transação é gravada e o documento simplesmente nunca chega ao RAG,
        sem que nada registre a perda. O `except httpx.RequestError: pass` é
        exatamente o defeito que a US-46 substitui por Outbox — este teste
        existe para fixar o comportamento até lá, não para abençoá-lo.
        """
        chamadas = []

        def _post(url, json, timeout=5.0):
            chamadas.append(url)
            if url.endswith("/index-document"):
                raise main.httpx.ConnectError("agente fora do ar")
            return _RespostaFalsa(200, {"id": 1, **json})

        monkeypatch.setattr(main.httpx, "post", _post)

        resposta = self._confirmar(cliente)

        assert resposta.status_code == 200
        assert any(url.endswith("/index-document") for url in chamadas)

    def test_documento_sem_texto_nao_e_indexado(self, cliente, limits_falso):
        self._confirmar(cliente, ocr_text=None, description=None)

        assert not [e for e in limits_falso if e["url"].endswith("/index-document")]


class TestReset:
    def test_apaga_os_arquivos_enviados(self, cliente, pasta_de_upload):
        enviar(cliente)
        enviar(cliente)

        resposta = cliente.delete("/reset")

        assert resposta.json() == {"files_deleted": 2}
        assert list(pasta_de_upload.iterdir()) == []

    def test_pasta_vazia_nao_e_erro(self, cliente):
        assert cliente.delete("/reset").json() == {"files_deleted": 0}

    def test_com_minio_ativo_apaga_tambem_o_bucket(self, cliente, monkeypatch):
        """Com `storage-minio` ligada os uploads vão para o bucket; o reset
        que só limpava a pasta local deixava todos eles lá."""

        class Bucket:
            nome = "minio"

            def apagar_tudo(self):
                return 5

        monkeypatch.setattr(main, "obter_armazenamento", lambda: Bucket())

        assert cliente.delete("/reset").json() == {"files_deleted": 5}


@pytest.mark.parametrize("rota", ["/upload", "/confirm"])
def test_rotas_de_escrita_recusam_email_invalido(cliente, limits_falso, rota):
    if rota == "/upload":
        resposta = cliente.post(
            "/upload",
            files={"file": ("nota.txt", NOTA.encode("utf-8"), "text/plain")},
            data={"email": "nao-e-email"},
        )
    else:
        resposta = cliente.post(
            "/confirm",
            json={
                "email": "nao-e-email",
                "amount": 1.0,
                "tx_date": "2026-01-01",
                "tx_type": "venda",
            },
        )

    assert resposta.status_code == 422
