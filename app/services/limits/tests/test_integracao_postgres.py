"""Integração do Limits contra um PostgreSQL 16 de verdade.

Existe porque SQLite não é PostgreSQL nos dois pontos em que este serviço mais
depende do banco:

1. `func.extract("year", ...)` compila para dialetos diferentes. No SQLite vira
   `CAST(STRFTIME(...))`; no PostgreSQL, `EXTRACT`. Um filtro que funciona num
   pode devolver vazio no outro.
2. `Numeric(10, 2)` é decimal nativo no PostgreSQL e ponto flutuante no SQLite.
   Somar centavos em float acumula erro — e a soma anual é exatamente o número
   que decide se o MEI foi desenquadrado.

Também é aqui que `create_tables_with_retry` é exercitado de fato, com o
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` que só o PostgreSQL entende.

Exige Docker. Sem daemon disponível, a suíte é pulada em vez de reprovar: a
verificação não some da CI, mas também não vira obstáculo na máquina de quem
está desenvolvendo sem contêiner.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import main

pytestmark = pytest.mark.integracao

PostgresContainer = pytest.importorskip(
    "testcontainers.postgres",
    reason="testcontainers não instalado",
).PostgresContainer

EMAIL = "integracao@mei.com.br"
ANO = 2026


@pytest.fixture(scope="module")
def url_do_postgres() -> Iterator[str]:
    try:
        contexto = PostgresContainer("postgres:16-alpine")
        with contexto as postgres:
            yield postgres.get_connection_url()
    except Exception as erro:  # qualquer falha aqui significa "sem Docker disponível"
        pytest.skip(f"PostgreSQL de teste indisponível: {type(erro).__name__}: {erro}")


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch, url_do_postgres: str) -> Iterator[TestClient]:
    motor = create_engine(url_do_postgres, future=True)
    monkeypatch.setattr(main, "engine", motor)
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(autoflush=False, bind=motor))

    with TestClient(main.app) as cliente:
        cliente.delete(f"/reset/{EMAIL}")
        yield cliente
        cliente.delete(f"/reset/{EMAIL}")


def registrar(cliente: TestClient, valor: str, data: str, tipo: str = "venda") -> None:
    resposta = cliente.post(
        "/transactions",
        json={"email": EMAIL, "amount": float(valor), "tx_date": data, "tx_type": tipo},
    )
    assert resposta.status_code == 200, resposta.text


class TestEsquema:
    def test_criacao_e_idempotente(self, cliente):
        """Subir duas vezes sobre o mesmo banco não pode falhar.

        O `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` existe justamente para
        bancos que já existiam antes de a coluna `tx_type` ser criada.
        """
        main.create_tables_with_retry()
        main.create_tables_with_retry()

        assert cliente.get("/health").json()["status"] == "ok"


class TestFiltrosDeData:
    def test_extract_ano_recorta_de_verdade(self, cliente):
        registrar(cliente, "100.00", f"{ANO}-01-15")
        registrar(cliente, "200.00", f"{ANO - 1}-01-15")

        do_ano = cliente.get(f"/transactions?email={EMAIL}&year={ANO}").json()

        assert [t["amount"] for t in do_ano] == [100.00]

    def test_extract_mes_recorta_de_verdade(self, cliente):
        registrar(cliente, "100.00", f"{ANO}-01-15")
        registrar(cliente, "200.00", f"{ANO}-02-15")

        de_fevereiro = cliente.get(f"/transactions?email={EMAIL}&year={ANO}&month=2").json()

        assert [t["amount"] for t in de_fevereiro] == [200.00]

    def test_virada_de_ano_nao_vaza(self, cliente):
        """31/12 e 01/01 são o par que mais expõe erro de fuso ou de corte."""
        registrar(cliente, "10.00", f"{ANO - 1}-12-31")
        registrar(cliente, "20.00", f"{ANO}-01-01")

        assert cliente.get(f"/summary/{EMAIL}?year={ANO}").json()["total_revenue"] == 20.00


class TestPrecisaoDosCentavos:
    def test_soma_de_centavos_nao_acumula_erro(self, cliente):
        """0,10 + 0,20 = 0,30. Em ponto flutuante, 0,30000000000000004.

        Somado sobre um ano de lançamentos, o desvio deixa de ser curiosidade
        numérica e passa a mover o percentual do limite exibido ao MEI.
        """
        for _ in range(3):
            registrar(cliente, "0.10", f"{ANO}-03-01")
        registrar(cliente, "0.20", f"{ANO}-03-02")

        assert cliente.get(f"/summary/{EMAIL}?year={ANO}").json()["total_revenue"] == 0.50

    def test_valor_no_teto_permanece_exato(self, cliente):
        registrar(cliente, "80999.99", f"{ANO}-06-01")
        registrar(cliente, "0.01", f"{ANO}-06-02")

        resumo = cliente.get(f"/summary/{EMAIL}?year={ANO}").json()

        assert resumo["total_revenue"] == 81000.00
        assert resumo["remaining"] == 0.00
        assert resumo["exceeded"] is False


class TestBalancete:
    def test_venda_e_compra_somam_em_colunas_separadas(self, cliente):
        registrar(cliente, "50000.00", f"{ANO}-02-10")
        registrar(cliente, "30000.00", f"{ANO}-02-11", tipo="compra")

        resumo = cliente.get(f"/summary/{EMAIL}?year={ANO}").json()

        assert resumo["total_revenue"] == 50000.00
        assert resumo["total_despesas"] == 30000.00
        assert resumo["saldo_liquido"] == 20000.00
