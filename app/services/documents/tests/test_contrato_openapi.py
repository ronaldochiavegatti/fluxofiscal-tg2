"""Verificação de contrato: as respostas obedecem ao OpenAPI que o serviço publica.

Ver a suíte equivalente do Limits para o raciocínio completo. Aqui há uma
diferença: o Documents é o único serviço que fala com outros dois por HTTP, e
essas chamadas são substituídas por um duplo. Sem isso, cada exemplo gerado
tentaria alcançar `http://limits:8000` e o teste mediria a rede, não o contrato.
"""

import gc

import pytest
import schemathesis
from hypothesis import HealthCheck, Phase, settings

from app import main
from tests.conftest import _RespostaFalsa

pytestmark = [
    pytest.mark.contrato,
    # O transporte ASGI do Schemathesis abre um TestClient por exemplo gerado.
    # Os fluxos internos do anyio só são liberados na coleta de lixo; o filtro
    # fica restrito a este módulo para não afrouxar o `error` do resto.
    pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning"),
    pytest.mark.filterwarnings("ignore::ResourceWarning"),
]

# O FastAPI 0.115 publica OpenAPI 3.1.0. O Schemathesis 3.x só lê a 3.1 com o
# suporte habilitado explicitamente — sem esta linha, a carga falha na coleta.
schemathesis.experimental.OPEN_API_3_1.enable()

esquema = schemathesis.from_asgi("/openapi.json", main.app)


@pytest.fixture(autouse=True)
def servicos_vizinhos_substituidos(tmp_path, monkeypatch):
    destino = tmp_path / "uploads"
    destino.mkdir()
    monkeypatch.setattr(main, "UPLOAD_DIR", destino)
    monkeypatch.setattr(
        main.httpx,
        "post",
        lambda url, json, timeout=5.0: _RespostaFalsa(200, {"id": 1, **json}),
    )

    yield

    # Mantém o aviso de recurso não fechado dentro deste módulo, onde o filtro
    # está declarado, em vez de deixá-lo aparecer no meio de outro teste.
    gc.collect()


@esquema.parametrize()
@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
    phases=[Phase.explicit, Phase.reuse, Phase.generate],
)
def test_respostas_obedecem_ao_contrato(case):
    resposta = case.call()
    case.validate_response(resposta)
