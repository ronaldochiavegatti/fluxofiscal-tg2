# Runbooks

Um alerta de severidade **página** sem runbook é um alerta que ninguém sabe
atender. Cada um aqui responde três perguntas: *o que está acontecendo*,
*como confirmar* e *o que fazer agora*.

| Alerta | Runbook | Onda |
| --- | --- | --- |
| `SLOQueimaDeOrcamento` | [`error-budget-burn.md`](error-budget-burn.md) | 1 (US-13) |
| `FilaAcumulando` | _pendente_ | 3 (US-18) |
| `OutboxTravado` | _pendente_ | 3 (US-21) |
| `ConciliacaoDivergente` | _pendente_ | 3 (US-23) |

Os alertas de fila, outbox e conciliação dependem de infraestrutura que só
existe a partir da Onda 3 — os runbooks entram junto com eles.

O `runbook_url` de cada alerta é gerado automaticamente por
`tools/observabilidade/gerar_alertas.py` a partir do campo `runbook:` em
`docs/observabilidade/slos.yaml`.
