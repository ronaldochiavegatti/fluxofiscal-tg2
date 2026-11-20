#!/usr/bin/env python3
"""Gera as tabelas em Markdown da seção de resultados do artigo.

Lê os JSON de tests/load/ e produz um Markdown datado e com o commit, pronto
para colar no artigo — sem transcrição à mão, que é a maior fonte de erro em
trabalho com dado experimental.

Uso:
  python tests/benchmarks/gerar_tabelas.py --entrada resultados/ \\
    --saida resultados/tabelas-artigo.md
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

with contextlib.suppress(Exception):
    sys.stdout.reconfigure(encoding="utf-8")


def _commit() -> str:
    for chave in ("GITHUB_SHA",):
        if os.environ.get(chave):
            return os.environ[chave][:12]
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "desconhecido"


def _carregar(caminho: Path) -> dict | None:
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else None


def gerar(entrada: Path) -> str:
    perfil = _carregar(entrada / "perfil-mei.json")
    estresse = _carregar(entrada / "estresse.json")

    linhas = [
        "# Resultados dos testes de carga",
        "",
        f"- Data: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        f"- Commit: `{_commit()}`",
        "- Instrumento: k6 (`tests/load/`), SLOs em `docs/observabilidade/slos.yaml`",
        "",
    ]

    if perfil:
        linhas += [
            "## Perfil realista de MEI",
            "",
            f"{perfil.get('vus')} VUs por {perfil.get('duracao')}.",
            "",
            "| Métrica | Valor |",
            "| --- | --- |",
            f"| p95 de `/limits/summary` | {_ms(perfil.get('summary_p95_ms'))} |",
            f"| p99 de `/limits/summary` | {_ms(perfil.get('summary_p99_ms'))} |",
            f"| Taxa de erro | {_pct(perfil.get('taxa_erro'))} |",
            f"| Requisições por segundo | {_num(perfil.get('req_por_s'))} |",
            f"| Iterações completas | {perfil.get('iteracoes', '—')} |",
            f"| Dentro do SLO | {'sim' if perfil.get('aprovado') else 'não'} |",
            "",
        ]

    if estresse:
        linhas += [
            "## Ponto de saturação",
            "",
            f"{estresse.get('observacao', '')}",
            "",
            "| VUs | p95 `/limits/summary` | Viola SLO (300 ms) |",
            "| --- | --- | --- |",
        ]
        for d in estresse.get("degraus", []):
            viola = "—" if d.get("violou_slo") is None else ("sim" if d["violou_slo"] else "não")
            linhas.append(f"| {d['vus']} | {_ms(d.get('p95_ms'))} | {viola} |")
        linhas.append("")

    linhas += [
        "---",
        "",
        "Linha de base para comparação após a arquitetura assíncrona (Onda 3).",
        "",
    ]
    return "\n".join(linhas)


def _ms(v: float | None) -> str:
    return f"{v:.0f} ms" if isinstance(v, (int, float)) else "—"


def _pct(v: float | None) -> str:
    return f"{v * 100:.2f}%" if isinstance(v, (int, float)) else "—"


def _num(v: float | None) -> str:
    return f"{v:.1f}" if isinstance(v, (int, float)) else "—"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--entrada", type=Path, default=Path("resultados"))
    p.add_argument("--saida", type=Path, default=Path("resultados/tabelas-artigo.md"))
    args = p.parse_args()

    md = gerar(args.entrada)
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(md, encoding="utf-8", newline="\n")
    print(f"Escrito {args.saida}")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
