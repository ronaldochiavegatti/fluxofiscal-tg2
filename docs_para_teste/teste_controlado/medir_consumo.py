"""Rodada de medição do consumo registrado no billing (ADR-0024).

Faz o ciclo completo com um usuário de avaliação novo: envia e CONFIRMA as 12
notas do protocolo do artigo (extração + indexação no RAG) e faz as 5
perguntas do teste de recuperação (embedding da pergunta + geração). Depois lê
o extrato de consumo no billing e compara o débito fixo atual com o débito
proporcional da tabela de conversão versionada.

Pré-requisito: pilha no ar com a flag `billing-tokens-reais` ligada.
Uso: python medir_consumo.py [--base http://localhost:8000]
Saída: consumo_<data>.json e .md nesta pasta. Só biblioteca padrão.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from datetime import datetime

from abstencao import perguntar
from avaliar import AQUI, CNPJ_MEI, EMAIL, post_json, post_multipart

# Débito fixo atual do billing (TOKEN_COSTS), pedido pelo frontend por ação.
DEBITO_FIXO = {"document_confirm": 15, "chat_message": 5}


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    args = ap.parse_args()
    gab = json.loads((AQUI / "gabarito.json").read_text(encoding="utf-8"))
    notas = [n for n in gab["notas"] if n.get("conjunto") == "artigo"]

    confirmadas = 0
    for nota in notas:
        resp = post_multipart(
            f"{args.base}/documents/upload",
            {"email": EMAIL, "user_cnpj": CNPJ_MEI},
            AQUI / nota["arquivo"],
        )
        sd = resp.get("structured_data") or {}
        post_json(
            f"{args.base}/documents/confirm",
            {
                "email": EMAIL,
                "amount": nota["valor_total"],
                "tx_date": nota["data"],
                "tx_type": "venda" if nota["tipo"] == "venda" else "compra",
                "cnpj_emitente": nota["cnpj_emitente"],
                "description": sd.get("description"),
                "source_filename": nota["arquivo"],
                "ocr_text": resp.get("ocr_text"),
                "documento_id": resp.get("documento_id"),
            },
        )
        confirmadas += 1
        print(f"{nota['arquivo']}: enviada e confirmada")

    for p in gab["perguntas_rag"]:
        r = perguntar(args.base, p["pergunta"])
        print(f"chat: {r['tempo_s']} s")

    time.sleep(5)  # o registro é enviado em segundo plano pelos serviços
    extrato = get_json(f"{args.base}/billing/usage/{EMAIL}?limite=500")
    perguntas = len(gab["perguntas_rag"])
    fixo = confirmadas * DEBITO_FIXO["document_confirm"] + perguntas * DEBITO_FIXO["chat_message"]
    proporcional = sum(t["creditos_proporcionais"] for t in extrato["totais"])
    custo = sum(t["custo_estimado_brl"] for t in extrato["totais"])

    quando = datetime.now().strftime("%Y-%m-%d_%H%M")
    meta = {
        "quando": quando,
        "base": args.base,
        "email": EMAIL,
        "notas_confirmadas": confirmadas,
        "perguntas": perguntas,
        "debito_fixo_creditos": fixo,
        "debito_proporcional_creditos": proporcional,
        "custo_estimado_brl": round(custo, 6),
    }
    (AQUI / f"consumo_{quando}.json").write_text(
        json.dumps({"meta": meta, "extrato": extrato}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md = [
        f"# Consumo registrado — {quando}",
        "",
        f"{confirmadas} notas confirmadas e {perguntas} perguntas ao chat; "
        f"tabela {extrato['versao_tabela']}.",
        "",
        "| Serviço | Operação | Modelo | Chamadas | Tokens entrada | Tokens saída "
        "| Créditos proporcionais | Custo estimado (R$) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for t in extrato["totais"]:
        md.append(
            f"| {t['servico']} | {t['operacao']} | {t['modelo']} | {t['chamadas']} | "
            f"{t['tokens_entrada']} | {t['tokens_saida']} | {t['creditos_proporcionais']} | "
            f"{t['custo_estimado_brl']:.6f} |"
        )
    md += [
        "",
        f"Débito fixo (15 por nota, 5 por mensagem): {fixo} créditos.",
        f"Débito proporcional (tabela versionada): {proporcional} créditos.",
        f"Custo estimado total: R$ {custo:.6f}.",
    ]
    (AQUI / f"consumo_{quando}.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md[-3:]))


if __name__ == "__main__":
    main()
