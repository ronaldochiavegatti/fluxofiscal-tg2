# RUNBOOK — da Onda 1 até a entrega do TG II

Sequência de comandos para levar o plano de `docs/` até o fim, com sessões
Claude Code em paralelo. Este arquivo tem o **porquê** de cada passo e as tabelas
de paralelismo. Os **comandos literais história por história**, prontos para
copiar e colar terminal a terminal, estão em `.claude/RUNBOOK-COMANDOS.md`.

Os comandos de `git` / `gh` são iguais em PowerShell e Git Bash. Rode sempre a
partir da raiz:

```
C:\Users\ronal\Desktop\TG 2
```

## Convenções

- **1 terminal = 1 worktree = 1 história = 1 sessão `claude`.**
- Worktree irmão por história: `..\ff-usNN` (fora da pasta do repo).
- Branch: `<tipo>/onda<N>-us<NN>-<resumo-kebab>` — ex.: `feat/onda3-us19-minio`.
- Título de PR: `<tipo>(<escopo>): US-NN <resumo>` — o squash merge o transforma
  no commit da `main`.
- O portão **`docker compose up --wait` roda um worktree por vez** (os
  `container_name` e as portas são fixos). Testes de unidade/contrato rodam em
  paralelo à vontade.
- Nunca `git push` na `main`. Nunca `gh pr merge` sem os portões locais verdes
  — GitHub Actions está desativado desde 12/09/2026
  ([ADR-0020](../docs/adr/0020-ci-local-sem-github-actions.md)), então não há
  check de CI pra esperar; a régua de "nunca vermelho" passa a valer sobre o
  resultado local, citado no commit/PR.

---

## BLOCO REUTILIZÁVEL — ciclo de uma história

Substitua `US-NN`, `<tipo>`, `<escopo>`, `<resumo-kebab>` e `<onda>`.

### 1. Criar o worktree a partir da `main` atualizada

```
cd "C:\Users\ronal\Desktop\TG 2"
git fetch origin
git worktree add "..\ff-usNN" -b <tipo>/onda<onda>-usNN-<resumo-kebab> origin/main
cd "..\ff-usNN"
git config --get core.hooksPath
```

O último comando deve responder `.githooks`. Se não, rode
`git config core.hooksPath .githooks`.

### 2. Implementar (sessão Claude Code, dentro do worktree)

```
claude
```

Dentro da sessão, cole:

```
Implemente a US-NN. Leia CLAUDE.md e .claude/PLAYBOOK.md primeiro. Use o agente
implementador-historia. Fique no serviço da história. Escreva um teste para cada
cenário Gherkin. Rode /portoes. PARE antes de abrir o PR.
```

Depois que ele parar:

```
/revisar
```

Resolva os bloqueadores que o revisor apontar (peça as correções na mesma
sessão). Quando estiver limpo:

```
/abrir-pr US-NN
```

Saia do `claude` (Ctrl+D).

### 3. Conferir os portões locais e mergear

GitHub Actions desativado (ADR-0020) — `gh pr checks --watch` não tem mais o
que esperar. O `/portoes` do passo 2 (e o `/revisar`) já são o portão; confira
o resultado citado no corpo do commit/PR antes de mergear:

```
cd "..\ff-usNN"
gh pr view --json title,body
```

Se os portões locais estavam verdes quando a história parou:

```
gh pr merge --squash --delete-branch
```

Se algo ficou vermelho: volte ao `claude` no mesmo worktree, corrija, rode
`/portoes` de novo, `git push`.

### 4. Limpar o worktree

```
cd "C:\Users\ronal\Desktop\TG 2"
git worktree remove "..\ff-usNN"
```

### 5. Rebase dos worktrees paralelos ainda abertos

Em cada outro worktree ativo:

```
git fetch origin && git rebase origin/main
```

Resolva conflitos, rode `/portoes` de novo, `git push --force-with-lease`.

---

## BLOCO REUTILIZÁVEL — preparação de uma onda

Roda **uma vez por onda, antes do fan-out**. Landa os arquivos compartilhados
(Compose, `feature-flags.yaml`, `slos.yaml`, matriz de CI, esqueletos de serviço).

```
cd "C:\Users\ronal\Desktop\TG 2"
git fetch origin
git worktree add "..\ff-onda<N>-prep" -b chore/onda<N>-preparacao origin/main
cd "..\ff-onda<N>-prep"
claude
```

Dentro da sessão:

```
Faça a PR de preparação da Onda <N>. Use o agente preparador-de-onda. Só toque
arquivos compartilhados. Depois /revisar e /abrir-pr.
```

Depois:

```
cd "..\ff-onda<N>-prep"
gh pr checks --watch
gh pr merge --squash --delete-branch
cd "C:\Users\ronal\Desktop\TG 2"
git worktree remove "..\ff-onda<N>-prep"
```

---

## FASE 0 — desbloquear e adotar o harness

```
cd "C:\Users\ronal\Desktop\TG 2"
git fetch origin

# 1. Mergear o harness (PR #29) — já rebaseado na main atual
gh pr checks 29 --watch
gh pr merge 29 --squash --delete-branch

# 2. Trazer o harness para o working tree principal
git switch main && git pull

# 3. (opcional, recomendado) Criar as issues das histórias restantes
#    para rastreabilidade. Edite a lista conforme o board.
```

Criação de issues em lote (opcional) — rode no Git Bash:

```bash
while IFS='|' read -r titulo onda; do
  gh issue create --title "$titulo" --label "onda-$onda" \
    --body "Ver docs/BACKLOG.md. Onda $onda." >/dev/null && echo "criada: $titulo"
done <<'EOF'
US-09 — Logs estruturados com identificador de correlação|1
US-10 — Métricas RED e painel de saúde|1
US-11 — Métricas de negócio|1
US-13 — SLOs e alertas por queima de orçamento|1
US-14 — Testes de carga e evidência de escalabilidade|1
US-15 — Unleash integrado aos serviços e ao frontend|2
US-16 — Inventário de flags auditado automaticamente|2
US-17 — Modo de avaliação para a defesa|2
US-18 — Upload assíncrono|3
US-19 — Arquivos no MinIO com acesso temporário|3
US-20 — Documentos persistidos e desduplicados|3
US-21 — Eventos de domínio com Outbox|3
US-22 — Trilha de auditoria|3
US-23 — Serviço de Insights com projeções materializadas|3
US-46 — Camadas anticorrupção nas fronteiras|3
US-47 — Contratos versionados e verificados|3
US-24 — Migração para Tailwind e sistema visual|4
US-25 — Termômetro do limite e painel de ritmo|4
US-26 — Gráfico da corrida contra o limite|4
US-27 — Mês a mês e origem do faturamento|4
US-28 — Cálculo de ritmo, projeção e limite proporcional|4
US-29 — Alertas acionáveis com controle de ruído|4
US-29b — Alertas de contexto do negócio|4
US-29c — Centro de notificações in-app|4
US-30 — Lançamento manual de venda e compra|5
US-31 — Simulador de faturamento|5
US-32 — Metas mensais|5
US-33 — Categorias de lançamento|5
US-34 — Perfil do MEI|5
US-35 — Edição em massa|5
US-36 — Exportação em CSV e XLSX|5
US-37 — Comparativo entre anos|5
US-38 — Filtros e busca na movimentação|5
US-38b — Edição em linha na movimentação|5
US-39 — Conversas persistidas com memória de curto prazo|6
US-40 — Montagem de contexto com orçamento de tokens|6
US-41 — Busca híbrida e segmentação semântica|6
US-42 — Saber quando não sabe|6
US-43 — Memória de longo prazo revisável|6
US-44 — Resposta com fonte verificável|6
US-45 — Cobrança por consumo real de tokens|6
US-48 — Glossário da linguagem ubíqua|6
US-48b — Mapa de contexto documentado|6
US-49 — Retenção e expurgo de documentos|7
US-50 — Exclusão a pedido do titular|7
US-51 — Criptografia e mascaramento|7
US-52 — Limite de taxa e proteção do gateway|7
EOF
```

---

## FASE 1 — Onda 1 · Observabilidade (restante)

Confira no board o que o PR #28 já cobriu. Rode o **ciclo de uma história** para
cada pendente, **uma por vez** (compartilham o bootstrap OTel e o
`docker-compose.observability.yml`):

| Ordem | História | Escopo | Depende de |
| --- | --- | --- | --- |
| 1 | US-09 logs estruturados + correlation-id | `observabilidade` | — |
| 2 | US-10 métricas RED + painel | `observabilidade` | US-09 |
| 3 | US-11 12 métricas de negócio | `observabilidade` | US-10 |
| 4 | US-13 SLOs + alertas multi-janela | `observabilidade` | US-10, US-11 |
| 5 | US-14 k6 + ponto de saturação | `observabilidade` | US-13 |

US-13 já está em andamento no branch `feat/onda1-us13-slos` — termine esse pelo
ciclo (passos 2 e 3) em vez de recriar o worktree.

**Fim da onda:**

```
git fetch origin && git switch main && git pull
git tag v0.3.0 && git push origin v0.3.0
```

---

## FASE 2 — Onda 2 · Feature flags

Quase serial. Sem PR de preparação.

| Ordem | História | Escopo | Paralelo |
| --- | --- | --- | --- |
| 1 | US-15 Unleash + SDK backend e frontend | `flags` | **não** — transversal, 5 serviços + frontend + Compose |
| 2 | US-16 auditoria de inventário | `flags` | pode começar quando US-15 estiver no PR |
| 3 | US-17 modo de avaliação (`perfil-modo-avaliacao`) | `flags` | depois de US-15 |

**Fim da onda:**

```
git fetch origin && git switch main && git pull
git tag v0.4.0 && git push origin v0.4.0
```

---

## FASE 3 — Onda 3 · Assíncrono, persistência, eventos

Primeiro a **preparação da onda** (`chore/onda3-preparacao`): `redis`, `worker`,
`minio`, `mongodb` no Compose; esqueleto do serviço `insights` + matriz de CI;
scaffolding de contrato para US-47.

Depois o fan-out com **2 terminais**:

| Terminal | Ordem | Histórias | Escopo |
| --- | --- | --- | --- |
| **A** (dono de `documents`) | 1→2→3→4 | US-19 → US-20 → US-18 → US-21 | `documents`, `worker` |
| **B** (paralelo) | 1→2→3 | US-46 → US-47 → US-22 | `agent`/`limits` contratos, auditoria |

Depois que A termina US-21: **US-23** (serviço `insights`, um terminal, sozinho).

Ordem de merge: US-19, US-20, US-46, US-47, US-18, US-22, US-21, US-23.

**Fim da onda:**

```
git fetch origin && git switch main && git pull
git tag v0.5.0 && git push origin v0.5.0
```

---

## FASE 4 — Onda 4 · Dashboard e motor de ritmo

Preparação (`chore/onda4-preparacao`): `tailwind.config.js` com tokens,
esqueleto do serviço `notifications` + matriz de CI, flag `dashboard-v2` e
`alertas-ritmo-vendas` revalidadas.

| Ordem | Terminal | Histórias | Escopo | Nota |
| --- | --- | --- | --- | --- |
| 1 | — | **US-24** Tailwind | `frontend`/`dashboard` | sozinho, merge antes do resto |
| 2 | A ‖ B | US-28 (ritmo, `dominio/ritmo.py`) ‖ US-27 (mês a mês) | `limits` ‖ `frontend` | US-27 não depende de ritmo |
| 3 | A ‖ B | US-25 (termômetro) ‖ US-26 (corrida) | `frontend` | ambos precisam de US-28 |
| 4 | A ‖ B ‖ C | US-29 ‖ US-29b ‖ US-29c | `notifications`/`frontend` | precisam de US-28 |

> US-28 aplica o limite proporcional, que depende de **US-34 (Perfil do MEI,
> Onda 5)**. Opção: entregar US-28 só com o motor de ritmo atrás de
> `alertas-ritmo-vendas` e o proporcional atrás de `limite-proporcional`
> desligado; ligar o proporcional depois de US-34. Ou puxar US-34 para cá.

**Fim da onda:**

```
git fetch origin && git switch main && git pull
git tag v0.6.0 && git push origin v0.6.0
```

---

## FASE 5 — Onda 5 · Controles de gestão

A onda mais paralelizável — até **3–4 terminais**. Superfície compartilhada: o
componente da tabela de movimentação e o código de exportação.

| Ordem | Histórias | Nota |
| --- | --- | --- |
| 1 | **US-34** Perfil do MEI | prereq de US-28 (proporcional) e do DAS; entregue cedo |
| 2 (paralelo) | US-30, US-31, US-32, US-33 | lançamento manual, simulador, metas, categorias |
| 3 (paralelo) | US-35, US-36, US-37, US-38, US-38b | edição em massa, export, comparativo, filtros, edição em linha |

Quem terminar primeiro na rodada 2/3 mergeia; os outros `git rebase origin/main`.

**Fim da onda:**

```
git fetch origin && git switch main && git pull
git tag v0.7.0 && git push origin v0.7.0
```

---

## FASE 6 — Onda 6 · Contexto do agente

Preparação (`chore/onda6-preparacao`): **define o contrato dos módulos internos
do `agent-orchestrator`** — interface do recuperador, do montador de contexto, do
extrator de memória — com a implementação atual por trás. Sem isso, serializa.

| Ordem | Terminal | Histórias | Escopo |
| --- | --- | --- | --- |
| 1 | — | **US-39** conversas + memória curta | `contexto` |
| 2 | A ‖ B ‖ C ‖ D | US-40 (orçamento) ‖ US-41 (busca híbrida) ‖ US-42 (limiar) ‖ US-45 (cobrança) | 40/41/42 = `contexto`/`rag` (mesmo serviço, cuidado no montador); 45 = `billing` (paralelo de verdade) |
| 3 | A ‖ B | US-43 (memória longa) ‖ US-44 (fontes verificáveis) | `contexto` |
| paralelo o tempo todo | E | US-48, US-48b (glossário, mapa de contexto) | `docs` — só documentação |

Como cada técnica tem sua flag (`rag-busca-hibrida`, `rag-limiar-similaridade`,
`contexto-memoria-longa`, `contexto-orcamento-tokens`), rode o conjunto de
referência de 30 perguntas com e sem cada uma — é o que sustenta a tabela do
artigo.

**Fim da onda:**

```
git fetch origin && git switch main && git pull
git tag v0.8.0 && git push origin v0.8.0
```

---

## FASE 7 — Onda 7 · Privacidade e fechamento

Até **4 terminais** — histórias quase independentes.

| Terminal | História | Escopo |
| --- | --- | --- |
| A | US-49 retenção e expurgo | `documents`/`worker` |
| B | US-50 exclusão a pedido do titular | transversal (endpoint + consumidores) |
| C | US-51 criptografia e mascaramento | `infra`/`observabilidade` |
| D | US-52 limite de taxa no gateway | `gateway` |

**Fim da onda e entrega:**

```
git fetch origin && git switch main && git pull
git tag v1.0.0 && git push origin v1.0.0
git tag tg2-final && git push origin tg2-final
```

---

## Higiene contínua (rode a cada semana)

```
# flags vencidas — com Actions desativado (ADR-0020) isto não roda mais
# sozinho às segundas; rode à mão de vez em quando:
python tools/flags/auditar.py --inventario docs/feature-flags.yaml --modo vencidas

# métricas DORA do processo — pausadas desde 12/09/2026 (ADR-0020); `gh
# workflow run dora.yml` não dispara com Actions desligado.

# worktrees órfãos
git worktree prune && git worktree list
```

## Se algo travar

- **CI vermelha por dependência nova** (como o `anyio` 4.15): é uma PR
  `fix(build):` própria, pequena, mergeada primeiro — depois `git rebase
  origin/main` nos worktrees abertos.
- **Conflito em arquivo compartilhado:** não era para acontecer no fan-out. A
  mudança deveria ter entrado na PR de preparação da onda. Reverta a linha, mova
  para a preparação.
- **Branch passou de 72 h:** a história é grande demais. Quebre em duas, feche a
  atual com o que já está pronto atrás da flag.
