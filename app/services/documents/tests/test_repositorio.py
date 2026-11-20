"""Repositório de documentos no MongoDB (US-20, ADR-0005).

Roda contra o `mongomock`, que enforce o índice único — então o teste de
deduplicação exercita o mesmo caminho que a produção, sem subir o Mongo.
"""

from datetime import UTC, datetime

import mongomock

from app.repositorio import RepositorioMongo, novo_documento

EMAIL = "marcia@mei.com.br"


def _repo() -> RepositorioMongo:
    return RepositorioMongo(mongomock.MongoClient()["fluxofiscal"]["documentos"])


def _doc(email: str = EMAIL, hash_: str = "abc123", **over) -> dict:
    d = novo_documento(
        email=email,
        nome_original="nota.txt",
        chave_armazenamento="chave/2026/09/x.txt",
        tamanho_bytes=42,
        tipo_mime="text/plain",
        hash_sha256=hash_,
        ocr_texto="texto do ocr",
        ocr_motor="tesseract",
        extracao_metodo="regex",
        extracao_modelo=None,
        campos={"value": 10.0, "date": "2026-09-01"},
        confianca=0.55,
    )
    d.update(over)
    return d


def test_novo_documento_tem_o_formato_do_adr():
    d = _doc()
    assert d["estado"] == "extraido"
    assert d["arquivo"]["hash_sha256"] == "abc123"
    assert d["transacao_limits_id"] is None
    assert d["historico"][0]["evento"] == "extraido"
    assert "value" in d["extracao"]["campos"]


def test_salva_e_recupera_por_id():
    repo = _repo()
    doc = repo.salvar(_doc())
    achado = repo.por_id(doc["_id"])
    assert achado is not None
    assert achado["_id"] == doc["_id"]
    assert repo.por_id("nao-existe") is None


def test_por_hash_e_por_usuario():
    repo = _repo()
    d1 = repo.salvar(_doc(hash_="h1"))

    assert repo.por_hash(EMAIL, "h1")["_id"] == d1["_id"]
    assert repo.por_hash(EMAIL, "outro-hash") is None
    assert repo.por_hash("douglas@outro.com", "h1") is None


def test_indice_unico_deduplica_reenvio():
    repo = _repo()
    primeiro = repo.salvar(_doc(hash_="mesmo"))
    segundo = repo.salvar(_doc(hash_="mesmo"))  # _id novo, mesmo hash+email

    # salvar devolve o registro já existente em vez de inserir uma segunda cópia
    assert segundo["_id"] == primeiro["_id"]
    assert repo.listar(EMAIL) == [primeiro] or len(repo.listar(EMAIL)) == 1


def test_mesmo_arquivo_de_usuarios_diferentes_nao_colide():
    repo = _repo()
    repo.salvar(_doc(email="a@x.com", hash_="h"))
    b = repo.salvar(_doc(email="b@x.com", hash_="h"))
    assert b["_id"] is not None
    assert len(repo.listar("a@x.com")) == 1
    assert len(repo.listar("b@x.com")) == 1


def test_listar_mais_recente_primeiro():
    repo = _repo()
    antigo = repo.salvar(_doc(hash_="v", criado_em=datetime(2026, 1, 1, tzinfo=UTC)))
    novo = repo.salvar(_doc(hash_="n", criado_em=datetime(2026, 9, 1, tzinfo=UTC)))

    ids = [d["_id"] for d in repo.listar(EMAIL)]
    assert ids == [novo["_id"], antigo["_id"]]
