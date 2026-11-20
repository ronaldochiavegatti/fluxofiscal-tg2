# CLAUDE.md — FluxoFiscal

Assistente fiscal para MEI. Monorepo privado. Plano de engenharia em
`docs/PLANO.md`; 56 histórias em `docs/BACKLOG.md`; arquitetura alvo em
`docs/arquitetura/README.md`; decisões em `docs/adr/`.

Este arquivo é o padrão herdado por toda sessão e todo subagente. As decisões
por trás das regras estão nos ADRs; o detalhe do dia a dia está em
`CONTRIBUTING.md` e `docs/versionamento.md` — leia-os quando precisar do porquê.

---

## Layout

| Caminho | O quê |
| --- | --- |
| `app/services/<serviço>/app/` e `/tests/` | Serviço FastAPI (Python 3.12) |
| `app/services/frontend/src/` | Frontend React + Vite + TypeScript |
| `app/services/api-gateway/` | NGINX (roteamento, correlation-id, rate limit) |
| `app/services/limits/app/dominio/` | **Regra fiscal do MEI — e nenhum outro lugar** |
| `app/docker-compose.yml` | Pilha local completa |
| `docs/feature-flags.yaml` | Inventário de flags — fonte da verdade, auditado na CI |

Serviços de backend: `auth`, `billing`, `limits`, `documents`,
`agent-orchestrator`. Não há pacote Python compartilhado; `observability.py` é
copiado em cada serviço (mudança no padrão = aplicar em todos).

---

## Portões locais — rode antes de qualquer PR

Com GitHub Actions desativado (ADR-0020), estes comandos **são** o portão —
não uma repetição do que a CI faria. Rode e cite o resultado no commit.

Backend, de `app/services/<serviço>/`:

```bash
ruff check app/ tests/
ruff format --check app/ tests/
mypy app/ --ignore-missing-imports
pytest tests/ --cov=app --cov-report=term-missing --cov-fail-under=80
```

Cobertura mínima: **95% em `dominio/`**, 80% por serviço. Ao mexer em regra
fiscal, rode também `mutmut run --paths-to-mutate dominio/` (alvo 80% de
mutantes mortos) antes de considerar pronto.

Frontend, de `app/services/frontend/`:

```bash
npx tsc --noEmit
npm run lint -- --max-warnings=0
npm run test:cov
npm run build
```

O portão `docker compose up -d --build --wait` (de `app/`) roda **serializado**
entre worktrees — os `container_name` e as portas são fixos. Veja
"Trabalho paralelo" abaixo.

---

## Branch e commit

- Nome do branch: `<tipo>/<nº-issue>-<resumo-em-kebab-case>`
  (`feat/42-gauge-limite-anual`).
- **Uma história por branch. Vida máxima 72 h.** Passou disso, a história é
  grande demais — quebre a história, não estenda o branch.
- Mensagens em Conventional Commits, **escopo obrigatório** para mudança de um
  serviço. Escopos: `auth`, `billing`, `limits`, `documents`, `agent`,
  `insights`, `notifications`, `worker`, `gateway`, `frontend`, `dashboard`,
  `rag`, `contexto`, `flags`, `observabilidade`, `infra`, `adr`.
- O corpo do commit explica **por que**, não o que o diff já mostra. Rodapé:
  `Refs #<n>`.
- Trabalho incompleto entra na `main` **só atrás de feature flag** (ADR-0002 /
  ADR-0008). Nunca commits `wip`.
- Rodapé de atribuição em todo commit de uma sessão Claude Code:

  ```
  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  Claude-Session: <URL da sessão atual, quando a sessão fornecer uma>
  ```

- Descrição de PR termina com:
  `🤖 Generated with [Claude Code](https://claude.com/claude-code)`

---

## Definição de Concluído (de `docs/BACKLOG.md`)

> **GitHub Actions está desativado desde 12/09/2026** (ADR-0020) — cobrança da
> conta, sem prazo pra voltar. Os portões abaixo rodam **localmente** antes do
> PR, e o commit (ou a descrição do PR) registra o resultado real (quantos
> testes, cobertura obtida) no lugar do log de CI. `git push`/PR no GitHub
> continua normal; só o workflow automático não dispara.

- Critérios de aceite (Gherkin da história) passando em teste automatizado.
- Portões locais verdes: lint, tipos, cobertura, contrato, segredos, imagem —
  resultado documentado no commit (ver ADR-0020; era "CI verde" com Actions
  ligado).
- Rota nova instrumentada: métrica RED + span OTel nomeado + log estruturado com
  `trace_id` (ver `CONTRIBUTING.md`, "Ao criar uma rota nova").
- Mudança arriscada atrás de flag declarada em `docs/feature-flags.yaml`, com
  dono e `remover_ate`.
- Documentação atualizada; ADR quando houver decisão arquitetural; impacto
  anotado em `docs/IMPACTO-ARTIGO.md` quando aplicável.
- Sem segredo nem dado pessoal real no diff.

---

## Nunca

- Push direto na `main` (fluxo é PR com squash merge).
- Log de e-mail sem hash, CNPJ sem máscara, ou texto de OCR / conteúdo de chat.
- Caminho concreto como rótulo de métrica — sempre o padrão da rota
  (`/summary/{email}`, nunca `/summary/maria@…`).
- `except Exception: pass` sem registrar nada.
- Duplicar regra fiscal fora de `app/services/limits/app/dominio/`. Se precisou
  duplicar no frontend, falta um endpoint.
- Adicionar dependência estrutural (banco, fila, protocolo entre serviços) sem
  ADR.
- Versionar `.env` ou chave de API.

---

## Trabalho paralelo (várias sessões ao mesmo tempo)

Você provavelmente é **uma de várias sessões Claude Code**, cada uma num
`git worktree` próprio, cada uma numa história.

1. Trabalhe **só** dentro do(s) serviço(s) e arquivos da sua história designada.
2. **Não edite arquivos compartilhados** a menos que seja explicitamente a sua
   tarefa (uma "PR de preparação de onda"):
   - `app/docker-compose*.yml`
   - `docs/feature-flags.yaml`
   - `ruff.toml`, `app/requirements-dev.txt`
   - `.github/workflows/*`
   - `docs/observabilidade/slos.yaml`
   - `app/services/frontend/tailwind.config.js`
   - `app/services/frontend/src/pages/DashboardPage.tsx`
3. Antes de abrir o PR: `git fetch origin && git rebase origin/main`, rode os
   portões, rode `/revisar` (ou o skill `/code-review`).
4. Para rodar `docker compose up` sem colidir com outro worktree, use um
   `docker-compose.override.yml` local (fora do commit) com
   `COMPOSE_PROJECT_NAME` e offset de portas — ou combine com as outras sessões
   de rodar um de cada vez.
5. Os hooks locais valem para todos os worktrees (`.git` é compartilhado).
   Confirme uma vez: `git config --get core.hooksPath` deve devolver `.githooks`.

O playbook de quando paralelizar e quando serializar está em
`.claude/PLAYBOOK.md`. A sequência de comandos, onda a onda, da Onda 1 até a
entrega do TG II, está em `.claude/RUNBOOK.md`.
