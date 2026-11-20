#!/usr/bin/env python3
"""Gera as regras do Prometheus a partir de docs/observabilidade/slos.yaml.

Um SLO que só existe em prosa não alerta ninguém. Este script traduz a fonte
da verdade (`slos.yaml`) em regras que o Prometheus avalia:

  slo:sli_erro:taxa<janela>   recording rules — taxa de erro por SLO e janela
  slo:orcamento:consumido     quanto do orçamento de erro de 30d já foi gasto
  SLOQueimaDeOrcamento        alerta de queima em DUAS janelas (Site
                              Reliability Workbook, cap. 5): a curta evita
                              alerta tardio, a longa evita alerta por ruído.
                              As duas precisam estar queimando ao mesmo tempo.

Uso:
  python tools/observabilidade/gerar_alertas.py            # (re)escreve o arquivo
  python tools/observabilidade/gerar_alertas.py --check    # falha se desatualizado

O arquivo gerado é versionado (app/services/prometheus/rules/slo-burn-rate.yml)
para que a revisão de um PR veja exatamente o que muda no comportamento de
alerta — e a CI reprova se ele sair de sincronia com o slos.yaml.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[2]
SLOS = RAIZ / "docs" / "observabilidade" / "slos.yaml"
SAIDA = RAIZ / "app" / "services" / "prometheus" / "rules" / "slo-burn-rate.yml"
RUNBOOK_BASE = (
    "https://github.com/ronaldochiavegatti/fluxofiscal/blob/main/docs/observabilidade/runbooks/"
)

CABECALHO = (
    "# GERADO por tools/observabilidade/gerar_alertas.py — NÃO EDITE À MÃO.\n"
    "# Fonte: docs/observabilidade/slos.yaml. Para atualizar:\n"
    "#   python tools/observabilidade/gerar_alertas.py\n"
    "# A CI (observabilidade.yml) reprova se este arquivo sair de sincronia.\n"
)

# Janela longa de referência do orçamento de erro.
JANELA_ORCAMENTO = "30d"


def _selector(base: str, extra: str) -> str:
    partes = [p for p in (base, extra) if p]
    return "{" + ",".join(partes) + "}" if partes else ""


def taxa_erro_expr(slo: dict, janela: str) -> str:
    """sum(rate(erro[j])) / sum(rate(total[j])) — a taxa de erro do SLO."""
    metrica = slo["metrica"]
    erro = _selector(slo.get("selector_erro", ""), "")
    total = _selector(slo.get("selector_total", ""), "")
    return f"sum(rate({metrica}{erro}[{janela}])) / sum(rate({metrica}{total}[{janela}]))"


def gerar(slos: dict) -> dict:
    disponibilidade = slos.get("disponibilidade", [])
    queimas = slos.get("queima_de_orcamento", [])

    por_id = {s["id"]: s for s in disponibilidade}

    janelas: set[str] = {JANELA_ORCAMENTO}
    for q in queimas:
        janelas.add(q["janela_longa"])
        janelas.add(q["janela_curta"])

    def ordem(j: str) -> int:
        unid = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        return int(j[:-1]) * unid[j[-1]]

    janelas_ord = sorted(janelas, key=ordem)

    # Janelas curtas avaliadas de perto; as longas (3d, 30d) num grupo à parte
    # com intervalo folgado, porque `rate(...[30d])` a cada 30s pesa demais.
    limite_rapido = ordem("6h")
    grupo_sli_rapido = {"name": "slo_sli_erro_rapido", "interval": "30s", "rules": []}
    grupo_sli_lento = {"name": "slo_sli_erro_lento", "interval": "2m", "rules": []}
    for slo in disponibilidade:
        for janela in janelas_ord:
            destino = grupo_sli_rapido if ordem(janela) <= limite_rapido else grupo_sli_lento
            destino["rules"].append(
                {
                    "record": f"slo:sli_erro:taxa{janela}",
                    "expr": taxa_erro_expr(slo, janela),
                    "labels": {"slo": slo["id"]},
                }
            )

    grupo_orc = {"name": "slo_orcamento", "interval": "2m", "rules": []}
    for slo in disponibilidade:
        objetivo_erro = round(1 - float(slo["objetivo"]), 6)
        grupo_orc["rules"].append(
            {
                "record": "slo:orcamento_erro:objetivo",
                "expr": f"{objetivo_erro}",
                "labels": {"slo": slo["id"]},
            }
        )
        grupo_orc["rules"].append(
            {
                # 0 = intacto, 1 = esgotado. Acima de 1 estourou o orçamento.
                "record": "slo:orcamento:consumido",
                "expr": (
                    f'slo:sli_erro:taxa{JANELA_ORCAMENTO}{{slo="{slo["id"]}"}} / {objetivo_erro}'
                ),
                "labels": {"slo": slo["id"]},
            }
        )

    grupo_alertas = {"name": "slo_queima_orcamento", "rules": []}
    for q in queimas:
        fator = float(q["fator"])
        severidade = q["severidade"]
        runbook = q.get("runbook", "")
        espera = "2m" if severidade == "pagina" else "15m"
        for slo_id in q["aplica_a"]:
            slo = por_id.get(slo_id)
            if slo is None:
                raise SystemExit(f"queima '{q['nome']}' aplica_a SLO desconhecido: {slo_id}")
            objetivo_erro = round(1 - float(slo["objetivo"]), 6)
            limiar = round(fator * objetivo_erro, 8)
            longa = q["janela_longa"]
            curta = q["janela_curta"]
            expr = (
                f'slo:sli_erro:taxa{longa}{{slo="{slo_id}"}} > {limiar} '
                f'and slo:sli_erro:taxa{curta}{{slo="{slo_id}"}} > {limiar}'
            )
            grupo_alertas["rules"].append(
                {
                    "alert": "SLOQueimaDeOrcamento",
                    "expr": expr,
                    "for": espera,
                    "labels": {
                        "severity": severidade,
                        "slo": slo_id,
                        "janela": q["nome"],
                    },
                    "annotations": {
                        "summary": (
                            f"SLO {slo_id} queimando orçamento de erro ({q['nome']}, {fator}x)"
                        ),
                        "description": (
                            f"A taxa de erro do SLO {slo_id} está acima de "
                            f"{fator}x o orçamento nas janelas de {longa} e {curta}. "
                            f"Objetivo: {slo['objetivo']:.4f}."
                        ),
                        "runbook_url": f"{RUNBOOK_BASE}{runbook}" if runbook else "",
                    },
                }
            )

    return {
        "groups": [
            grupo_sli_rapido,
            grupo_sli_lento,
            grupo_orc,
            grupo_alertas,
        ]
    }


def render(regras: dict) -> str:
    corpo = yaml.safe_dump(
        regras, sort_keys=False, allow_unicode=True, default_flow_style=False, width=100
    )
    return CABECALHO + "\n" + corpo


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--slos", type=Path, default=SLOS)
    p.add_argument("--saida", type=Path, default=SAIDA)
    p.add_argument(
        "--check",
        action="store_true",
        help="não escreve; falha se o arquivo gerado difere do versionado",
    )
    args = p.parse_args()

    slos = yaml.safe_load(args.slos.read_text(encoding="utf-8"))
    conteudo = render(gerar(slos))

    if args.check:
        atual = args.saida.read_text(encoding="utf-8") if args.saida.exists() else ""
        if atual != conteudo:
            print(
                "::error::regras do Prometheus fora de sincronia com o slos.yaml.\n"
                "Rode: python tools/observabilidade/gerar_alertas.py"
            )
            return 1
        print(f"{args.saida.relative_to(RAIZ)} está em sincronia com o slos.yaml.")
        return 0

    args.saida.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n": o arquivo é versionado e a CI compara byte a byte; sem isso
    # o Python no Windows grava CRLF e o --check quebra no runner Linux.
    args.saida.write_text(conteudo, encoding="utf-8", newline="\n")
    n_alertas = sum(1 for g in gerar(slos)["groups"] for r in g["rules"] if "alert" in r)
    print(f"Escrito {args.saida.relative_to(RAIZ)} — {n_alertas} regra(s) de alerta.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
