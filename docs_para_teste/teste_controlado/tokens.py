"""Confere o consumo de tokens registrado pelo sistema (revisão MD7 do orientador).

Roda DENTRO do contêiner do serviço, com o mesmo código e a mesma chave da
pilha. Para cada chamada ao Gemini, compara três números:
  1. o que o sistema registra na métrica (função registrar_custo_gemini),
     capturado substituindo essa função;
  2. o usage_metadata completo devolvido pela API (inclui tokens de raciocínio,
     thoughts_token_count, que a API cobra como saída);
  3. uma contagem independente da entrada, pelo endpoint count_tokens da API.

Uso (pilha no ar, a partir desta pasta):
    docker exec -i agent_service python - agente < tokens.py
    docker cp 04_venda_nfse.txt documents_service:/tmp/ ; (idem para .png/.jpg)
    docker exec -i documents_service python - documentos /tmp/04_venda_nfse.txt ... < tokens.py
Saída: JSON no stdout (redirecione para tokens_<servico>_<data>.json).
"""

import json
import sys

registros = []
respostas = []


def capturar_registro(operacao, modelo, tokens_entrada, tokens_saida):
    registros.append({"entrada": tokens_entrada, "saida": tokens_saida})


def envolver(cliente):
    original = cliente.models.generate_content

    def generate_content(**kw):
        r = original(**kw)
        u = r.usage_metadata
        respostas.append(
            {
                "contents": kw["contents"],
                "prompt_token_count": u.prompt_token_count,
                "candidates_token_count": u.candidates_token_count,
                "thoughts_token_count": getattr(u, "thoughts_token_count", None) or 0,
                "total_token_count": u.total_token_count,
            }
        )
        return r

    cliente.models.generate_content = generate_content


def contar(cliente, modelo, contents):
    return cliente.models.count_tokens(model=modelo, contents=contents).total_tokens


def linha(rotulo, cliente, modelo):
    reg, resp = registros[-1], respostas[-1]
    return {
        "item": rotulo,
        "registrado_entrada": reg["entrada"],
        "registrado_saida": reg["saida"],
        "api_prompt_token_count": resp["prompt_token_count"],
        "api_candidates_token_count": resp["candidates_token_count"],
        "api_thoughts_token_count": resp["thoughts_token_count"],
        "api_total_token_count": resp["total_token_count"],
        "count_tokens_entrada": contar(cliente, modelo, resp["contents"]),
    }


def agente():
    from app import main

    main.registrar_custo_gemini = capturar_registro
    envolver(main.gemini_client)
    perguntas = [
        "Se eu faturar mais do que o teto permitido no ano, o que acontece comigo?",
        "Aquele boleto que pago todo mês como MEI serve pra quê?",
        "Tenho que prestar contas à Receita de quanto ganhei no ano anterior?",
    ]
    email = "tokens.tg@fluxofiscal.tech"
    db = main.SessionLocal()
    out = []
    for p in perguntas:
        retrato = main.traduzir_resumo_limits(main.get_limits_summary(email))
        emb = main.embed_text(p)
        prompt = main.build_prompt(
            retrato=retrato,
            user_message=p,
            email=email,
            knowledge_hits=main.retrieve_knowledge(db, emb, top_k=3),
            document_hits=main.retrieve_document_chunks(db, email, emb, top_k=3),
        )
        main.call_gemini(prompt)
        out.append(linha(p, main.gemini_client, main.GEMINI_MODEL))
    return out


def documentos(arquivos):
    from app import main, processamento

    envolver(main.gemini_client)
    out = []
    import time

    for caminho in arquivos:
        dados = open(caminho, "rb").read()
        for tentativa in range(1, 6):  # 503 de alta demanda é transitório
            try:
                if caminho.endswith(".txt"):
                    processamento.gemini_de_texto(
                        main.gemini_client,
                        main.GEMINI_MODEL,
                        dados.decode("utf-8"),
                        capturar_registro,
                    )
                else:
                    mime = "image/png" if caminho.endswith(".png") else "image/jpeg"
                    processamento.gemini_de_imagem(
                        main.gemini_client, main.GEMINI_MODEL, dados, mime, capturar_registro
                    )
                break
            except processamento.FalhaTransitoriaGemini:
                time.sleep(20 * tentativa)
        out.append(linha(caminho.rsplit("/", 1)[-1], main.gemini_client, main.GEMINI_MODEL))
    return out


if __name__ == "__main__":
    modo = sys.argv[1]
    linhas = agente() if modo == "agente" else documentos(sys.argv[2:])
    print(json.dumps(linhas, ensure_ascii=False, indent=2))
