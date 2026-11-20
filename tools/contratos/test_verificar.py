"""Testes do verificador de contrato OpenAPI (US-47).

Cenário-chave da história: um PR que remove ``total_despesas`` do resumo do
Limits reprova, e a mensagem aponta o consumidor afetado.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import verificar  # noqa: E402


def _openapi(propriedades_summary, *, rota="/summary/{email}", com_rota=True):
    """OpenAPI mínimo com uma rota GET e um schema de resposta referenciado."""
    doc = {
        "openapi": "3.1.0",
        "paths": {},
        "components": {
            "schemas": {
                "Summary": {
                    "type": "object",
                    "properties": {p: {"type": "number"} for p in propriedades_summary},
                }
            }
        },
    }
    if com_rota:
        doc["paths"][rota] = {
            "get": {
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Summary"}}
                        }
                    }
                }
            }
        }
    return doc


BASE = ["total_revenue", "total_despesas", "saldo_liquido", "annual_limit"]


class TestComparar:
    def test_iguais_nao_acusam_quebra(self):
        assert verificar.comparar(_openapi(BASE), _openapi(BASE)) == []

    def test_campo_novo_e_compativel(self):
        assert verificar.comparar(_openapi(BASE), _openapi([*BASE, "novo_indicador"])) == []

    def test_campo_removido_e_quebra(self):
        quebras = verificar.comparar(
            _openapi(BASE), _openapi([b for b in BASE if b != "total_despesas"])
        )
        assert len(quebras) == 1
        assert "total_despesas" in quebras[0]
        assert "GET /summary/{email}" in quebras[0]

    def test_rota_removida_e_quebra(self):
        quebras = verificar.comparar(_openapi(BASE), _openapi(BASE, com_rota=False))
        assert quebras == ["rota removida: /summary/{email}"]

    def test_operacao_removida_e_quebra(self):
        novo = _openapi(BASE)
        novo["paths"]["/summary/{email}"] = {"post": novo["paths"]["/summary/{email}"]["get"]}
        quebras = verificar.comparar(_openapi(BASE), novo)
        assert quebras == ["operação removida: GET /summary/{email}"]

    def test_resposta_2xx_removida_e_quebra(self):
        novo = _openapi(BASE)
        novo["paths"]["/summary/{email}"]["get"]["responses"] = {
            "404": {"description": "não encontrado"}
        }
        quebras = verificar.comparar(_openapi(BASE), novo)
        assert quebras == ["resposta 200 removida: GET /summary/{email}"]

    def test_campo_aninhado_removido_e_quebra(self):
        antigo = _openapi(BASE)
        antigo["components"]["schemas"]["Summary"]["properties"]["extracao"] = {
            "type": "object",
            "properties": {"metodo": {"type": "string"}, "confianca": {"type": "number"}},
        }
        novo = json.loads(json.dumps(antigo))
        del novo["components"]["schemas"]["Summary"]["properties"]["extracao"]["properties"][
            "confianca"
        ]
        quebras = verificar.comparar(antigo, novo)
        assert quebras == [
            "campo removido da resposta 200 de GET /summary/{email}: extracao.confianca"
        ]


class TestCli:
    def _preparar(self, tmp_path, monkeypatch, servico="limits"):
        snapdir = tmp_path / "snapshots"
        snapdir.mkdir()
        monkeypatch.setattr(verificar, "SNAPSHOTS", snapdir)
        monkeypatch.setattr(verificar, "MAPA_CONSUMIDORES", tmp_path / "consumidores.json")
        (tmp_path / "consumidores.json").write_text(
            json.dumps({"limits": ["frontend", "agent-orchestrator", "documents", "insights"]}),
            encoding="utf-8",
        )
        return snapdir

    def _escrever_atual(self, tmp_path, doc):
        alvo = tmp_path / "atual.json"
        alvo.write_text(json.dumps(doc), encoding="utf-8")
        return alvo

    def test_bootstrap_cria_snapshot_e_passa(self, tmp_path, monkeypatch, capsys):
        snapdir = self._preparar(tmp_path, monkeypatch)
        atual = self._escrever_atual(tmp_path, _openapi(BASE))

        codigo = verificar.main(["--servico", "limits", "--atual", str(atual)])

        assert codigo == 0
        assert (snapdir / "limits.openapi.json").exists()
        assert "bootstrap" in capsys.readouterr().out

    def test_campo_removido_reprova_e_aponta_consumidores(self, tmp_path, monkeypatch, capsys):
        snapdir = self._preparar(tmp_path, monkeypatch)
        (snapdir / "limits.openapi.json").write_text(json.dumps(_openapi(BASE)), encoding="utf-8")
        atual = self._escrever_atual(tmp_path, _openapi([b for b in BASE if b != "total_despesas"]))

        codigo = verificar.main(["--servico", "limits", "--atual", str(atual)])

        saida = capsys.readouterr().out
        assert codigo == 1
        assert "total_despesas" in saida
        assert "agent-orchestrator" in saida
        assert "frontend" in saida

    def test_escrever_regrava_snapshot(self, tmp_path, monkeypatch):
        snapdir = self._preparar(tmp_path, monkeypatch)
        (snapdir / "limits.openapi.json").write_text(json.dumps(_openapi(BASE)), encoding="utf-8")
        atual = self._escrever_atual(tmp_path, _openapi([b for b in BASE if b != "total_despesas"]))

        codigo = verificar.main(["--servico", "limits", "--atual", str(atual), "--escrever"])

        assert codigo == 0
        regravado = json.loads((snapdir / "limits.openapi.json").read_text("utf-8"))
        assert "total_despesas" not in regravado["components"]["schemas"]["Summary"]["properties"]

    def test_snapshot_compativel_passa(self, tmp_path, monkeypatch):
        snapdir = self._preparar(tmp_path, monkeypatch)
        (snapdir / "limits.openapi.json").write_text(json.dumps(_openapi(BASE)), encoding="utf-8")
        atual = self._escrever_atual(tmp_path, _openapi([*BASE, "campo_novo"]))

        assert verificar.main(["--servico", "limits", "--atual", str(atual)]) == 0
