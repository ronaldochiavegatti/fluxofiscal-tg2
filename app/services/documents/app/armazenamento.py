"""Armazenamento de documentos — sistema de arquivos ou MinIO (ADR-0004, US-19).

A flag `storage-minio` decide qual implementação o upload usa. O padrão
(`padrao_seguro: false`) é o sistema de arquivos local, exatamente como antes.
O acesso fica atrás desta interface para que os testes rodem sem MinIO e para
que trocar de destino seja configuração, não reescrita.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
from datetime import date
from pathlib import Path
from typing import Protocol, runtime_checkable

BUCKET_PADRAO = "fiscalflow-documents"
VALIDADE_URL_SEGUNDOS = 900  # 15 minutos (ADR-0004)


def hash_email(email: str) -> str:
    """SHA-256 truncado do e-mail. A chave do objeto no MinIO usa isto, nunca o
    e-mail — quem lista o bucket não vê dado pessoal."""
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:16]


@runtime_checkable
class ArmazenamentoDeDocumentos(Protocol):
    nome: str

    def chave(self, email: str, nome_arquivo: str, quando: date) -> str: ...
    def salvar(self, chave: str, conteudo: bytes, tipo_mime: str) -> None: ...
    def ler(self, chave: str) -> bytes: ...
    def url_temporaria(self, chave: str, expira_em: int = VALIDADE_URL_SEGUNDOS) -> str: ...
    def existe(self, chave: str) -> bool: ...
    def apagar_tudo(self) -> int: ...
    def apagar(self, chave: str) -> None: ...


class ArquivoAusente(Exception):
    """A chave pedida não existe no armazenamento — erro permanente (US-18)."""


class ArmazenamentoLocal:
    """Grava em disco, como o serviço sempre fez. A "URL temporária" é o
    caminho servido por GET /arquivos/{chave} — não é pré-assinada, mas mantém
    o modo local (flag desligada) funcional e testável."""

    nome = "local"

    def __init__(self, raiz: Path):
        self.raiz = Path(raiz)

    def chave(self, email: str, nome_arquivo: str, quando: date) -> str:
        return nome_arquivo

    def salvar(self, chave: str, conteudo: bytes, tipo_mime: str) -> None:
        destino = self.raiz / chave
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(conteudo)

    def ler(self, chave: str) -> bytes:
        try:
            return (self.raiz / chave).read_bytes()
        except (FileNotFoundError, OSError, ValueError) as erro:
            raise ArquivoAusente(chave) from erro

    def url_temporaria(self, chave: str, expira_em: int = VALIDADE_URL_SEGUNDOS) -> str:
        return f"/documents/arquivos/{chave}"

    def existe(self, chave: str) -> bool:
        try:
            return (self.raiz / chave).is_file()
        except (ValueError, OSError):
            return False

    def apagar(self, chave: str) -> None:
        (self.raiz / chave).unlink(missing_ok=True)

    def apagar_tudo(self) -> int:
        apagados = 0
        for caminho in self.raiz.glob("*"):
            if caminho.is_file():
                caminho.unlink()
                apagados += 1
        return apagados


class ArmazenamentoMinio:
    """Grava no MinIO com criptografia em repouso (SSE-S3) e devolve URL
    pré-assinada com validade de 15 minutos. O arquivo não trafega pelo
    serviço na leitura — o cliente baixa direto do MinIO."""

    nome = "minio"

    def __init__(self, cliente, bucket: str):
        self._s3 = cliente
        self._bucket = bucket

    def chave(self, email: str, nome_arquivo: str, quando: date) -> str:
        return f"{hash_email(email)}/{quando:%Y/%m}/{nome_arquivo}"

    def salvar(self, chave: str, conteudo: bytes, tipo_mime: str) -> None:
        self._s3.put_object(
            Bucket=self._bucket,
            Key=chave,
            Body=conteudo,
            ContentType=tipo_mime or "application/octet-stream",
            ServerSideEncryption="AES256",
        )

    def ler(self, chave: str) -> bytes:
        try:
            resposta = self._s3.get_object(Bucket=self._bucket, Key=chave)
        except Exception as erro:
            raise ArquivoAusente(chave) from erro
        return resposta["Body"].read()

    def url_temporaria(self, chave: str, expira_em: int = VALIDADE_URL_SEGUNDOS) -> str:
        return self._s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": chave},
            ExpiresIn=expira_em,
        )

    def existe(self, chave: str) -> bool:
        try:
            self._s3.head_object(Bucket=self._bucket, Key=chave)
        except Exception:
            return False
        return True

    def apagar_tudo(self) -> int:
        """Remove todas as versões e marcadores de exclusão do bucket.

        O bucket é versionado (`garantir_bucket`): um `delete_object` simples
        só criaria marcador e o arquivo continuaria guardado. O reset de teste
        promete apagar de vez, então cada versão é removida pelo `VersionId`.
        Devolve quantos arquivos (versões, sem contar marcadores) saíram."""
        return self._apagar_versoes()

    def apagar(self, chave: str) -> None:
        """Apaga um arquivo de vez, com todas as versões (#96) — pelo mesmo
        motivo do `apagar_tudo`: no bucket versionado, `delete_object` só
        esconderia o arquivo atrás de um marcador."""
        self._apagar_versoes(chave)

    def _apagar_versoes(self, chave: str | None = None) -> int:
        apagados = 0
        marcadores: dict[str, str] = {}
        filtro = {"Prefix": chave} if chave else {}
        while True:
            pagina = self._s3.list_object_versions(Bucket=self._bucket, **filtro, **marcadores)
            # O prefixo de "a.pdf" também casa "a.pdf.bak": só a chave exata sai.
            versoes = [v for v in pagina.get("Versions", []) if chave is None or v["Key"] == chave]
            marcas = [
                m for m in pagina.get("DeleteMarkers", []) if chave is None or m["Key"] == chave
            ]
            alvos = [
                {"Key": item["Key"], "VersionId": item["VersionId"]} for item in versoes + marcas
            ]
            if alvos:
                self._s3.delete_objects(
                    Bucket=self._bucket, Delete={"Objects": alvos, "Quiet": True}
                )
            apagados += len(versoes)
            if not pagina.get("IsTruncated"):
                return apagados
            marcadores = {
                "KeyMarker": pagina["NextKeyMarker"],
                "VersionIdMarker": pagina["NextVersionIdMarker"],
            }


def criar_cliente_minio():
    """Cliente boto3 apontado para o MinIO. Endpoint e credenciais vêm do
    ambiente (docker-compose)."""
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=os.getenv("MINIO_ENDPOINT", "http://minio:9000"),
        aws_access_key_id=os.getenv("MINIO_ROOT_USER", "fiscalflow"),
        aws_secret_access_key=os.getenv("MINIO_ROOT_PASSWORD", ""),
        region_name="us-east-1",
        config=Config(signature_version="s3v4"),
    )


def garantir_bucket(cliente, bucket: str) -> None:
    """Idempotente: cria o bucket e liga o versionamento se ainda não existir.
    Chamado uma vez, na primeira gravação com a flag ligada."""
    try:
        cliente.head_bucket(Bucket=bucket)
    except Exception:
        with contextlib.suppress(Exception):
            cliente.create_bucket(Bucket=bucket)
    with contextlib.suppress(Exception):
        cliente.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})
