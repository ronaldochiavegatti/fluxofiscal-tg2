"""Métricas de negócio do Insights (US-11, ampliadas na US-23).

A conciliação noturna (ADR-0009) compara os totais do modelo de leitura com a
fonte da verdade (Limits). O SLO `conciliacao-projecao` de
`docs/observabilidade/slos.yaml` — divergência máxima de R$ 0,01, severidade
crítica — se alimenta destas séries.
"""

from prometheus_client import Counter, Gauge

conciliacao_execucoes_total = Counter(
    "insights_conciliacao_execucoes_total",
    "Execuções da conciliação da projeção contra o Limits",
)

conciliacao_divergencias_total = Counter(
    "insights_conciliacao_divergencias_total",
    "Divergências (acima da tolerância) detectadas na conciliação",
    ["campo"],
)

conciliacao_divergencia_reais = Gauge(
    "insights_conciliacao_divergencia_reais",
    "Maior divergência absoluta, em BRL, apurada na última conciliação",
    ["campo"],
)

reconstrucoes_total = Counter(
    "insights_reconstrucoes_total",
    "Reconstruções de projeção disparadas a partir do Limits",
)
