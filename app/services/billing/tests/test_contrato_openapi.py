"""Verificação de contrato: as respostas obedecem ao OpenAPI que o serviço publica.

Ver a suíte equivalente do Limits para o raciocínio completo. Em resumo: o
Schemathesis gera entradas válidas a partir do `/openapi.json` do próprio
serviço e cobra que nenhuma rota devolva 500 para entrada válida, nem responda
fora do esquema declarado.
"""

import gc

import pytest
import schemathesis
from hypothesis import HealthCheck, Phase, settings

from app import main
from tests.conftest import apontar_para, criar_motor_em_memoria

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
def banco_em_memoria():
    with pytest.MonkeyPatch.context() as mp:
        motor = criar_motor_em_memoria()
        apontar_para(mp, motor)
        main.Base.metadata.create_all(bind=motor)
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
