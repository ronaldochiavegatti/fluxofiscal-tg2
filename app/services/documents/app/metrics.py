from prometheus_client import Counter, Histogram

# US-11 — Métricas de negócio (Documents)

documentos_processados_total = Counter(
    "documentos_processados_total",
    "Número total de documentos processados (upload)",
    ["metodo", "formato"],
)

extracao_confianca = Histogram(
    "extracao_confianca",
    "Distribuição da confiança da extração",
    ["metodo"],
    buckets=[0.1, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 0.99, 1.0],
)

# #100: fotos barradas pela checagem de qualidade antes do OCR e do Gemini.
# Cada uma é uma chamada ao Gemini que deixou de ser feita.
fotos_recusadas_total = Counter(
    "documentos_fotos_recusadas_total",
    "Fotos recusadas por qualidade antes da leitura (chamadas ao Gemini evitadas)",
    ["motivo"],
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
