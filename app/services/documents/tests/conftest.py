"""Infraestrutura comum dos testes do Documents.

Duas restrições moldam este arquivo.

A primeira: `UPLOAD_DIR` é resolvido na importação do módulo, e o padrão é
`/data/uploads` — um caminho que só existe dentro do contêiner. A variável de
ambiente precisa estar definida *antes* do import, e é por isso que ele vem
depois das primeiras linhas em vez de no topo.

A segunda: nenhum teste chama a API do Gemini. Sem `GEMINI_API_KEY` o cliente
nasce como `None` e o serviço entra no caminho de contingência por expressões
regulares — que é justamente o caminho que a suíte precisa exercitar, porque é
o que roda quando a cota acaba ou a chave falha.
"""

import os
import tempfile

os.environ["UPLOAD_DIR"] = tempfile.mkdtemp(prefix="fluxofiscal-uploads-")
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("UNLEASH_URL", None)  # US-15: idem, sem tentativa de rede no lifespan

from collections.abc import Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402

EMAIL = "marcia@mei.com.br"


@pytest.fixture
def pasta_de_upload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isola os arquivos de cada teste, para que um não veja o do outro."""
    destino = tmp_path / "uploads"
    destino.mkdir()
    monkeypatch.setattr(main, "UPLOAD_DIR", destino)
    return destino


@pytest.fixture
def cliente(pasta_de_upload: Path) -> Iterator[TestClient]:
    with TestClient(main.app) as cliente:
        yield cliente


@pytest.fixture
def limits_falso(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Substitui a chamada HTTP ao Limits e devolve o que foi enviado.

    O Documents é o único serviço que fala com outros dois por HTTP. Deixar a
    chamada real na suíte transformaria um teste de unidade em teste de rede.
    """
    enviados: list[dict] = []

    def _post(url: str, json: dict, timeout: float = 5.0):
        enviados.append({"url": url, "json": json})
        return _RespostaFalsa(200, {"id": 1, **json})

    monkeypatch.setattr(main.httpx, "post", _post)
    return enviados


class _RespostaFalsa:
    def __init__(self, status_code: int, corpo: dict | None = None, texto: str = ""):
        self.status_code = status_code
        self._corpo = corpo or {}
        self.text = texto

    def json(self) -> dict:
        return self._corpo
