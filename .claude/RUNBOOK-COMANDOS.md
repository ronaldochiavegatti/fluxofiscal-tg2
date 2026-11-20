# RUNBOOK — comandos literais, história por história

Cada bloco é para **copiar e colar direto no terminal** (funciona em PowerShell e
Git Bash — um comando por linha, sem `&&`). Fluxo de cada história:

1. cole o bloco **Abrir** → cria o worktree e entra nele
2. roda `claude` → cole o prompt indicado → `/revisar` → `/abrir-pr US-NN` → `Ctrl+D`
3. cole o bloco **Fechar** → acompanha a CI, mergeia, limpa
4. se houver terminais paralelos abertos, cada um roda o bloco **Sincronizar**

Regra dura: **`gh pr merge` só com a CI verde.** O bloco Fechar já espera com
`gh pr checks --watch`.

O prompt para colar no `claude`, sempre o mesmo (troque o número):

```
Implemente a US-NN seguindo CLAUDE.md e .claude/PLAYBOOK.md. Use o agente implementador-historia. Fique no serviço da história. Escreva um teste para cada cenário Gherkin do docs/BACKLOG.md. Rode /portoes. PARE antes de abrir o PR.
```

Depois `/revisar`, resolver os bloqueadores, `/abrir-pr US-NN`.

Bloco **Sincronizar** (nos outros worktrees abertos, depois de cada merge):

```
git fetch origin
git rebase origin/main
```

Resolver conflitos → rodar `/portoes` no `claude` → `git push --force-with-lease`.

---

# FASE 0 — desbloquear e adotar o harness

```
cd "C:\Users\ronal\Desktop\TG 2"
git fetch origin
gh pr checks 29 --watch
gh pr merge 29 --squash --delete-branch
git switch main
git pull
```

---

# FASE 1 — Onda 1 · Observabilidade (1 terminal, serial)

## US-13 · SLOs e alertas por queima de orçamento — JÁ EM ANDAMENTO

O branch `feat/onda1-us13-slos` já existe. Continue nele:

```
cd "C:\Users\ronal\Desktop\TG 2"
git switch feat/onda1-us13-slos
claude
```

No `claude`: termine a US-13, `/portoes`, `/revisar`, `/abrir-pr US-13`. Depois:

```
gh pr checks --watch
gh pr merge --squash --delete-branch
git switch main
git pull
```

> Se US-09 / US-10 / US-11 ainda não estiverem no board como concluídas, rode-as
> ANTES de US-13, cada uma pelo padrão Abrir/Fechar abaixo, trocando o número e o
> resumo do branch (`us09-logs-estruturados`, `us10-metricas-red`,
> `us11-metricas-de-negocio`).

## US-14 · Testes de carga e ponto de saturação (k6)

**Abrir**
```
cd "C:\Users\ronal\Desktop\TG 2"
git fetch origin
git worktree add "..\ff-us14" -b test/onda1-us14-testes-de-carga origin/main
cd "..\ff-us14"
claude
```
Prompt: `Implemente a US-14 ...` (padrão acima) · `/revisar` · `/abrir-pr US-14`

**Fechar**
```
cd "C:\Users\ronal\Desktop\ff-us14"
gh pr checks --watch
gh pr merge --squash --delete-branch
cd "C:\Users\ronal\Desktop\TG 2"
git worktree remove "..\ff-us14"
git switch main
git pull
```

## Fim da Onda 1

```
git fetch origin
git switch main
git pull
git tag v0.3.0
git push origin v0.3.0
```

---

# FASE 2 — Onda 2 · Feature flags (1 terminal, ~serial)

## US-15 · Unleash + SDK backend e frontend  (transversal — sozinho)

**Abrir**
```
cd "C:\Users\ronal\Desktop\TG 2"
git fetch origin
git worktree add "..\ff-us15" -b feat/onda2-us15-unleash-sdk origin/main
cd "..\ff-us15"
claude
```
Prompt: `Implemente a US-15 ...` · `/revisar` · `/abrir-pr US-15`

**Fechar**
```
cd "C:\Users\ronal\Desktop\ff-us15"
gh pr checks --watch
gh pr merge --squash --delete-branch
cd "C:\Users\ronal\Desktop\TG 2"
git worktree remove "..\ff-us15"
git switch main
git pull
```

## US-16 · Auditoria de inventário de flags

**Abrir**
```
cd "C:\Users\ronal\Desktop\TG 2"
git fetch origin
git worktree add "..\ff-us16" -b ci/onda2-us16-auditoria-flags origin/main
cd "..\ff-us16"
claude
```
Prompt: `Implemente a US-16 ...` · `/revisar` · `/abrir-pr US-16`

**Fechar**
```
cd "C:\Users\ronal\Desktop\ff-us16"
gh pr checks --watch
gh pr merge --squash --delete-branch
cd "C:\Users\ronal\Desktop\TG 2"
git worktree remove "..\ff-us16"
git switch main
git pull
```

## US-17 · Modo de avaliação para a defesa

**Abrir**
```
cd "C:\Users\ronal\Desktop\TG 2"
git fetch origin
git worktree add "..\ff-us17" -b feat/onda2-us17-modo-de-avaliacao origin/main
cd "..\ff-us17"
claude
```
Prompt: `Implemente a US-17 ...` · `/revisar` · `/abrir-pr US-17`

**Fechar**
```
cd "C:\Users\ronal\Desktop\ff-us17"
gh pr checks --watch
gh pr merge --squash --delete-branch
cd "C:\Users\ronal\Desktop\TG 2"
git worktree remove "..\ff-us17"
git switch main
git pull
```

## Fim da Onda 2

```
git fetch origin
git switch main
git pull
git tag v0.4.0
git push origin v0.4.0
```

---

# FASE 3 — Onda 3 · Assíncrono, persistência, eventos (2 terminais)

## Passo 0 — preparação da onda (1 terminal, sozinho)

**Abrir**
```
cd "C:\Users\ronal\Desktop\TG 2"
git fetch origin
git worktree add "..\ff-onda3-prep" -b chore/onda3-preparacao origin/main
cd "..\ff-onda3-prep"
claude
```
Prompt no `claude`:
```
Faça a PR de preparação da Onda 3. Use o agente preparador-de-onda. Adicione redis, worker (Celery), minio e mongodb ao docker-compose.yml; crie o esqueleto do serviço insights com /health e entrada na matriz do ci.yml; revalide as flags ocr-assincrono, storage-minio, documentos-persistidos, eventos-outbox no docs/feature-flags.yaml; crie o scaffolding do teste de contrato para US-47. Só arquivos compartilhados. Depois /revisar e /abrir-pr.
```

**Fechar**
```
cd "C:\Users\ronal\Desktop\ff-onda3-prep"
gh pr checks --watch
gh pr merge --squash --delete-branch
cd "C:\Users\ronal\Desktop\TG 2"
git worktree remove "..\ff-onda3-prep"
git switch main
git pull
```

## TERMINAL A — dono de `documents` (US-19 → US-20 → US-18 → US-21, em série)

### A1 · US-19 · Arquivos no MinIO
**Abrir**
```
cd "C:\Users\ronal\Desktop\TG 2"
git fetch origin
git worktree add "..\ff-us19" -b feat/onda3-us19-minio origin/main
cd "..\ff-us19"
claude
```
Prompt: `Implemente a US-19 ...` · `/revisar` · `/abrir-pr US-19`

**Fechar**
```
cd "C:\Users\ronal\Desktop\ff-us19"
gh pr checks --watch
gh pr merge --squash --delete-branch
cd "C:\Users\ronal\Desktop\TG 2"
git worktree remove "..\ff-us19"
git switch main
git pull
```

### A2 · US-20 · Documentos persistidos e desduplicados
**Abrir**
```
cd "C:\Users\ronal\Desktop\TG 2"
git fetch origin
git worktree add "..\ff-us20" -b feat/onda3-us20-documentos-persistidos origin/main
cd "..\ff-us20"
claude
```
Prompt: `Implemente a US-20 ...` · `/revisar` · `/abrir-pr US-20`

**Fechar**
```
cd "C:\Users\ronal\Desktop\ff-us20"
gh pr checks --watch
gh pr merge --squash --delete-branch
cd "C:\Users\ronal\Desktop\TG 2"
git worktree remove "..\ff-us20"
git switch main
git pull
```

### A3 · US-18 · Upload assíncrono (Celery)
**Abrir**
```
cd "C:\Users\ronal\Desktop\TG 2"
git fetch origin
git worktree add "..\ff-us18" -b feat/onda3-us18-upload-assincrono origin/main
cd "..\ff-us18"
claude
```
Prompt: `Implemente a US-18 ...` · `/revisar` · `/abrir-pr US-18`

**Fechar**
```
cd "C:\Users\ronal\Desktop\ff-us18"
gh pr checks --watch
gh pr merge --squash --delete-branch
cd "C:\Users\ronal\Desktop\TG 2"
git worktree remove "..\ff-us18"
git switch main
git pull
```

### A4 · US-21 · Eventos de domínio com Outbox
**Abrir**
```
cd "C:\Users\ronal\Desktop\TG 2"
git fetch origin
git worktree add "..\ff-us21" -b feat/onda3-us21-eventos-outbox origin/main
cd "..\ff-us21"
claude
```
Prompt: `Implemente a US-21 ...` · `/revisar` · `/abrir-pr US-21`

**Fechar**
```
cd "C:\Users\ronal\Desktop\ff-us21"
gh pr checks --watch
gh pr merge --squash --delete-branch
cd "C:\Users\ronal\Desktop\TG 2"
git worktree remove "..\ff-us21"
git switch main
git pull
```

## TERMINAL B — em paralelo com A (US-46 → US-47 → US-22)

### B1 · US-46 · Camadas anticorrupção nas fronteiras
**Abrir**
```
cd "C:\Users\ronal\Desktop\TG 2"
git fetch origin
git worktree add "..\ff-us46" -b refactor/onda3-us46-anticorrupcao origin/main
cd "..\ff-us46"
claude
```
Prompt: `Implemente a US-46 ...` · `/revisar` · `/abrir-pr US-46`

**Fechar**
```
cd "C:\Users\ronal\Desktop\ff-us46"
gh pr checks --watch
gh pr merge --squash --delete-branch
cd "C:\Users\ronal\Desktop\TG 2"
git worktree remove "..\ff-us46"
git switch main
git pull
```

### B2 · US-47 · Contratos versionados e verificados na CI
**Abrir**
```
cd "C:\Users\ronal\Desktop\TG 2"
git fetch origin
git worktree add "..\ff-us47" -b ci/onda3-us47-contratos-verificados origin/main
cd "..\ff-us47"
claude
```
Prompt: `Implemente a US-47 ...` · `/revisar` · `/abrir-pr US-47`

**Fechar**
```
cd "C:\Users\ronal\Desktop\ff-us47"
gh pr checks --watch
gh pr merge --squash --delete-branch
cd "C:\Users\ronal\Desktop\TG 2"
git worktree remove "..\ff-us47"
git switch main
git pull
```

### B3 · US-22 · Trilha de auditoria
**Abrir**
```
cd "C:\Users\ronal\Desktop\TG 2"
git fetch origin
git worktree add "..\ff-us22" -b feat/onda3-us22-trilha-de-auditoria origin/main
cd "..\ff-us22"
claude
```
Prompt: `Implemente a US-22 ...` · `/revisar` · `/abrir-pr US-22`

**Fechar**
```
cd "C:\Users\ronal\Desktop\ff-us22"
gh pr checks --watch
gh pr merge --squash --delete-branch
cd "C:\Users\ronal\Desktop\TG 2"
git worktree remove "..\ff-us22"
git switch main
git pull
```

## Passo final da Onda 3 — US-23 (1 terminal, depois que A e B terminaram)

### US-23 · Serviço de Insights com projeções materializadas
**Abrir**
```
cd "C:\Users\ronal\Desktop\TG 2"
git fetch origin
git worktree add "..\ff-us23" -b feat/onda3-us23-insights-cqrs origin/main
cd "..\ff-us23"
claude
```
Prompt: `Implemente a US-23 ...` · `/revisar` · `/abrir-pr US-23`

**Fechar**
```
cd "C:\Users\ronal\Desktop\ff-us23"
gh pr checks --watch
gh pr merge --squash --delete-branch
cd "C:\Users\ronal\Desktop\TG 2"
git worktree remove "..\ff-us23"
git switch main
git pull
```

## Fim da Onda 3

```
git fetch origin
git switch main
git pull
git tag v0.5.0
git push origin v0.5.0
```

---

# FASE 4 — Onda 4 · Dashboard e motor de ritmo

## Passo 0 — preparação
**Abrir**
```
cd "C:\Users\ronal\Desktop\TG 2"
git fetch origin
git worktree add "..\ff-onda4-prep" -b chore/onda4-preparacao origin/main
cd "..\ff-onda4-prep"
claude
```
Prompt:
```
Faça a PR de preparação da Onda 4. Use o agente preparador-de-onda. Crie o app/services/frontend/tailwind.config.js com os tokens de estado (ok/atenção/risco/estourado), crie o esqueleto do serviço notifications com /health e entrada na matriz do ci.yml, revalide as flags dashboard-v2 e alertas-ritmo-vendas. Só arquivos compartilhados. Depois /revisar e /abrir-pr.
```
**Fechar**
```
cd "C:\Users\ronal\Desktop\ff-onda4-prep"
gh pr checks --watch
gh pr merge --squash --delete-branch
cd "C:\Users\ronal\Desktop\TG 2"
git worktree remove "..\ff-onda4-prep"
git switch main
git pull
```

## Passo 1 — US-24 (sozinho, merge antes do resto)

### US-24 · Migração para Tailwind
**Abrir**
```
cd "C:\Users\ronal\Desktop\TG 2"
git fetch origin
git worktree add "..\ff-us24" -b refactor/onda4-us24-tailwind origin/main
cd "..\ff-us24"
claude
```
Prompt: `Implemente a US-24 ...` · `/revisar` · `/abrir-pr US-24`
**Fechar**
```
cd "C:\Users\ronal\Desktop\ff-us24"
gh pr checks --watch
gh pr merge --squash --delete-branch
cd "C:\Users\ronal\Desktop\TG 2"
git worktree remove "..\ff-us24"
git switch main
git pull
```

## Passo 2 — TERMINAL A: US-28  ‖  TERMINAL B: US-27

### A · US-28 · Cálculo de ritmo, projeção e limite proporcional
```
cd "C:\Users\ronal\Desktop\TG 2"
git fetch origin
git worktree add "..\ff-us28" -b feat/onda4-us28-ritmo-projecao origin/main
cd "..\ff-us28"
claude
```
Prompt: `Implemente a US-28 ...` · `/revisar` · `/abrir-pr US-28`
```
cd "C:\Users\ronal\Desktop\ff-us28"
gh pr checks --watch
gh pr merge --squash --delete-branch
cd "C:\Users\ronal\Desktop\TG 2"
git worktree remove "..\ff-us28"
git switch main
git pull
```

### B · US-27 · Mês a mês e origem do faturamento
```
cd "C:\Users\ronal\Desktop\TG 2"
git fetch origin
git worktree add "..\ff-us27" -b feat/onda4-us27-mes-a-mes origin/main
cd "..\ff-us27"
claude
```
Prompt: `Implemente a US-27 ...` · `/revisar` · `/abrir-pr US-27`
```
cd "C:\Users\ronal\Desktop\ff-us27"
gh pr checks --watch
gh pr merge --squash --delete-branch
cd "C:\Users\ronal\Desktop\TG 2"
git worktree remove "..\ff-us27"
git switch main
git pull
```

## Passo 3 — TERMINAL A: US-25  ‖  TERMINAL B: US-26

### A · US-25 · Termômetro do limite e painel de ritmo
```
cd "C:\Users\ronal\Desktop\TG 2"
git fetch origin
git worktree add "..\ff-us25" -b feat/onda4-us25-termometro origin/main
cd "..\ff-us25"
claude
```
Prompt: `Implemente a US-25 ...` · `/revisar` · `/abrir-pr US-25`
```
cd "C:\Users\ronal\Desktop\ff-us25"
gh pr checks --watch
gh pr merge --squash --delete-branch
cd "C:\Users\ronal\Desktop\TG 2"
git worktree remove "..\ff-us25"
git switch main
git pull
```

### B · US-26 · Gráfico da corrida contra o limite
```
cd "C:\Users\ronal\Desktop\TG 2"
git fetch origin
git worktree add "..\ff-us26" -b feat/onda4-us26-corrida-contra-limite origin/main
cd "..\ff-us26"
claude
```
Prompt: `Implemente a US-26 ...` · `/revisar` · `/abrir-pr US-26`
```
cd "C:\Users\ronal\Desktop\ff-us26"
gh pr checks --watch
gh pr merge --squash --delete-branch
cd "C:\Users\ronal\Desktop\TG 2"
git worktree remove "..\ff-us26"
git switch main
git pull
```

## Passo 4 — A: US-29  ‖  B: US-29b  ‖  C: US-29c

### A · US-29 · Alertas acionáveis com controle de ruído
```
cd "C:\Users\ronal\Desktop\TG 2"
git fetch origin
git worktree add "..\ff-us29" -b feat/onda4-us29-alertas-acionaveis origin/main
cd "..\ff-us29"
claude
```
Prompt: `Implemente a US-29 ...` · `/revisar` · `/abrir-pr US-29`
```
cd "C:\Users\ronal\Desktop\ff-us29"
gh pr checks --watch
gh pr merge --squash --delete-branch
cd "C:\Users\ronal\Desktop\TG 2"
git worktree remove "..\ff-us29"
git switch main
git pull
```

### B · US-29b · Alertas de contexto do negócio
```
cd "C:\Users\ronal\Desktop\TG 2"
git fetch origin
git worktree add "..\ff-us29b" -b feat/onda4-us29b-alertas-contexto origin/main
cd "..\ff-us29b"
claude
```
Prompt: `Implemente a US-29b ...` · `/revisar` · `/abrir-pr US-29b`
```
cd "C:\Users\ronal\Desktop\ff-us29b"
gh pr checks --watch
gh pr merge --squash --delete-branch
cd "C:\Users\ronal\Desktop\TG 2"
git worktree remove "..\ff-us29b"
git switch main
git pull
```

### C · US-29c · Centro de notificações in-app
```
cd "C:\Users\ronal\Desktop\TG 2"
git fetch origin
git worktree add "..\ff-us29c" -b feat/onda4-us29c-centro-notificacoes origin/main
cd "..\ff-us29c"
claude
```
Prompt: `Implemente a US-29c ...` · `/revisar` · `/abrir-pr US-29c`
```
cd "C:\Users\ronal\Desktop\ff-us29c"
gh pr checks --watch
gh pr merge --squash --delete-branch
cd "C:\Users\ronal\Desktop\TG 2"
git worktree remove "..\ff-us29c"
git switch main
git pull
```

## Fim da Onda 4
```
git fetch origin
git switch main
git pull
git tag v0.6.0
git push origin v0.6.0
```

---

# FASE 5 — Onda 5 · Controles de gestão (3–4 terminais)

## Passo 1 — US-34 primeiro (prereq de US-28 e do DAS)

### US-34 · Perfil do MEI
```
cd "C:\Users\ronal\Desktop\TG 2"
git fetch origin
git worktree add "..\ff-us34" -b feat/onda5-us34-perfil-do-mei origin/main
cd "..\ff-us34"
claude
```
Prompt: `Implemente a US-34 ...` · `/revisar` · `/abrir-pr US-34`
```
cd "C:\Users\ronal\Desktop\ff-us34"
gh pr checks --watch
gh pr merge --squash --delete-branch
cd "C:\Users\ronal\Desktop\TG 2"
git worktree remove "..\ff-us34"
git switch main
git pull
```

## Passo 2 — rodada paralela (A/B/C/D): US-30, US-31, US-32, US-33

Mesmo padrão. Branches:
- `feat/onda5-us30-lancamento-manual`
- `feat/onda5-us31-simulador-faturamento`
- `feat/onda5-us32-metas-mensais`
- `feat/onda5-us33-categorias-de-lancamento`

Bloco por história (troque `NN` e o nome do branch):
```
cd "C:\Users\ronal\Desktop\TG 2"
git fetch origin
git worktree add "..\ff-usNN" -b feat/onda5-usNN-<resumo> origin/main
cd "..\ff-usNN"
claude
```
Prompt: `Implemente a US-NN ...` · `/revisar` · `/abrir-pr US-NN`
```
cd "C:\Users\ronal\Desktop\ff-usNN"
gh pr checks --watch
gh pr merge --squash --delete-branch
cd "C:\Users\ronal\Desktop\TG 2"
git worktree remove "..\ff-usNN"
git switch main
git pull
```
Nos outros terminais, depois de cada merge: `git fetch origin` + `git rebase origin/main`.

## Passo 3 — rodada paralela: US-35, US-36, US-37, US-38, US-38b

Branches:
- `feat/onda5-us35-edicao-em-massa`
- `feat/onda5-us36-exportacao-csv-xlsx`
- `feat/onda5-us37-comparativo-entre-anos`
- `feat/onda5-us38-filtros-e-busca`
- `feat/onda5-us38b-edicao-em-linha`

Mesmo bloco do Passo 2.

## Fim da Onda 5
```
git fetch origin
git switch main
git pull
git tag v0.7.0
git push origin v0.7.0
```

---

# FASE 6 — Onda 6 · Contexto do agente (4 terminais)

## Passo 0 — preparação (define o contrato dos módulos internos)
```
cd "C:\Users\ronal\Desktop\TG 2"
git fetch origin
git worktree add "..\ff-onda6-prep" -b chore/onda6-preparacao origin/main
cd "..\ff-onda6-prep"
claude
```
Prompt:
```
Faça a PR de preparação da Onda 6. Use o agente preparador-de-onda. Defina no agent-orchestrator as interfaces (Protocol) dos módulos internos: recuperador, montador de contexto em camadas, extrator de memória — com a implementação atual por trás de cada uma, sem mudar comportamento. Revalide as flags rag-busca-hibrida, rag-limiar-similaridade, contexto-memoria-longa, contexto-orcamento-tokens, contexto-resumo-progressivo, billing-tokens-reais. Depois /revisar e /abrir-pr.
```
```
cd "C:\Users\ronal\Desktop\ff-onda6-prep"
gh pr checks --watch
gh pr merge --squash --delete-branch
cd "C:\Users\ronal\Desktop\TG 2"
git worktree remove "..\ff-onda6-prep"
git switch main
git pull
```

## Passo 1 — US-39 (base, sozinho)
Branch `feat/onda6-us39-conversas-memoria-curta`. Bloco padrão.

## Passo 2 — paralelo: US-40 (A) ‖ US-41 (B) ‖ US-42 (C) ‖ US-45 (D)
Branches:
- `feat/onda6-us40-orcamento-de-tokens`
- `feat/onda6-us41-busca-hibrida`
- `feat/onda6-us42-limiar-de-similaridade`
- `feat/onda6-us45-cobranca-tokens-reais`

> A/B/C mexem no mesmo serviço (`agent-orchestrator`): mantenha cada um na sua
> peça do contrato definido no Passo 0 e faça `git rebase origin/main` a cada
> merge. D (`billing`) é paralelo de verdade.

## Passo 3 — paralelo: US-43 (A) ‖ US-44 (B) ‖ US-48 + US-48b (C, docs)
Branches:
- `feat/onda6-us43-memoria-longa`
- `feat/onda6-us44-fonte-verificavel`
- `docs/onda6-us48-glossario` e `docs/onda6-us48b-mapa-de-contexto`

## Fim da Onda 6
```
git fetch origin
git switch main
git pull
git tag v0.8.0
git push origin v0.8.0
```

---

# FASE 7 — Onda 7 · Privacidade e fechamento (4 terminais)

Rodada paralela A/B/C/D. Branches:
- A: `feat/onda7-us49-retencao-e-expurgo`
- B: `feat/onda7-us50-exclusao-do-titular`
- C: `feat/onda7-us51-criptografia-e-mascaramento`
- D: `feat/onda7-us52-limite-de-taxa-gateway`

Bloco por história (padrão). Depois de cada merge, os outros: `git fetch origin` + `git rebase origin/main`.

## Entrega
```
git fetch origin
git switch main
git pull
git tag v1.0.0
git push origin v1.0.0
git tag tg2-final
git push origin tg2-final
```

---

# Limpeza (a qualquer momento)

```
git worktree prune
git worktree list
git branch --merged main
```
