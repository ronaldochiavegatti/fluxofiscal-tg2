"""Teste de fumaça do esqueleto do Notifications (preparação da Onda 4).

O serviço ainda não tem lógica de negócio. Isto garante só que ele sobe, o
`/health` responde e o OpenAPI é gerado — a base sobre a qual as US-29 / US-29b
/ US-29c constroem o feed de alertas.
"""

from fastapi.testclient import TestClient


def test_health_responde_ok(cliente: TestClient):
    resposta = cliente.get("/health")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok", "service": "notifications"}


def test_openapi_e_gerado(cliente: TestClient):
    resposta = cliente.get("/openapi.json")
    assert resposta.status_code == 200
    assert resposta.json()["info"]["title"] == "Notifications Service"


def test_metrics_expostas(cliente: TestClient):
    resposta = cliente.get("/metrics")
    assert resposta.status_code == 200
    assert b"http_requests_total" in resposta.content
