from prometheus_client import Counter, Histogram

# US-11 — Métricas de negócio (Agent Orchestrator)

rag_similaridade_melhor = Histogram(
    "rag_similaridade_melhor",
    "Melhor (maior) score de similaridade retornado em uma consulta",
    ["tipo_base"],
    buckets=[0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.98, 1.0],
)

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total de tokens consumidos em chamadas ao Gemini",
    ["modelo", "operacao", "direcao"],
)

llm_custo_estimado_reais_total = Counter(
    "llm_custo_estimado_reais_total",
    "Custo estimado acumulado do LLM em BRL",
    ["modelo", "operacao"],
)

# Custo aproximado do Gemini 1.5 Flash (agosto 2026):
# $0.075 / 1M tokens entrada, $0.30 / 1M tokens saída.
# Dólar ~R$ 5.50
CUSTO_POR_TOKEN_BRL = {
    "entrada": (0.075 / 1_000_000) * 5.50,
    "saida": (0.30 / 1_000_000) * 5.50,
}


def registrar_custo_gemini(operacao: str, modelo: str, tokens_entrada: int, tokens_saida: int):
    """Registra uso de tokens e custo financeiro estimado."""
    llm_tokens_total.labels(modelo=modelo, operacao=operacao, direcao="entrada").inc(tokens_entrada)
    llm_tokens_total.labels(modelo=modelo, operacao=operacao, direcao="saida").inc(tokens_saida)

    custo_entrada = tokens_entrada * CUSTO_POR_TOKEN_BRL["entrada"]
    custo_saida = tokens_saida * CUSTO_POR_TOKEN_BRL["saida"]

    llm_custo_estimado_reais_total.labels(modelo=modelo, operacao=operacao).inc(
        custo_entrada + custo_saida
    )
