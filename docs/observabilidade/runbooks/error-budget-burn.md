# Runbook — `SLOQueimaDeOrcamento`

## O que o alerta significa

A taxa de erro de um SLO de disponibilidade está consumindo o **orçamento de
erro** rápido demais. O alerta só dispara quando **duas janelas** estão
queimando ao mesmo tempo (Site Reliability Workbook, cap. 5):

| Rótulo `janela` | Janela longa | Janela curta | Fator | Severidade |
| --- | --- | --- | --- | --- |
| `queima-rapida` | 1h | 5m | 14,4× | página |
| `queima-media` | 6h | 30m | 6× | página |
| `queima-lenta` | 3d | 6h | 1× | ticket |

A janela curta evita que o alerta chegue tarde; a longa evita que ele dispare
por um pico de 30 segundos. Se só uma está queimando, **não** dispara.

O SLO afetado está no rótulo `slo` (`gateway-disponivel`, `limits-disponivel`
ou `insights-disponivel`). Os objetivos estão em
[`docs/observabilidade/slos.yaml`](../slos.yaml).

## Como confirmar

1. **Painel:** Grafana → *SLO e orçamento de erro*. Veja `slo:orcamento:consumido`
   para o SLO — acima de `1` o orçamento de 30 dias já estourou.
2. **Rastro:** no painel *RED por serviço*, identifique a rota com 5xx. Clique
   no pico → rastro → log (US-12).
3. **Escopo:** é um serviço só (`slo="limits-disponivel"`) ou tudo
   (`slo="gateway-disponivel"`)? Gateway queimando sem nenhum serviço
   específico queimando aponta para rede, banco compartilhado ou saturação.

```promql
# taxa de erro atual do SLO, por janela
slo:sli_erro:taxa5m{slo="limits-disponivel"}
slo:sli_erro:taxa1h{slo="limits-disponivel"}

# quais rotas estão devolvendo 5xx
sum(rate(http_requests_total{job="limits",status=~"5.."}[5m])) by (handler)
```

## O que fazer agora

1. **Estancar.** Se a queima veio de um deploy recente, reverta para a imagem
   anterior (as imagens são imutáveis e marcadas pelo SHA — ver
   [ADR-0014](../../adr/0014-entrega-continua-ate-o-ghcr.md)):
   ```bash
   docker compose -f docker-compose.release.yml pull
   docker compose -f docker-compose.release.yml up -d
   ```
2. **Banco.** `pg_isready` no `*_db` correspondente. Conexões esgotadas
   aparecem como 5xx em rajada. Reinicie o serviço, não o banco.
3. **Dependência externa.** Se for o `agent`/`documents` e os 5xx coincidirem
   com erro do Gemini, ligue a flag de corte `ops-desligar-gemini` — o serviço
   cai para o modo demo em vez de devolver erro.
4. **Sem causa óbvia.** Escale. Não fique reiniciando serviço no escuro.

## Depois

- Orçamento esgotado dispara a política de
  [`slos.yaml`](../slos.yaml) (`politica.orcamento_esgotado`): congelar
  entregas de funcionalidade até o orçamento voltar, registrar análise de
  causa raiz sem culpado no repositório.
- Se o alerta disparou sem impacto real de usuário, o SLO ou o alerta estão
  calibrados errado — abra PR ajustando `slos.yaml` com justificativa.
