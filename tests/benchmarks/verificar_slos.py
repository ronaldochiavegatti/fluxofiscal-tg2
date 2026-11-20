#!/usr/bin/env python3
"""Confere os resultados dos testes de carga contra os SLOs declarados.

Lê os JSON produzidos pelos cenários k6 (tests/load/) e compara com
docs/observabilidade/slos.yaml. É a ponte entre "o k6 rodou" e "o k6 rodou
DENTRO do objetivo".

  --modo gate    (nightly) sai com código != 0 se o perfil realista violar
                 um SLO. É o portão do pipeline noturno.
  --modo smoke   (PR)      só relata; nunca reprova. O smoke roda com poucos
                 VUs por 1 min e sob a carga variável do runner — o número
                 não é confiável o bastante para reprovar um PR.

Uso:
  python tests/benchmarks/verificar_slos.py --entrada resultados/ \\
    --slos docs/observabilidade/slos.yaml --modo gate
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path

import yaml


def _slo_por_id(slos: dict, familia: str, id_: str) -> dict | None:
    for item in slos.get(familia, []):
        if item.get("id") == id_:
            return item
    return None


def verificar(entrada: Path, slos_path: Path) -> tuple[list[str], list[str], list[dict]]:
    slos = yaml.safe_load(slos_path.read_text(encoding="utf-8"))
    ok: list[str] = []
    violacoes: list[str] = []
    linhas: list[dict] = []

    perfil_path = entrada / "perfil-mei.json"
    if perfil_path.exists():
        perfil = json.loads(perfil_path.read_text(encoding="utf-8"))
        resumo_slo = _slo_por_id(slos, "latencia", "resumo-anual-rapido")
        alvo_p95_ms = float(resumo_slo["objetivo_p95_s"]) * 1000 if resumo_slo else 300.0

        p95 = perfil.get("summary_p95_ms")
        erro = perfil.get("taxa_erro")

        linhas.append(
            {
                "metrica": "p95 /limits/summary",
                "medido": f"{p95:.0f} ms" if p95 is not None else "—",
                "alvo": f"< {alvo_p95_ms:.0f} ms",
                "ok": p95 is not None and p95 < alvo_p95_ms,
            }
        )
        linhas.append(
            {
                "metrica": "taxa de erro",
                "medido": f"{erro * 100:.2f}%" if erro is not None else "—",
                "alvo": "< 1,00%",
                "ok": erro is not None and erro < 0.01,
            }
        )

        for linha in linhas:
            destino = ok if linha["ok"] else violacoes
            destino.append(f"{linha['metrica']}: medido {linha['medido']}, alvo {linha['alvo']}")

    estresse_path = entrada / "estresse.json"
    if estresse_path.exists():
        estresse = json.loads(estresse_path.read_text(encoding="utf-8"))
        ponto = estresse.get("ponto_de_saturacao_vus")
        linhas.append(
            {
                "metrica": "ponto de saturação",
                "medido": f"{ponto} VUs" if ponto else "não atingido",
                "alvo": estresse.get("observacao", ""),
                "ok": True,  # informativo, não é gate
            }
        )
        ok.append(estresse.get("observacao", "estresse: sem observação"))

    return ok, violacoes, linhas


def main() -> int:
    # A saída tem acentos; consoles Windows em cp1252 quebrariam.
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8")

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--entrada", type=Path, default=Path("resultados"))
    p.add_argument("--slos", type=Path, default=Path("docs/observabilidade/slos.yaml"))
    p.add_argument("--modo", choices=["gate", "smoke"], default="gate")
    args = p.parse_args()

    if not (args.entrada / "perfil-mei.json").exists():
        print(f"::error::não encontrei {args.entrada}/perfil-mei.json — o k6 rodou?")
        return 1

    ok, violacoes, linhas = verificar(args.entrada, args.slos)

    print("\n| Métrica | Medido | Alvo | Resultado |")
    print("| --- | --- | --- | --- |")
    for linha in linhas:
        marca = "ok" if linha["ok"] else "FALHOU"
        print(f"| {linha['metrica']} | {linha['medido']} | {linha['alvo']} | {marca} |")
    print()

    if violacoes and args.modo == "gate":
        for v in violacoes:
            print(f"::error::SLO violado — {v}")
        print(f"\n{len(violacoes)} violação(ões) de SLO sob carga.")
        return 1

    if violacoes:
        for v in violacoes:
            print(f"::warning::SLO fora do alvo no smoke (não reprova) — {v}")

    print("Carga dentro dos SLOs." if not violacoes else "Smoke concluído.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
