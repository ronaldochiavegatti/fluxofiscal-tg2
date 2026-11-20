"""Executa o protocolo do teste controlado e registra o resultado POR ITEM.

Responde às revisões do orientador (MD24/25/39/40): a rodada de 19/10/2026
só guardou agregados. Este script grava, para cada nota, os valores esperados
e obtidos de valor/data/CNPJ, o método (gemini/regex) e o tempo; e, para cada
pergunta, a posição do trecho esperado entre as fontes devolvidas, o tempo e
a resposta gerada — que é o insumo da conferência factual manual.

Uso (pilha no ar, com GEMINI_API_KEY):
    python avaliar.py                      # gateway local http://localhost:8000
    python avaliar.py --base https://api.exemplo
Saída: resultados_<data>.json e resultados_<data>.md nesta pasta.

Usa um e-mail de avaliação novo a cada rodada (não toca nos dados do usuário
demo e não reaproveita extrações em cache de rodadas anteriores) e não confirma
nenhuma nota: só /upload (extração) e /chat (RAG). Só biblioteca padrão.

    python avaliar.py --conjunto artigo    # só as 12 do protocolo do artigo
    python avaliar.py                      # as 52 (artigo + extras), padrão
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
EMAIL = f"avaliacao.tg+{datetime.now():%Y%m%d%H%M%S}@fluxofiscal.tech"
CNPJ_MEI = "12.345.678/0001-90"


def so_digitos(v) -> str:
    return re.sub(r"\D", "", str(v or ""))


def normaliza_valor(v) -> float | None:
    """Acerto exato = mesmo valor em centavos, após normalizar "1.234,56"/1234.56."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    s = str(v).replace("R$", "").strip()
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def normaliza_data(v) -> str | None:
    """Acerto exato = mesma data ISO (AAAA-MM-DD); aceita DD/MM/AAAA."""
    s = str(v or "").strip()
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    return m.group(0) if m else None


def post_multipart(url: str, campos: dict, arquivo: Path) -> dict:
    limite = uuid.uuid4().hex
    partes = []
    for k, v in campos.items():
        partes.append(
            f'--{limite}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        )
    partes.append(
        (
            f'--{limite}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="{arquivo.name}"\r\nContent-Type: application/octet-stream\r\n\r\n'
        ).encode()
        + arquivo.read_bytes()
        + b"\r\n"
    )
    partes.append(f"--{limite}--\r\n".encode())
    req = urllib.request.Request(
        url,
        data=b"".join(partes),
        headers={"Content-Type": f"multipart/form-data; boundary={limite}"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())


def post_json(url: str, corpo: dict) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())


def avaliar_extracao(base: str, gabarito: dict, conjunto: str) -> list[dict]:
    linhas = []
    notas = [n for n in gabarito["notas"] if conjunto == "todas" or n.get("conjunto") == conjunto]
    for nota in notas:
        arq = AQUI / nota["arquivo"]
        t0 = time.perf_counter()
        try:
            resp = post_multipart(
                f"{base}/documents/upload", {"email": EMAIL, "user_cnpj": CNPJ_MEI}, arq
            )
            erro = None
        except Exception as exc:  # registra e segue: uma nota não derruba a rodada
            resp, erro = {}, f"{type(exc).__name__}: {exc}"
        dt = time.perf_counter() - t0
        sd = resp.get("structured_data") or {}
        obtido = {
            "valor": normaliza_valor(sd.get("value")),
            "data": normaliza_data(sd.get("date")),
            "cnpj": so_digitos(sd.get("cnpj_emitente")),
        }
        esperado = {
            "valor": round(nota["valor_total"], 2),
            "data": nota["data"],
            "cnpj": so_digitos(nota["cnpj_emitente"]),
        }
        linhas.append(
            {
                "arquivo": nota["arquivo"],
                "conjunto": nota.get("conjunto"),
                "tipo": nota.get("tipo"),
                "documento": nota["documento"],
                "erro": erro,
                "esperado": esperado,
                "obtido": obtido,
                "acerto": {k: esperado[k] == obtido[k] for k in esperado},
                "metodo": resp.get("extraction_method"),
                "duplicado": resp.get("duplicado", False),
                "tempo_s": round(dt, 2),
            }
        )
        print(f"{nota['arquivo']}: {linhas[-1]['acerto']} {dt:.1f}s")
    return linhas


def avaliar_rag(base: str, gabarito: dict) -> list[dict]:
    linhas = []
    for i, p in enumerate(gabarito["perguntas_rag"], 1):
        t0 = time.perf_counter()
        resp = post_json(f"{base}/agent/chat", {"email": EMAIL, "message": p["pergunta"]})
        dt = time.perf_counter() - t0
        # As fontes vêm na ordem do ranking: "<título> (<fonte>)" das regras,
        # depois os documentos do usuário. Só as 3 primeiras regras são visíveis.
        regras = [s for s in resp.get("sources", []) if not s.startswith("Documento:")]
        posicao = next(
            (k for k, s in enumerate(regras, 1) if s.startswith(p["trecho_esperado"])), None
        )
        linhas.append(
            {
                "n": i,
                "pergunta": p["pergunta"],
                "trecho_esperado": p["trecho_esperado"],
                "fontes": regras,
                "posicao": posicao,
                "tempo_s": round(dt, 2),
                "resposta": resp.get("reply", ""),
            }
        )
        print(f"P{i}: posição {posicao} {dt:.1f}s")
    return linhas


def markdown(ext: list[dict], rag: list[dict], meta: dict) -> str:
    sim = lambda b: "sim" if b else "NÃO"  # noqa: E731
    out = [f"# Teste controlado — {meta['quando']}", "", f"Base: {meta['base']}", ""]
    for nome in ("artigo", "extra"):
        sub = [e for e in ext if e["conjunto"] == nome]
        if not sub:
            continue
        tres = sum(all(e["acerto"].values()) for e in sub)
        campos = sum(sum(e["acerto"].values()) for e in sub)
        ts = [e["tempo_s"] for e in sub]
        out.append(
            f"- {nome}: {tres}/{len(sub)} notas com os três campos; {campos}/{3 * len(sub)} "
            f"campos; tempo médio {sum(ts) / len(ts):.1f} s ({min(ts)}–{max(ts)} s)"
        )
    out.append("")
    out += ["| Arquivo | Valor esp./obt. | Data esp./obt. | CNPJ | Método | Tempo (s) |", "|---|---|---|---|---|---|"]
    for e in ext:
        a, x, o = e["acerto"], e["esperado"], e["obtido"]
        out.append(
            f"| {e['arquivo']} | {x['valor']} / {o['valor']} ({sim(a['valor'])}) | "
            f"{x['data']} / {o['data']} ({sim(a['data'])}) | {sim(a['cnpj'])} | "
            f"{e['metodo']} | {e['tempo_s']} |"
        )
    out += ["", "| # | Trecho esperado | Posição | Tempo (s) |", "|---|---|---|---|"]
    for r in rag:
        out.append(f"| {r['n']} | {r['trecho_esperado']} | {r['posicao'] or '>3'} | {r['tempo_s']} |")
    out += ["", "## Respostas (para a conferência factual)", ""]
    for r in rag:
        out += [f"### P{r['n']}. {r['pergunta']}", "", r["resposta"], ""]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--conjunto", choices=["artigo", "extra", "todas"], default="todas")
    args = ap.parse_args()
    gabarito = json.loads((AQUI / "gabarito.json").read_text(encoding="utf-8"))
    quando = datetime.now().strftime("%Y-%m-%d_%H%M")
    ext = avaliar_extracao(args.base, gabarito, args.conjunto)
    rag = avaliar_rag(args.base, gabarito)
    meta = {"quando": quando, "base": args.base, "email": EMAIL, "conjunto": args.conjunto}
    (AQUI / f"resultados_{quando}.json").write_text(
        json.dumps({"meta": meta, "extracao": ext, "rag": rag}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (AQUI / f"resultados_{quando}.md").write_text(markdown(ext, rag, meta), encoding="utf-8")
    print(f"ok: resultados_{quando}.json / .md")


if __name__ == "__main__":
    main()
