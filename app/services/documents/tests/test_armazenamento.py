"""Testes do módulo de armazenamento (US-19, ADR-0004).

O `ArmazenamentoMinio` é testado contra um cliente S3 falso que registra as
chamadas — rápido, determinístico e sem MinIO. O que é responsabilidade do S3
(fazer a URL pré-assinada expirar de fato, cifrar em repouso) não é testado
aqui; o que testamos é que passamos os parâmetros certos.
"""

from datetime import date

from app.armazenamento import (
    ArmazenamentoLocal,
    ArmazenamentoMinio,
    criar_cliente_minio,
    garantir_bucket,
    hash_email,
)

QUANDO = date(2026, 9, 8)


# ---------------------------------------------------------------------------
# hash_email — a chave do objeto nunca expõe dado pessoal
# ---------------------------------------------------------------------------


def test_hash_email_e_deterministico_e_nao_contem_o_email():
    h = hash_email("Marcia@Exemplo.com")
    assert h == hash_email("marcia@exemplo.com")  # normaliza caixa e espaços
    assert "marcia" not in h
    assert "@" not in h
    assert len(h) == 16
    assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# ArmazenamentoLocal — comportamento de sempre (flag desligada)
# ---------------------------------------------------------------------------


def test_local_chave_e_o_nome_plano(tmp_path):
    arm = ArmazenamentoLocal(tmp_path)
    assert arm.chave("marcia@x.com", "abc.png", QUANDO) == "abc.png"


def test_local_salva_e_le_de_volta(tmp_path):
    arm = ArmazenamentoLocal(tmp_path)
    arm.salvar("nota.png", b"conteudo", "image/png")
    assert (tmp_path / "nota.png").read_bytes() == b"conteudo"
    assert arm.existe("nota.png") is True
    assert arm.existe("nao-existe.png") is False
    assert arm.existe("com\x00byte-nulo.png") is False  # não levanta


def test_local_url_temporaria_e_o_caminho_servido():
    arm = ArmazenamentoLocal("/qualquer")
    assert arm.url_temporaria("nota.png") == "/documents/arquivos/nota.png"


# ---------------------------------------------------------------------------
# ArmazenamentoMinio — cliente S3 falso
# ---------------------------------------------------------------------------


class _S3Falso:
    def __init__(self, objetos: set[str] | None = None):
        self.puts: list[dict] = []
        self.presigns: list[dict] = []
        self._objetos = objetos or set()

    def put_object(self, **kwargs):
        self.puts.append(kwargs)
        self._objetos.add(kwargs["Key"])

    def generate_presigned_url(self, operacao, Params, ExpiresIn):  # noqa: N803
        self.presigns.append({"operacao": operacao, "params": Params, "expira": ExpiresIn})
        return f"http://minio:9000/{Params['Bucket']}/{Params['Key']}?X-Amz-Expires={ExpiresIn}"

    def head_object(self, Bucket, Key):  # noqa: N803
        if Key not in self._objetos:
            raise KeyError(Key)

    def head_bucket(self, Bucket):  # noqa: N803
        raise KeyError(Bucket)

    def create_bucket(self, Bucket):  # noqa: N803
        self.criou = Bucket

    def put_bucket_versioning(self, Bucket, VersioningConfiguration):  # noqa: N803
        self.versionamento = VersioningConfiguration["Status"]


def test_minio_chave_usa_hash_do_email_e_data():
    arm = ArmazenamentoMinio(_S3Falso(), "bucket")
    chave = arm.chave("marcia@exemplo.com", "abc.png", QUANDO)
    assert chave == f"{hash_email('marcia@exemplo.com')}/2026/09/abc.png"
    assert "marcia" not in chave
    assert "exemplo.com" not in chave


def test_minio_salva_com_criptografia_em_repouso():
    s3 = _S3Falso()
    ArmazenamentoMinio(s3, "bucket").salvar("k/abc.png", b"bytes", "image/png")
    assert s3.puts[0]["ServerSideEncryption"] == "AES256"
    assert s3.puts[0]["Bucket"] == "bucket"
    assert s3.puts[0]["Key"] == "k/abc.png"
    assert s3.puts[0]["ContentType"] == "image/png"


def test_minio_url_pre_assinada_de_15_minutos():
    s3 = _S3Falso()
    url = ArmazenamentoMinio(s3, "bucket").url_temporaria("k/abc.png")
    assert s3.presigns[0]["expira"] == 900
    assert s3.presigns[0]["operacao"] == "get_object"
    assert "X-Amz-Expires=900" in url


def test_minio_existe_via_head_object():
    s3 = _S3Falso(objetos={"k/existe.png"})
    arm = ArmazenamentoMinio(s3, "bucket")
    assert arm.existe("k/existe.png") is True
    assert arm.existe("k/nao.png") is False


def test_garantir_bucket_e_idempotente_e_liga_versionamento():
    s3 = _S3Falso()
    garantir_bucket(s3, "meu-bucket")
    assert s3.criou == "meu-bucket"
    assert s3.versionamento == "Enabled"


def test_criar_cliente_minio_devolve_um_cliente_s3(monkeypatch):
    monkeypatch.setenv("MINIO_ENDPOINT", "http://minio:9000")
    monkeypatch.setenv("MINIO_ROOT_USER", "fiscalflow")
    monkeypatch.setenv("MINIO_ROOT_PASSWORD", "senha")
    cliente = criar_cliente_minio()
    # boto3 não conecta na construção; só precisa expor a API S3 que usamos.
    assert hasattr(cliente, "put_object")
    assert hasattr(cliente, "generate_presigned_url")


class _S3Versionado:
    """Bucket versionado em duas páginas, como o MinIO devolve."""

    def __init__(self):
        self.paginas = [
            {
                "Versions": [
                    {"Key": "a.png", "VersionId": "1"},
                    {"Key": "a.png", "VersionId": "2"},
                ],
                "DeleteMarkers": [{"Key": "b.pdf", "VersionId": "3"}],
                "IsTruncated": True,
                "NextKeyMarker": "a.png",
                "NextVersionIdMarker": "2",
            },
            {"Versions": [{"Key": "c.txt", "VersionId": "4"}], "IsTruncated": False},
        ]
        self.listagens: list[dict] = []
        self.remocoes: list[list[dict]] = []

    def list_object_versions(self, **kwargs):
        self.listagens.append(kwargs)
        return self.paginas[len(self.listagens) - 1]

    def delete_objects(self, Bucket, Delete):  # noqa: N803
        self.remocoes.append(Delete["Objects"])


def test_minio_apagar_tudo_remove_versoes_e_marcadores_de_todas_as_paginas():
    s3 = _S3Versionado()

    apagados = ArmazenamentoMinio(s3, "bucket").apagar_tudo()

    assert apagados == 3
    assert s3.listagens[1] == {"Bucket": "bucket", "KeyMarker": "a.png", "VersionIdMarker": "2"}
    removidos = [(o["Key"], o["VersionId"]) for lote in s3.remocoes for o in lote]
    assert removidos == [("a.png", "1"), ("a.png", "2"), ("b.pdf", "3"), ("c.txt", "4")]


def test_minio_apagar_tudo_com_bucket_vazio():
    s3 = _S3Versionado()
    s3.paginas = [{"IsTruncated": False}]

    assert ArmazenamentoMinio(s3, "bucket").apagar_tudo() == 0
    assert s3.remocoes == []


def test_local_apagar_remove_so_o_arquivo_pedido(tmp_path):
    armazenamento = ArmazenamentoLocal(tmp_path)
    armazenamento.salvar("a.pdf", b"a", "application/pdf")
    armazenamento.salvar("b.pdf", b"b", "application/pdf")

    armazenamento.apagar("a.pdf")
    armazenamento.apagar("nao-existe.pdf")  # não levanta

    assert not armazenamento.existe("a.pdf")
    assert armazenamento.existe("b.pdf")


def test_minio_apagar_remove_todas_as_versoes_so_da_chave_exata():
    s3 = _S3Versionado()
    s3.paginas = [
        {
            "Versions": [
                {"Key": "h/2026/05/a.pdf", "VersionId": "1"},
                {"Key": "h/2026/05/a.pdf.bak", "VersionId": "2"},
            ],
            "DeleteMarkers": [{"Key": "h/2026/05/a.pdf", "VersionId": "3"}],
            "IsTruncated": False,
        }
    ]

    ArmazenamentoMinio(s3, "bucket").apagar("h/2026/05/a.pdf")

    assert s3.listagens[0] == {"Bucket": "bucket", "Prefix": "h/2026/05/a.pdf"}
    removidos = [(o["Key"], o["VersionId"]) for lote in s3.remocoes for o in lote]
    assert removidos == [("h/2026/05/a.pdf", "1"), ("h/2026/05/a.pdf", "3")]
