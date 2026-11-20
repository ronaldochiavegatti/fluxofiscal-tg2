"""Teste de abstenção do assistente (revisões MD11/MD27 do orientador).

Faz ao /agent/chat as perguntas de perguntas_abstencao.json, cuja resposta não
está na base de regras, e também as cinco perguntas do teste de recuperação
(gabarito.json), para conferir que a mudança de prompt não piora as respostas
que têm suporte na base. Grava as respostas na íntegra; a classificação
(absteve-se / respondeu sem suporte) é feita à mão, como a conferência factual.

Uso (pilha no ar):
    python abstencao.py --rotulo antes     # prompt sem instrução de abstenção
    python abstencao.py --rotulo depois    # depois da mudança no Orquestrador
Saída: abstencao_<rotulo>_<data>.json e .md nesta pasta. Só biblioteca padrão.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime

from avaliar import AQUI, EMAIL, post_json


ERRO_GEMINI = "Houve um erro ao chamar o modelo Gemini"


def perguntar(base: str, pergunta: str, tentativas: int = 5) -> dict:
    """Repete a pergunta quando o Gemini devolve erro transitório (503 de alta
    demanda). O tempo registrado é o da tentativa que deu certo."""
    for n in range(1, tentativas + 1):
        t0 = time.perf_counter()
        resp = post_json(f"{base}/agent/chat", {"email": EMAIL, "message": pergunta})
        dt = time.perf_counter() - t0
        if not resp.get("reply", "").startswith(ERRO_GEMINI) or n == tentativas:
            break
        time.sleep(20 * n)
    return {
        "fontes": resp.get("sources", []),
        "tempo_s": round(dt, 2),
        "tentativas": n,
        "resposta": resp.get("reply", ""),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--rotulo", required=True, help="ex.: antes, depois")
    args = ap.parse_args()
    fora = json.loads((AQUI / "perguntas_abstencao.json").read_text(encoding="utf-8"))
    gab = json.loads((AQUI / "gabarito.json").read_text(encoding="utf-8"))

    linhas = []
    for p in fora["perguntas"]:
        linhas.append({"id": p["id"], "tipo": "fora_da_base", "pergunta": p["pergunta"]})
        linhas[-1].update(perguntar(args.base, p["pergunta"]))
        print(f"{p['id']}: {linhas[-1]['tempo_s']} s")
    for i, p in enumerate(gab["perguntas_rag"], 1):
        linhas.append({"id": f"P{i}", "tipo": "na_base", "pergunta": p["pergunta"]})
        linhas[-1].update(perguntar(args.base, p["pergunta"]))
        print(f"P{i}: {linhas[-1]['tempo_s']} s")

    quando = datetime.now().strftime("%Y-%m-%d_%H%M")
    meta = {"quando": quando, "base": args.base, "email": EMAIL, "rotulo": args.rotulo}
    nome = f"abstencao_{args.rotulo}_{quando}"
    (AQUI / f"{nome}.json").write_text(
        json.dumps({"meta": meta, "respostas": linhas}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md = [f"# Teste de abstenção ({args.rotulo}) — {quando}", ""]
    for r in linhas:
        md += [f"## {r['id']} ({r['tipo']}). {r['pergunta']}", "", r["resposta"], ""]
    (AQUI / f"{nome}.md").write_text("\n".join(md), encoding="utf-8")
    print(f"ok: {nome}.json / .md")


if __name__ == "__main__":
    main()
