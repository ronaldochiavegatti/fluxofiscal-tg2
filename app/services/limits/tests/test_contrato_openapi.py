"""Verificação de contrato: as respostas obedecem ao OpenAPI que o serviço publica.

Os testes de rota checam os casos que alguém pensou em escrever. Esta suíte
checa o resto: o Schemathesis lê o `/openapi.json` do próprio serviço, gera
entradas válidas para cada operação declarada e cobra duas garantias que nenhum
teste de exemplo cobre bem —

- nenhuma rota devolve 500 para entrada que o próprio contrato considera válida;
- nenhuma resposta viola o esquema que o serviço prometeu.

O valor está em não depender da imaginação de quem escreveu o teste. O contrato
é derivado do código, então ele acompanha qualquer rota nova sem que ninguém
precise lembrar de estendê-lo.
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
    # Os fluxos internos do anyio ficam pendentes de coleta de lixo e o aviso
    # aparece muito depois, em outro teste. É ruído de terceiro; o filtro fica
    # restrito a este módulo para não afrouxar o `error` do resto da suíte.
    pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning"),
    pytest.mark.filterwarnings("ignore::ResourceWarning"),
]

# O FastAPI 0.115 publica OpenAPI 3.1.0. O Schemathesis 3.x só lê a 3.1 com o
# suporte habilitado explicitamente — sem esta linha, a carga falha na coleta.
schemathesis.experimental.OPEN_API_3_1.enable()

esquema = schemathesis.from_asgi("/openapi.json", main.app)


@pytest.fixture(autouse=True)
def banco_em_memoria():
    """Cada operação gerada roda contra um SQLite limpo.

    O contrato é sobre forma de requisição e resposta, não sobre acumulação de
    dados: um banco por teste mantém os casos independentes entre si.
    """
    with pytest.MonkeyPatch.context() as mp:
        apontar_para(mp, criar_motor_em_memoria())
        yield

    # O transporte ASGI do Schemathesis abre um TestClient por exemplo gerado e
    # os fluxos internos do anyio só são liberados na coleta de lixo. Sem
    # forçá-la aqui, o aviso aparece no meio de outro teste — onde o filtro
    # declarado neste módulo não vale.
    gc.collect()


@esquema.parametrize()
@settings(
    max_examples=20,
    deadline=None,
    # `function_scoped_fixture`: o banco em memória é recriado por teste, e é
    # isso que queremos. `too_slow`: gerar PDF a cada exemplo do /report é
    # legitimamente lento, e não é sinal de defeito.
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
    # Sem a fase de encolhimento a suíte fica determinística no tempo: uma
    # falha ainda é relatada com o exemplo que a produziu.
    phases=[Phase.explicit, Phase.reuse, Phase.generate],
)
def test_respostas_obedecem_ao_contrato(case):
    resposta = case.call()
    case.validate_response(resposta)
