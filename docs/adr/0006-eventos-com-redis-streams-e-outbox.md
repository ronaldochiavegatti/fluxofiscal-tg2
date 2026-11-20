# ADR-0006 — Barramento de eventos com Redis Streams e padrão Outbox

- **Data:** 2026-08-22
- **Estado:** Aceita

## Contexto

A comunicação entre serviços hoje é toda síncrona e ponto a ponto, com o
chamador conhecendo a URL do chamado. O `documents` chama
`POST /limits/transactions` e, logo depois, `POST /agent/index-document`. Se o
Limits estiver fora do ar, a confirmação falha inteira. Se o Agent estiver fora,
a captura de `httpx.RequestError` engole o erro em silêncio e o documento
simplesmente nunca é indexado no RAG — sem log, sem alerta, sem retentativa.

Esse acoplamento também trava a evolução. O serviço de Insights (ADR-0009)
precisa reagir a toda transação criada; a notificação in-app precisa reagir a
todo alerta disparado. No modelo atual, cada consumidor novo exige alterar o
produtor.

## Decisão

Introduzir um barramento de eventos sobre **Redis Streams**, com grupos de
consumidores, e garantir a publicação com o **padrão Outbox transacional**.

**Eventos do domínio** — nomeados no passado, porque descrevem fato consumado:

| Evento | Produtor | Consumidores |
| --- | --- | --- |
| `documento.recebido` | documents | worker |
| `documento.extraido` | worker | documents, insights |
| `documento.confirmado` | documents | limits, agent, insights, auditoria |
| `transacao.criada` | limits | insights, auditoria |
| `transacao.atualizada` | limits | insights, auditoria |
| `transacao.removida` | limits | insights, auditoria |
| `alerta.disparado` | insights | notifications |
| `tokens.consumidos` | billing | auditoria |

**Envelope padrão**, versionado desde o primeiro dia:

```json
{
  "evento_id": "uuid",
  "tipo": "transacao.criada",
  "versao": 1,
  "ocorrido_em": "2026-08-22T13:00:00Z",
  "produtor": "limits",
  "trace_id": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
  "chave_particao": "mei@exemplo.com",
  "dados": {}
}
```

**Outbox.** O produtor grava o evento numa tabela `outbox` **dentro da mesma
transação** que altera o dado de negócio. Um publicador varre a tabela e envia
ao Redis. Ou os dois acontecem, ou nenhum acontece — o que elimina a janela em
que a transação é gravada mas o evento se perde.

**Consumo idempotente.** Todo consumidor mantém uma tabela
`eventos_processados` com o identificador do evento. Reentrega vira operação sem
efeito, que é exatamente o que precisa acontecer num barramento com garantia de
entrega ao menos uma vez.

**Fila morta.** Após 5 tentativas o evento vai para `dlq:<stream>`, com métrica
e alerta próprios.

O que continua **síncrono**: toda leitura que o usuário está esperando na tela,
como `GET /limits/summary` e `POST /agent/chat`. Evento serve para propagar fato
consumado, não para responder pergunta.

## Consequências

**A favor**

- Adicionar consumidor deixa de exigir mudança no produtor — é o que torna o
  serviço de Insights viável sem tocar no Limits.
- Indisponibilidade temporária de um consumidor deixa de derrubar a operação do
  usuário: o evento espera na stream.
- A trilha de auditoria vira mais um consumidor, sem instrumentação espalhada
  por todos os serviços.
- O identificador de rastro no envelope mantém o tracing distribuído contínuo
  através do barramento.

**Contra**

- Consistência entre serviços passa a ser eventual. Para este domínio é
  aceitável: o dashboard refletir uma venda 200 ms depois não muda decisão
  nenhuma do usuário. Onde não seria aceitável — o próprio total do resumo
  anual — a leitura continua síncrona contra o Limits.
- Outbox exige um publicador rodando e monitorado.
- Depurar fluxo assíncrono é mais difícil, o que reforça a necessidade do
  tracing distribuído do ADR-0007.

## Alternativas descartadas

**Kafka.** Oferece retenção longa, reprocessamento e particionamento de verdade.
Descartado pelo peso operacional diante da escala do trabalho e por adicionar
uma stack que o artigo não menciona.

**Chamadas REST diretas com retentativa.** Reduziria a perda silenciosa, mas
manteria o acoplamento e o problema de cada consumidor novo exigir alteração no
produtor.

**Apenas Celery.** Celery é fila de tarefas: um produtor manda um trabalho a um
executor. Não é publicação e assinatura — vários consumidores independentes
reagindo ao mesmo fato. Os dois coexistem, cada um no seu papel.

## Referências

- Richardson, C. *Microservices Patterns*, 2018, cap. 3 e 4 (Outbox e
  mensageria assíncrona).
- Documentação do Redis sobre Streams e grupos de consumidores.
- Especificação W3C Trace Context, para propagação do identificador de rastro.
