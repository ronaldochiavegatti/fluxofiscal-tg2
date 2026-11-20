"""Testa os verificadores de carga sem precisar rodar o k6.

Roda na CI (carga.yml). Cobre a lógica de decisão: o modo gate reprova uma
violação de SLO, o modo smoke não; as tabelas do artigo saem com os números
certos.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import gerar_tabelas as gt  # noqa: E402
import verificar_slos as vs  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
SLOS = RAIZ / "docs" / "observabilidade" / "slos.yaml"


def _escrever(dir_: Path, nome: str, dados: dict) -> None:
    (dir_ / nome).write_text(json.dumps(dados), encoding="utf-8")


def test_gate_reprova_p95_acima_do_slo(tmp_path: Path):
    _escrever(tmp_path, "perfil-mei.json", {"summary_p95_ms": 900, "taxa_erro": 0.0})
    _, violacoes, _ = vs.verificar(tmp_path, SLOS)
    assert any("p95" in v for v in violacoes)


def test_gate_aprova_dentro_do_slo(tmp_path: Path):
    _escrever(tmp_path, "perfil-mei.json", {"summary_p95_ms": 120, "taxa_erro": 0.002})
    ok, violacoes, _ = vs.verificar(tmp_path, SLOS)
    assert not violacoes
    assert ok


def test_smoke_nao_reprova(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _escrever(tmp_path, "perfil-mei.json", {"summary_p95_ms": 5000, "taxa_erro": 0.5})
    monkeypatch.setattr(
        sys, "argv", ["x", "--entrada", str(tmp_path), "--slos", str(SLOS), "--modo", "smoke"]
    )
    assert vs.main() == 0


def test_gate_reprova_de_verdade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _escrever(tmp_path, "perfil-mei.json", {"summary_p95_ms": 5000, "taxa_erro": 0.5})
    monkeypatch.setattr(
        sys, "argv", ["x", "--entrada", str(tmp_path), "--slos", str(SLOS), "--modo", "gate"]
    )
    assert vs.main() == 1


def test_saturacao_entra_no_relatorio(tmp_path: Path):
    _escrever(tmp_path, "perfil-mei.json", {"summary_p95_ms": 100, "taxa_erro": 0.0})
    _escrever(
        tmp_path,
        "estresse.json",
        {
            "ponto_de_saturacao_vus": 120,
            "observacao": "p95 cruzou 300 ms a partir de 120 VUs",
            "degraus": [
                {"vus": 100, "p95_ms": 210, "violou_slo": False},
                {"vus": 120, "p95_ms": 340, "violou_slo": True},
            ],
        },
    )
    _, _, linhas = vs.verificar(tmp_path, SLOS)
    assert any("saturação" in linha["metrica"] for linha in linhas)


def test_gerar_tabelas_traz_os_numeros(tmp_path: Path):
    _escrever(
        tmp_path,
        "perfil-mei.json",
        {
            "vus": 50,
            "duracao": "10m",
            "summary_p95_ms": 142.7,
            "summary_p99_ms": 310.0,
            "taxa_erro": 0.004,
            "req_por_s": 88.1,
            "iteracoes": 12000,
            "aprovado": True,
        },
    )
    md = gt.gerar(tmp_path)
    assert "143 ms" in md
    assert "0.40%" in md
    assert "50 VUs" in md
