"""Teste de fumaça do esqueleto do Insights (preparação da Onda 3).

O serviço ainda não tem lógica de negócio. Isto garante só que ele sobe, o
`/health` responde e o OpenAPI é gerado sem erro — a base sobre a qual a US-23
constrói as projeções materializadas.
"""

from fastapi.testclient import TestClient


def test_health_responde_ok(cliente: TestClient):
    resposta = cliente.get("/health")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok", "service": "insights"}


def test_openapi_e_gerado(cliente: TestClient):
    resposta = cliente.get("/openapi.json")
    assert resposta.status_code == 200
    assert resposta.json()["info"]["title"] == "Insights Service"


def test_metrics_expostas(cliente: TestClient):
    # O prometheus-fastapi-instrumentator registra GET /metrics (US-10).
    resposta = cliente.get("/metrics")
    assert resposta.status_code == 200
    assert b"http_requests_total" in resposta.content
