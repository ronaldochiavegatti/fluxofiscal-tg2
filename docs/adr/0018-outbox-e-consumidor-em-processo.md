# ADR-0018 — Publicador e consumidor de eventos em processo

- **Data:** 2026-09-09
- **Estado:** Aceita
- **Contexto:** US-21 (eventos de domínio com Outbox)

## Contexto

O ADR-0006 fixou o **quê**: Outbox transacional, Redis Streams com grupos de
consumidores, consumo idempotente, fila morta após 5 tentativas. A US-21
implementa isso e precisa decidir o **como** — onde o publicador roda, como o
grupo é criado, o que é adiado.

## Decisão

**Publicador em thread dentro do Limits.** O `Publicador` (`limits/app/eventos.py`)
sobe como uma thread daemon no `lifespan`, quando `eventos-outbox` está ligada.
Ele varre `outbox WHERE enviado_em IS NULL ORDER BY id` a cada 0,5 s, faz `XADD`
e marca a linha. Um processo separado só de publicação seria mais isolado, mas
adiciona um contêiner, um deploy e um ponto de monitoração para um trabalho que
são três linhas de SQL num laço. Na escala do TG, a thread paga o custo.

**Escrita atômica por `flush` + `commit` único.** O handler faz
`db.add(transacao); db.flush(); emitir_evento(db, ...); db.commit()`. O `flush`
atribui o `id` da transação antes de montar o envelope; o `commit` fecha a
transação com a linha de negócio e a linha da outbox juntas. Se `criar_envelope`
levantar, o `commit` não acontece e nada é persistido — é o cenário "publicação
é atômica com a escrita".

**Grupo de consumidores criado em `id=0`.** `XGROUP CREATE ... 0 MKSTREAM`. O
`0` faz o grupo enxergar a stream inteira desde o começo, então eventos
publicados antes de o Insights subir pela primeira vez não se perdem. Ao subir,
o consumidor primeiro **drena a própria PEL** (`XREADGROUP ... 0`, reprocessa o
que pegou e não confirmou — idempotente) e só depois lê novos (`>`).

**`FORCAR_EVENTOS_OUTBOX=true`** liga o barramento sem depender do Unleash, no
mesmo espírito de `OTEL_TRACES_ENABLED`. É o que o job de integração da CI usa
para o teste de caos (derruba o Insights, cria 5 transações, sobe o Insights,
verifica que os 5 foram processados e o backlog zerou).

## Consequências

**A favor**

- Zero infraestrutura nova: Redis já estava no Compose (ADR-0003).
- A garantia do Outbox não depende de o publicador estar de pé no instante da
  escrita — a linha commitada é a fonte da verdade, e a varredura seguinte a
  pega.
- O consumidor idempotente (`eventos_processados` + `db.get` antes de aplicar)
  absorve a entrega ao-menos-uma-vez sem efeito duplicado.

**Contra**

- A thread do publicador compartilha o processo do Limits: um bug nela (laço
  quente, vazamento) afeta o serviço que atende o usuário. Mitigado por
  `try/except` no laço e intervalo fixo.
- Um Limits com várias réplicas teria N publicadores varrendo a mesma outbox.
  Hoje é réplica única; quando não for, a varredura precisa de
  `SELECT ... FOR UPDATE SKIP LOCKED`. Anotado como dívida.

## Adiado desta história

- **Fila morta explícita (`dlq:<stream>`).** Hoje um evento que o consumidor não
  consegue aplicar fica pendente (PEL) e é retentado no próximo `drenar`. Não há
  contador de tentativas por evento nem stream de descarte. Entra quando houver
  um consumidor cujo processamento possa falhar de forma não transitória — o
  Insights atual só faz aritmética, que não falha.
- **Reconstrução da projeção a partir do zero** (reprocessar a stream inteira).
  A projeção do Insights é mínima nesta história; a reconstrução completa entra
  com as projeções ricas da US-23.
- **Consumidores `auth`/`billing` e a trilha de auditoria como consumidor**
  (ADR-0006 os lista). Entram quando cada um tiver o que fazer com o evento.

## Referências

- ADR-0006 (a decisão de barramento que esta implementa).
- Documentação do Redis sobre Streams, `XGROUP`, `XREADGROUP`, `XPENDING`.
- Kleppmann, M. *Designing Data-Intensive Applications*, 2017, cap. 11.
