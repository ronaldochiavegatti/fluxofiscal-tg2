# ADR-0019 — Serviço de Notificações com banco próprio

- **Data:** 2026-09-10
- **Estado:** Aceita
- **Contexto:** Preparação da Onda 4 (dashboard e motor de ritmo); US-29, US-29b, US-29c

## Contexto

O `docs/arquitetura/README.md` já prevê um contexto genérico **Notificação**,
serviço `notifications`, como consumidor de `alerta.disparado`
([ADR-0006](0006-eventos-com-redis-streams-e-outbox.md), tabela de eventos). Até
agora ele não existia: o alerta de 80% do limite mora num `useMemo` no frontend.

A Onda 4 traz o motor de ritmo (US-28) e três histórias de alerta:

- **US-29** — alerta acionável, com dedup no mesmo nível, notificação só na
  escalada, teto diário de 3.
- **US-29b** — alertas de contexto do negócio (inatividade, mês atípico, DAS).
- **US-29c** — centro de notificações in-app, com feed cronológico, estado de
  lido, filtro por nível e memória de dispensa.

Nada disso funciona sem estado que sobreviva a reinício: "o mesmo alerta não
repete amanhã", "3 já foram enviados hoje", "dispensei este e ele não deve
voltar como banner". É um feed transacional por usuário — escrita frequente,
leitura por faixa de tempo, contadores por dia.

Duas decisões precisam ficar de pé antes do fan-out da onda, porque tocam
arquivos compartilhados (Compose, matriz de CI): **existe um serviço novo** e
**onde ele guarda o feed**.

## Decisão

**Serviço `notifications` dedicado**, FastAPI, no mesmo molde de `insights` e
`worker`. Ele consome `alerta.disparado` do barramento, aplica as regras de
ruído (dedup, escalada, teto) e serve o feed ao frontend por
`GET /notifications/...`. A avaliação das regras de alerta continua no
`insights` (ADR-0009) — o `notifications` recebe o alerta pronto e decide
apenas **se e como** notificar.

**Banco próprio: `notifications_db`, PostgreSQL 16**, um contêiner espelhando
`insights_db` — healthcheck `pg_isready`, volume `notifications_db_data`,
credenciais locais no Compose. O serviço fala com ele por SQLAlchemy.

Descartado **reusar o MongoDB**: o dono do Mongo é o `documents`
([ADR-0005](0005-mongodb-para-metadados-e-auditoria.md)), e o feed é relacional
por natureza (agregação por dia, junção com o nível anterior para detectar
escalada) — encaixa mal em documento. Descartado **reusar o `insights_db`**:
são contextos delimitados diferentes, com ciclos de release e de dado
independentes; compartilhar o banco acopla os dois pelo esquema, que é
exatamente o que a separação de serviços evita.

## Consequências

**A favor**

- US-29/29b/29c entram como fan-out puro: o serviço, o banco, a rota do gateway,
  a entrada na matriz de CI/CD e o scrape do Prometheus já estão no lugar.
- O feed persiste; as regras de ruído (dedup, escalada, teto) têm onde guardar
  estado.
- Fronteira limpa: `insights` decide *o que é alerta*, `notifications` decide
  *o que vira aviso* — cada um testável isolado.

**Contra**

- Mais um serviço e mais um banco para operar e subir no `docker compose up`.
  Mitigado: nenhum serviço existente declara `depends_on` no `notifications`, e
  o `--wait-timeout` da CI subiu para 720 s.
- Duplicação de identidade do usuário (o e-mail) em mais um banco. Aceitável —
  é o mesmo padrão dos outros serviços, e a introdução de JWT depois
  ([ADR-0011](0011-manter-autenticacao-simplificada.md)) não muda o esquema do
  feed.

## Notas de implementação

O esqueleto desta PR de preparação traz só `/health`, métricas, a fiação de
observabilidade e flags, e `db.py` com `engine`/`SessionLocal`/`criar_tabelas`
sobre um `Base` ainda vazio. Os modelos do feed e o consumidor de
`alerta.disparado` entram com as histórias, atrás da flag `alertas-ritmo-vendas`.
