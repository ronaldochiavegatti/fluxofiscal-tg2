"""Testa o gerador de regras de SLO.

Roda na CI (observabilidade.yml). Cobre o que a revisão de um PR não consegue
ver de relance: os limiares de queima calculados a partir do objetivo, a
exigência das duas janelas e a rastreabilidade até o runbook.
"""

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))

import gerar_alertas as ga  # noqa: E402


@pytest.fixture
def regras() -> dict:
    slos = yaml.safe_load(ga.SLOS.read_text(encoding="utf-8"))
    return ga.gerar(slos)


def _grupo(regras: dict, nome: str) -> dict:
    return next(g for g in regras["groups"] if g["name"] == nome)


def test_arquivo_versionado_em_sincronia():
    """O mesmo que a CI roda: o .yml commitado bate com o slos.yaml."""
    resultado = subprocess.run(
        [sys.executable, str(RAIZ / "tools/observabilidade/gerar_alertas.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr


def test_limiar_de_queima_vem_do_objetivo(regras: dict):
    alertas = _grupo(regras, "slo_queima_orcamento")["rules"]
    rapida_limits = next(
        r
        for r in alertas
        if r["labels"]["slo"] == "limits-disponivel" and r["labels"]["janela"] == "queima-rapida"
    )
    # objetivo 0.999 -> orçamento de erro 0.001 -> 14.4x = 0.0144
    assert "> 0.0144" in rapida_limits["expr"]


def test_alerta_exige_as_duas_janelas(regras: dict):
    for r in _grupo(regras, "slo_queima_orcamento")["rules"]:
        assert " and " in r["expr"], r["expr"]
        assert "taxa1h" in r["expr"] or "taxa6h" in r["expr"] or "taxa3d" in r["expr"]
        assert "taxa5m" in r["expr"] or "taxa30m" in r["expr"] or "taxa6h" in r["expr"]


def test_pagina_tem_runbook(regras: dict):
    for r in _grupo(regras, "slo_queima_orcamento")["rules"]:
        if r["labels"]["severity"] == "pagina":
            assert r["annotations"]["runbook_url"].endswith("error-budget-burn.md")


def test_runbook_referenciado_existe(regras: dict):
    for r in _grupo(regras, "slo_queima_orcamento")["rules"]:
        url = r["annotations"].get("runbook_url", "")
        if url:
            nome = url.rsplit("/", 1)[-1]
            assert (RAIZ / "docs/observabilidade/runbooks" / nome).exists(), nome


def test_aplica_a_desconhecido_falha():
    slos = {
        "disponibilidade": [
            {
                "id": "x-disponivel",
                "objetivo": 0.99,
                "metrica": "http_requests_total",
                "selector_total": "",
                "selector_erro": 'status=~"5.."',
            }
        ],
        "queima_de_orcamento": [
            {
                "nome": "queima-rapida",
                "fator": 14.4,
                "janela_longa": "1h",
                "janela_curta": "5m",
                "severidade": "pagina",
                "aplica_a": ["nao-existe"],
            }
        ],
    }
    with pytest.raises(SystemExit):
        ga.gerar(slos)
