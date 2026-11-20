"""Persistência e deduplicação de documentos (US-20).

Cenários Gherkin:
  - Reenvio reconhecido: mesmo arquivo -> documento anterior, sem reprocessar,
    resposta marca `duplicado`.
  - Histórico sobrevive à troca de dispositivo: GET /documentos lista o que
    está no Mongo, não no navegador.
"""

import mongomock
import pytest

from app import main
from app.auditoria import RepositorioAuditoriaMongo
from app.repositorio import RepositorioMongo
from tests.conftest import EMAIL

NOTA = b"NOTA FISCAL\nVALOR TOTAL R$ 1.234,56\nEmissao 17/06/2026\n"


def enviar(cliente, conteudo: bytes = NOTA, nome: str = "nota.txt"):
    return cliente.post(
        "/upload",
        files={"file": (nome, conteudo, "text/plain")},
        data={"email": EMAIL},
    )


# ---------------------------------------------------------------------------
# Flag desligada — sem banco, como antes
# ---------------------------------------------------------------------------


class TestSemPersistencia:
    def test_upload_nao_traz_documento_id(self, cliente):
        corpo = enviar(cliente).json()
        assert "documento_id" not in corpo

    def test_listar_documentos_responde_409(self, cliente):
        resp = cliente.get("/documentos", params={"email": EMAIL})
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Flag ligada — MongoDB (mongomock)
# ---------------------------------------------------------------------------


@pytest.fixture
def persistencia(monkeypatch: pytest.MonkeyPatch) -> RepositorioMongo:
    banco = mongomock.MongoClient()["fluxofiscal"]
    repo = RepositorioMongo(banco["documentos"])
    monkeypatch.setattr(main, "_repositorio", repo)
    monkeypatch.setattr(main, "_auditoria", RepositorioAuditoriaMongo(banco["auditoria"]))
    monkeypatch.setattr(main, "MONGO_URL", "mongodb://fake:27017")
    monkeypatch.setattr(
        main,
        "esta_ativa",
        lambda nome, *, padrao=False, **_: nome == "documentos-persistidos",
    )
    return repo


class TestComPersistencia:
    def test_upload_persiste_e_devolve_id(self, cliente, persistencia):
        corpo = enviar(cliente).json()

        assert corpo["duplicado"] is False
        assert corpo["estado"] == "extraido"
        assert persistencia.por_id(corpo["documento_id"]) is not None

    def test_reenvio_e_reconhecido_sem_reprocessar(self, cliente, persistencia, monkeypatch):
        primeiro = enviar(cliente).json()

        # Se o reenvio reprocessasse, chamaria a extração de novo. Trava o
        # caminho de extração: se for chamado, o teste quebra.
        def _nao_deveria_extrair(*_a, **_k):
            raise AssertionError("reenvio reprocessou o arquivo")

        monkeypatch.setattr(main, "regex_extract", _nao_deveria_extrair)
        monkeypatch.setattr(main, "gemini_extract_from_text", _nao_deveria_extrair)

        segundo = enviar(cliente).json()

        assert segundo["duplicado"] is True
        assert segundo["documento_id"] == primeiro["documento_id"]
        assert segundo["structured_data"]["value"] == primeiro["structured_data"]["value"]

    def test_arquivo_diferente_nao_e_duplicado(self, cliente, persistencia):
        a = enviar(cliente, b"nota A R$ 1,00").json()
        b = enviar(cliente, b"nota B R$ 2,00").json()

        assert a["documento_id"] != b["documento_id"]
        assert b["duplicado"] is False

    def test_historico_sobrevive_e_lista_do_mongo(self, cliente, persistencia):
        for i in range(3):
            enviar(cliente, f"nota {i} R$ {i + 1},00".encode())

        lista = cliente.get("/documentos", params={"email": EMAIL}).json()

        assert len(lista) == 3
        assert all(d["estado"] == "extraido" for d in lista)
        assert "ocr" not in lista[0]  # o resumo não carrega o texto de OCR inteiro

    def test_detalhe_do_documento(self, cliente, persistencia):
        doc_id = enviar(cliente).json()["documento_id"]

        resp = cliente.get(f"/documentos/{doc_id}")

        assert resp.status_code == 200
        assert resp.json()["documento_id"] == doc_id
        assert resp.json()["ocr_text"]
        assert "historico" in resp.json()

    def test_detalhe_inexistente_da_404(self, cliente, persistencia):
        assert cliente.get("/documentos/nao-existe").status_code == 404


# ---------------------------------------------------------------------------
# Reset da demo — o histórico some junto com as transações
# ---------------------------------------------------------------------------


class TestResetComPersistencia:
    def test_reset_com_email_apaga_o_historico_do_usuario(self, cliente, persistencia):
        enviar(cliente, b"nota A R$ 1,00")
        enviar(cliente, b"nota B R$ 2,00")

        resposta = cliente.delete("/reset", params={"email": EMAIL})

        assert resposta.json()["documentos_apagados"] == 2
        assert cliente.get("/documentos", params={"email": EMAIL}).json() == []

    def test_reset_nao_apaga_o_historico_de_outro_usuario(self, cliente, persistencia):
        cliente.post(
            "/upload",
            files={"file": ("nota.txt", NOTA, "text/plain")},
            data={"email": "outra@mei.com.br"},
        )

        cliente.delete("/reset", params={"email": EMAIL})

        assert len(persistencia.listar("outra@mei.com.br")) == 1

    def test_reset_sem_email_mantem_a_resposta_antiga(self, cliente, persistencia):
        enviar(cliente)

        resposta = cliente.delete("/reset").json()

        assert "documentos_apagados" not in resposta
        assert len(persistencia.listar(EMAIL)) == 1


class TestResetSemPersistencia:
    def test_reset_com_email_e_flag_desligada_nao_apaga_nada(self, cliente):
        resposta = cliente.delete("/reset", params={"email": EMAIL})

        assert resposta.status_code == 200
        assert resposta.json()["documentos_apagados"] == 0


# ---------------------------------------------------------------------------
# Confirmação — o documento sai de "extraido" e guarda o que foi confirmado
# ---------------------------------------------------------------------------


def confirmar(cliente, doc_id: str, amount: float):
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


class TestConfirmacaoPersistida:
    def test_confirmar_muda_o_estado_para_confirmado(self, cliente, persistencia, limits_falso):
        doc_id = enviar(cliente).json()["documento_id"]

        assert confirmar(cliente, doc_id, 1234.56).status_code == 200

        lista = cliente.get("/documentos", params={"email": EMAIL}).json()
        assert lista[0]["estado"] == "confirmado"

    def test_correcao_fica_em_confirmacao_e_a_extracao_original_e_preservada(
        self, cliente, persistencia, limits_falso
    ):
        doc_id = enviar(cliente).json()["documento_id"]

        confirmar(cliente, doc_id, 1250.0)

        item = cliente.get("/documentos", params={"email": EMAIL}).json()[0]
        assert item["extracao"]["campos"]["value"] == 1234.56
        assert item["confirmacao"]["campos"]["value"] == 1250.0
        assert item["confirmacao"]["transacao_limits_id"] == 1

    def test_documento_so_extraido_nao_tem_confirmacao(self, cliente, persistencia):
        enviar(cliente)

        item = cliente.get("/documentos", params={"email": EMAIL}).json()[0]
        assert item["estado"] == "extraido"
        assert item["confirmacao"] is None

    def test_confirmar_sem_documento_id_nao_quebra(self, cliente, persistencia, limits_falso):
        enviar(cliente)

        resposta = cliente.post(
            "/confirm",
            json={"email": EMAIL, "amount": 10.0, "tx_date": "2026-06-17", "tx_type": "venda"},
        )

        assert resposta.status_code == 200
        lista = cliente.get("/documentos", params={"email": EMAIL}).json()
        assert lista[0]["estado"] == "extraido"


# ---------------------------------------------------------------------------
# Nota repetida (#93) — o upload avisa quando a nota já foi salva
# ---------------------------------------------------------------------------


def _doc_confirmado(repo: RepositorioMongo, *, valor, data, cnpj, hash_sha256):
    doc = repo.salvar(_novo(valor=valor, data=data, cnpj=cnpj, hash_sha256=hash_sha256))
    repo.marcar_confirmado(
        doc["_id"],
        campos={"value": valor, "date": data, "cnpj_emitente": cnpj, "tx_type": "venda"},
        transacao_limits_id=1,
    )
    return doc["_id"]


class TestNotaRepetida:
    def test_primeiro_envio_nao_tem_repeticao(self, cliente, persistencia):
        assert enviar(cliente).json()["repeticoes"] == []

    def test_reenvio_de_arquivo_nao_salvo_nao_avisa(self, cliente, persistencia):
        # Abandonado na conferência: não entrou no faturamento, não duplica nada.
        enviar(cliente)
        assert enviar(cliente).json()["repeticoes"] == []

    def test_reenvio_do_mesmo_arquivo_ja_salvo_avisa(self, cliente, persistencia, limits_falso):
        doc_id = enviar(cliente).json()["documento_id"]
        confirmar(cliente, doc_id, 1234.56)

        repeticoes = enviar(cliente).json()["repeticoes"]

        assert len(repeticoes) == 1
        assert repeticoes[0]["documento_id"] == doc_id
        assert repeticoes[0]["mesmo_arquivo"] is True
        assert repeticoes[0]["valor"] == 1234.56
        assert repeticoes[0]["data"] == "2026-06-17"

    def test_outro_arquivo_da_mesma_nota_avisa(self, cliente, persistencia, limits_falso):
        primeiro = enviar(cliente).json()
        confirmar(cliente, primeiro["documento_id"], 1234.56)

        # Mesmo valor e data, arquivo diferente (outra foto da mesma nota).
        segundo = enviar(cliente, NOTA + b"\nfoto tirada de novo").json()

        assert segundo["duplicado"] is False
        assert [r["documento_id"] for r in segundo["repeticoes"]] == [primeiro["documento_id"]]
        assert segundo["repeticoes"][0]["mesmo_arquivo"] is False

    def test_valor_confirmado_diferente_nao_avisa(self, cliente, persistencia, limits_falso):
        primeiro = enviar(cliente).json()
        confirmar(cliente, primeiro["documento_id"], 999.0)  # usuário corrigiu o valor

        assert enviar(cliente, NOTA + b"\noutra").json()["repeticoes"] == []

    def test_cnpj_emitente_diferente_nao_e_a_mesma_nota(self, persistencia):
        _doc_confirmado(
            persistencia, valor=100.0, data="2026-03-01", cnpj="11.111.111/0001-11", hash_sha256="a"
        )
        novo = persistencia.salvar(
            _novo(valor=100.0, data="2026-03-01", cnpj="22222222000122", hash_sha256="b")
        )

        assert main._repeticoes(persistencia, novo) == []

    def test_cnpj_com_e_sem_mascara_e_a_mesma_nota(self, persistencia):
        antigo = _doc_confirmado(
            persistencia, valor=100.0, data="2026-03-01", cnpj="11.111.111/0001-11", hash_sha256="a"
        )
        novo = persistencia.salvar(
            _novo(valor=100.0, data="2026-03-01", cnpj="11111111000111", hash_sha256="b")
        )

        assert [r["documento_id"] for r in main._repeticoes(persistencia, novo)] == [antigo]

    def test_cnpj_nao_lido_ainda_avisa(self, persistencia):
        antigo = _doc_confirmado(
            persistencia, valor=100.0, data="2026-03-01", cnpj="11.111.111/0001-11", hash_sha256="a"
        )
        novo = persistencia.salvar(
            _novo(valor=100.0, data="2026-03-01", cnpj=None, hash_sha256="b")
        )

        assert [r["documento_id"] for r in main._repeticoes(persistencia, novo)] == [antigo]

    def test_sem_valor_ou_data_nao_compara(self, persistencia):
        _doc_confirmado(persistencia, valor=100.0, data="2026-03-01", cnpj=None, hash_sha256="a")
        novo = persistencia.salvar(_novo(valor=None, data="2026-03-01", cnpj=None, hash_sha256="b"))

        assert main._repeticoes(persistencia, novo) == []

    def test_nao_compara_com_nota_de_outro_usuario(self, persistencia):
        _doc_confirmado(persistencia, valor=100.0, data="2026-03-01", cnpj=None, hash_sha256="a")
        novo = persistencia.salvar(
            _novo(valor=100.0, data="2026-03-01", cnpj=None, hash_sha256="b", email="outra@mei.com")
        )

        assert main._repeticoes(persistencia, novo) == []

    def test_detalhe_do_documento_traz_as_repeticoes(self, cliente, persistencia, limits_falso):
        primeiro = enviar(cliente).json()["documento_id"]
        confirmar(cliente, primeiro, 1234.56)
        segundo = enviar(cliente, NOTA + b"\nde novo").json()["documento_id"]

        detalhe = cliente.get(f"/documentos/{segundo}").json()

        assert [r["documento_id"] for r in detalhe["repeticoes"]] == [primeiro]

    def test_sem_persistencia_nao_ha_repeticoes(self, cliente):
        assert "repeticoes" not in enviar(cliente).json()


class TestHistoricoDaNotaRepetida:
    """Continuar depois do aviso (#93): a repetição aparece no histórico,
    sinalizada, em vez de sumir dentro do registro da primeira nota."""

    def test_mesmo_arquivo_confirmado_de_novo_ganha_linha_propria(
        self, cliente, persistencia, limits_falso
    ):
        original = enviar(cliente).json()["documento_id"]
        confirmar(cliente, original, 1234.56)

        reenvio = enviar(cliente).json()
        assert reenvio["documento_id"] == original  # o upload ainda acha o original
        resposta = confirmar(cliente, original, 1234.56).json()

        assert resposta["documento_id"] != original
        lista = cliente.get("/documentos", params={"email": EMAIL}).json()
        assert len(lista) == 2
        por_id = {d["id"]: d for d in lista}
        assert por_id[original]["repeticao_de"] == []
        assert por_id[resposta["documento_id"]]["repeticao_de"] == [original]
        assert por_id[resposta["documento_id"]]["estado"] == "confirmado"
        assert por_id[resposta["documento_id"]]["nome_original"] == "nota.txt"

    def test_primeira_confirmacao_continua_no_mesmo_registro(
        self, cliente, persistencia, limits_falso
    ):
        doc_id = enviar(cliente).json()["documento_id"]

        assert confirmar(cliente, doc_id, 1234.56).json()["documento_id"] == doc_id
        assert cliente.get("/documentos", params={"email": EMAIL}).json()[0]["repeticao_de"] == []

    def test_outra_foto_da_mesma_nota_fica_sinalizada(self, cliente, persistencia, limits_falso):
        primeiro = enviar(cliente).json()["documento_id"]
        confirmar(cliente, primeiro, 1234.56)
        segundo = enviar(cliente, NOTA + b"\nfoto 2").json()["documento_id"]

        confirmar(cliente, segundo, 1234.56)

        por_id = {d["id"]: d for d in cliente.get("/documentos", params={"email": EMAIL}).json()}
        assert por_id[segundo]["repeticao_de"] == [primeiro]

    def test_correcao_na_conferencia_desfaz_a_repeticao(self, cliente, persistencia, limits_falso):
        primeiro = enviar(cliente).json()["documento_id"]
        confirmar(cliente, primeiro, 1234.56)
        segundo = enviar(cliente, NOTA + b"\nfoto 2").json()["documento_id"]

        confirmar(cliente, segundo, 99.0)  # o usuário corrigiu: não é a mesma nota

        por_id = {d["id"]: d for d in cliente.get("/documentos", params={"email": EMAIL}).json()}
        assert por_id[segundo]["repeticao_de"] == []

    def test_terceiro_envio_aponta_as_duas_anteriores(self, cliente, persistencia, limits_falso):
        original = enviar(cliente).json()["documento_id"]
        confirmar(cliente, original, 1234.56)
        enviar(cliente)
        copia = confirmar(cliente, original, 1234.56).json()["documento_id"]

        repeticoes = enviar(cliente).json()["repeticoes"]

        assert {r["documento_id"] for r in repeticoes} == {original, copia}
        assert all(r["mesmo_arquivo"] for r in repeticoes)

    def test_documento_inexistente_nao_quebra_a_confirmacao(
        self, cliente, persistencia, limits_falso
    ):
        resposta = confirmar(cliente, "nao-existe", 10.0)

        assert resposta.status_code == 200
        assert resposta.json()["documento_id"] == "nao-existe"


def _novo(*, valor, data, cnpj, hash_sha256, email=EMAIL):
    from app.repositorio import novo_documento

    return novo_documento(
        email=email,
        nome_original="nova.pdf",
        chave_armazenamento=f"local/{hash_sha256}.pdf",
        tamanho_bytes=10,
        tipo_mime="application/pdf",
        hash_sha256=hash_sha256,
        ocr_texto="",
        ocr_motor="tesseract",
        extracao_metodo="regex",
        extracao_modelo=None,
        campos={"value": valor, "date": data, "cnpj_emitente": cnpj},
        confianca=0.9,
    )


# ---------------------------------------------------------------------------
# Correção no detalhe da nota (#95) — a nota salva continua editável
# ---------------------------------------------------------------------------


@pytest.fixture
def limits_patch(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    from tests.conftest import _RespostaFalsa

    enviados: list[dict] = []

    def _patch(url: str, json: dict, timeout: float = 5.0):
        enviados.append({"url": url, "json": json})
        return _RespostaFalsa(200, {"id": 1, **json})

    monkeypatch.setattr(main.httpx, "patch", _patch)
    return enviados


def corrigir(cliente, doc_id: str, **mudancas):
    corpo = {"amount": 1300.0, "tx_date": "2026-06-18", "tx_type": "venda"} | mudancas
    return cliente.patch(f"/documentos/{doc_id}", json=corpo)


class TestCorrecaoDaNota:
    def test_detalhe_traz_o_que_foi_confirmado(self, cliente, persistencia, limits_falso):
        doc_id = enviar(cliente).json()["documento_id"]
        confirmar(cliente, doc_id, 1250.0)

        detalhe = cliente.get(f"/documentos/{doc_id}").json()

        assert detalhe["confirmacao"]["campos"]["value"] == 1250.0
        assert detalhe["confirmacao"]["transacao_limits_id"] == 1
        assert detalhe["original_filename"] == "nota.txt"

    def test_corrigir_atualiza_o_limits_e_o_historico(
        self, cliente, persistencia, limits_falso, limits_patch
    ):
        doc_id = enviar(cliente).json()["documento_id"]
        confirmar(cliente, doc_id, 1250.0)

        resposta = corrigir(cliente, doc_id, tx_type="compra", description="bolo")

        assert resposta.status_code == 200
        assert limits_patch == [
            {
                "url": limits_patch[0]["url"],
                "json": {"amount": 1300.0, "tx_date": "2026-06-18", "tx_type": "compra"},
            }
        ]
        assert limits_patch[0]["url"].endswith("/transactions/1")
        campos = resposta.json()["confirmacao"]["campos"]
        assert campos["value"] == 1300.0
        assert campos["tx_type"] == "compra"
        assert campos["description"] == "bolo"
        item = cliente.get("/documentos", params={"email": EMAIL}).json()[0]
        assert item["confirmacao"]["campos"]["value"] == 1300.0
        assert item["extracao"]["campos"]["value"] == 1234.56  # leitura original preservada
        assert item["confirmacao"]["transacao_limits_id"] == 1

    def test_correcao_vai_para_a_trilha(self, cliente, persistencia, limits_falso, limits_patch):
        doc_id = enviar(cliente).json()["documento_id"]
        confirmar(cliente, doc_id, 1250.0)
        corrigir(cliente, doc_id)

        registros = cliente.get(f"/documentos/{doc_id}/auditoria").json()["registros"]

        ultimo = registros[-1]
        assert ultimo["acao"] == "documento.corrigido"
        assert ultimo["antes"]["campos"]["value"] == 1250.0
        assert ultimo["depois"]["value"] == 1300.0

    def test_limits_recusando_nao_muda_o_documento(
        self, cliente, persistencia, limits_falso, monkeypatch
    ):
        from tests.conftest import _RespostaFalsa

        doc_id = enviar(cliente).json()["documento_id"]
        confirmar(cliente, doc_id, 1250.0)
        monkeypatch.setattr(
            main.httpx, "patch", lambda *a, **k: _RespostaFalsa(404, texto="não achei")
        )

        assert corrigir(cliente, doc_id).status_code == 502
        detalhe = cliente.get(f"/documentos/{doc_id}").json()
        assert detalhe["confirmacao"]["campos"]["value"] == 1250.0

    def test_nota_so_lida_nao_e_corrigida_por_aqui(self, cliente, persistencia):
        doc_id = enviar(cliente).json()["documento_id"]
        assert corrigir(cliente, doc_id).status_code == 409

    def test_tipo_invalido(self, cliente, persistencia, limits_falso):
        doc_id = enviar(cliente).json()["documento_id"]
        confirmar(cliente, doc_id, 1250.0)
        assert corrigir(cliente, doc_id, tx_type="doacao").status_code == 400

    def test_documento_inexistente(self, cliente, persistencia):
        assert corrigir(cliente, "nao-existe").status_code == 404

    def test_sem_persistencia(self, cliente):
        assert corrigir(cliente, "qualquer").status_code == 409

    def test_valor_zero_e_recusado(self, cliente, persistencia, limits_falso):
        doc_id = enviar(cliente).json()["documento_id"]
        confirmar(cliente, doc_id, 1250.0)
        assert corrigir(cliente, doc_id, amount=0).status_code == 422


# ---------------------------------------------------------------------------
# Apagar a nota (#96) — lançamento, registro e arquivo
# ---------------------------------------------------------------------------


@pytest.fixture
def limits_delete(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    from tests.conftest import _RespostaFalsa

    chamadas: list[str] = []

    def _delete(url: str, timeout: float = 5.0):
        chamadas.append(url)
        return _RespostaFalsa(200, {"removida": True})

    monkeypatch.setattr(main.httpx, "delete", _delete)
    return chamadas


def apagar(cliente, doc_id: str):
    return cliente.delete(f"/documentos/{doc_id}")


class TestApagarNota:
    def test_nota_salva_sai_do_historico_do_limits_e_do_armazenamento(
        self, cliente, persistencia, limits_falso, limits_delete
    ):
        doc_id = enviar(cliente).json()["documento_id"]
        confirmar(cliente, doc_id, 1234.56)
        chave = persistencia.por_id(doc_id)["arquivo"]["chave_armazenamento"]
        assert main.obter_armazenamento().existe(chave)

        resposta = apagar(cliente, doc_id)

        assert resposta.status_code == 200
        assert resposta.json() == {
            "documento_id": doc_id,
            "transacao_removida": True,
            "arquivo_removido": True,
        }
        assert limits_delete[0].endswith("/transactions/1")
        assert cliente.get("/documentos", params={"email": EMAIL}).json() == []
        assert cliente.get(f"/documentos/{doc_id}").status_code == 404
        assert not main.obter_armazenamento().existe(chave)

    def test_nota_so_lida_nao_chama_o_limits(self, cliente, persistencia, limits_delete):
        doc_id = enviar(cliente).json()["documento_id"]

        resposta = apagar(cliente, doc_id)

        assert resposta.json()["transacao_removida"] is False
        assert limits_delete == []
        assert cliente.get("/documentos", params={"email": EMAIL}).json() == []

    def test_limits_recusando_nao_apaga_nada(
        self, cliente, persistencia, limits_falso, monkeypatch
    ):
        from tests.conftest import _RespostaFalsa

        doc_id = enviar(cliente).json()["documento_id"]
        confirmar(cliente, doc_id, 1234.56)
        monkeypatch.setattr(main.httpx, "delete", lambda *a, **k: _RespostaFalsa(500, texto="x"))

        assert apagar(cliente, doc_id).status_code == 502
        assert persistencia.por_id(doc_id) is not None

    def test_transacao_ja_apagada_no_limits_nao_impede(
        self, cliente, persistencia, limits_falso, monkeypatch
    ):
        from tests.conftest import _RespostaFalsa

        doc_id = enviar(cliente).json()["documento_id"]
        confirmar(cliente, doc_id, 1234.56)
        monkeypatch.setattr(main.httpx, "delete", lambda *a, **k: _RespostaFalsa(404))

        resposta = apagar(cliente, doc_id)

        assert resposta.status_code == 200
        assert resposta.json()["transacao_removida"] is False
        assert persistencia.por_id(doc_id) is None

    def test_apagar_a_repeticao_mantem_o_arquivo_da_original(
        self, cliente, persistencia, limits_falso, limits_delete
    ):
        original = enviar(cliente).json()["documento_id"]
        confirmar(cliente, original, 1234.56)
        enviar(cliente)
        copia = confirmar(cliente, original, 1234.56).json()["documento_id"]
        chave = persistencia.por_id(original)["arquivo"]["chave_armazenamento"]

        resposta = apagar(cliente, copia)

        assert resposta.json()["arquivo_removido"] is False
        assert main.obter_armazenamento().existe(chave)
        assert [d["id"] for d in cliente.get("/documentos", params={"email": EMAIL}).json()] == [
            original
        ]

    def test_remocao_fica_na_trilha(self, cliente, persistencia, limits_falso, limits_delete):
        doc_id = enviar(cliente).json()["documento_id"]
        confirmar(cliente, doc_id, 1250.0)

        apagar(cliente, doc_id)

        registros = cliente.get(f"/documentos/{doc_id}/auditoria").json()["registros"]
        assert registros[-1]["acao"] == "documento.apagado"
        assert registros[-1]["antes"]["campos"]["value"] == 1250.0
        assert registros[-1]["depois"]["transacao_removida"] is True

    def test_arquivo_que_nao_sai_do_armazenamento_nao_derruba(
        self, cliente, persistencia, monkeypatch
    ):
        doc_id = enviar(cliente).json()["documento_id"]

        class _Quebrado:
            def apagar(self, chave):
                raise OSError("disco")

        monkeypatch.setattr(main, "obter_armazenamento", lambda: _Quebrado())

        resposta = apagar(cliente, doc_id)

        assert resposta.status_code == 200
        assert resposta.json()["arquivo_removido"] is False

    def test_documento_inexistente(self, cliente, persistencia):
        assert apagar(cliente, "nao-existe").status_code == 404

    def test_sem_persistencia(self, cliente):
        assert apagar(cliente, "qualquer").status_code == 409
