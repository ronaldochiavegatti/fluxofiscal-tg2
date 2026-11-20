# Playbook de paralelização

Como rodar várias sessões Claude Code em paralelo sobre o plano de `docs/` sem
que uma atropele a outra e sem baixar a qualidade dos PRs.

---

## 1. O caminho crítico é real — não paralelize entre ondas

As 8 ondas (`docs/PLANO.md` §3) são uma cadeia de dependência dura:
medir → flag → re-arquitetar → construir produto em cima.

- **Ondas 0, 1, 2** são pré-requisito de tudo e majoritariamente seriais.
- **O fan-out real começa na Onda 3.**
- Ondas mais paralelizáveis: **Onda 5** (10 features de frontend quase
  independentes, cada uma com sua flag) e **Onda 7** (4 histórias independentes).

## 2. Fluxo por onda

1. **PR de preparação da onda** (serial, 1 sessão): `/preparar-onda N`.
   Landa de uma vez todos os arquivos compartilhados da onda — Compose, flags em
   `docs/feature-flags.yaml`, `slos.yaml`, matriz de `ci.yml`, esqueletos de
   serviço novo, interfaces de módulo internas. **Merge antes de qualquer fan-out.**
2. **Fan-out** (paralelo): `/nova-historia US-XX` por sessão, uma história por
   worktree. Atribuição por **diretório de serviço + flag**. Nunca dois branches
   vivos editando o núcleo do mesmo serviço.
3. **Ordem de merge = ordem de dependência.** Depois de cada merge, as outras
   sessões rodam `git fetch origin && git rebase origin/main`. Branches pequenos
   → conflito raro.
4. **Portão do Compose serializado.** Testes de unidade e contrato rodam em
   paralelo à vontade; `docker compose up --wait` roda um worktree por vez.

## 3. Regras de fatiamento

- História com > 13 pontos, ou que toca > 1 serviço no núcleo: **quebrada antes**
  de virar branch.
- **`dominio/` tem dono único** ao longo de todo o projeto (US-03 feito, US-28
  depois). É o módulo mais dependido e o de maior risco (mutation-tested,
  precisão numérica 100%).
- **`agent-orchestrator` (Onda 6):** as 7 histórias vivem no mesmo serviço. A PR
  de preparação define o contrato de módulos internos (interface do recuperador,
  interface do montador de contexto) antes do fan-out. Sem isso, serializa.
- Frontend vs. qualquer backend: sem sobreposição além de Compose / `.env.example`
  — sempre paralelizável.

## 4. Preservação de qualidade (idêntica ao fluxo serial)

Cada branch, sem exceção:

1. Portões locais verdes — os mesmos comandos que a CI rodava (ver `CLAUDE.md`).
2. `/revisar` (agente `revisor-pr`) ou skill `/code-review` sobre o diff.
3. PR pelo `.github/PULL_REQUEST_TEMPLATE.md`, com os cenários Gherkin colados,
   o checklist de Definição de Concluído marcado, e o resultado dos portões
   locais citado (número de testes, cobertura) — é a evidência que substitui
   o log de CI.

**GitHub Actions está desativado desde 12/09/2026**
([ADR-0020](../docs/adr/0020-ci-local-sem-github-actions.md), cobrança da
conta): não há mais "CI verde" pra esperar no GitHub. Isso não muda a régua —
o GitHub Free privado **já não impunha** o status check "CI aprovada"
(`docs/versionamento.md` §3) antes disso, então a regra sempre foi disciplina,
não trava de servidor: **nunca abrir/mergear PR sem os portões locais
verdes.**

---

## 5. Aplicação: Onda 2 — Feature flags (13 pts)

Quase toda serial. Ela existe para destravar a Onda 3.

| História | Serviço(s) | Paralelismo |
| --- | --- | --- |
| US-15 Unleash + SDK backend e frontend | 5 serviços + frontend + Compose | **Nenhum** — 1 branch, transversal |
| US-16 Auditoria de inventário de flags | `tools/flags/`, `higiene-flags.yml` | Pode ir junto com o fim de US-15 |
| US-17 Modo de avaliação (`perfil-modo-avaliacao`) | `frontend`, `insights` | Depois de US-15 |

**Veredito: 1–2 sessões.** Trate como serial.

---

## 6. Aplicação: Onda 3 — Assíncrono, persistência, eventos (70 pts)

### PR de preparação — `/preparar-onda 3`

- Adiciona ao `docker-compose.yml`: `redis`, `worker` (Celery), `minio`,
  `mongodb`, com healthchecks.
- Confirma as flags `ocr-assincrono`, `storage-minio`, `documentos-persistidos`,
  `eventos-outbox` em `docs/feature-flags.yaml` (já declaradas — só revalidar
  datas).
- Cria o esqueleto do serviço `insights` + entrada na matriz de `ci.yml`.
- Scaffolding do teste de contrato para US-47.

### Fan-out — `documents` é o gargalo, então a sequência interna é obrigatória

| Passo | História | Serviço(s) | Em paralelo com |
| --- | --- | --- | --- |
| 1 | US-19 MinIO | `documents`, `worker` | US-46 / US-47 (sessão B) |
| 2 | US-20 Mongo + dedup | `documents`, `frontend` | US-46 / US-47 (sessão B) |
| 3 | US-18 Upload assíncrono (Celery) | `documents`, `worker` | US-22 (sessão B) |
| 4 | US-21 Eventos Outbox | `limits`, `billing`, `documents` | US-22 (sessão B) |
| 5 | US-23 Insights CQRS | serviço novo `insights` | — |

- **Sessão A** é a dona de `documents`: US-19 → US-20 → US-18 → US-21 em série
  (mesmo serviço, não dá para paralelizar dentro dele).
- **Sessão B** trabalha no que não toca `documents`: US-46 (camadas
  anticorrupção) + US-47 (contratos na CI) durante os passos 1–2; depois US-22
  (trilha de auditoria, consumidor de eventos) durante os passos 3–4.
- Passo 5 (US-23) é serviço novo, uma sessão, depois que US-21 mergeou.

**Paralelismo real: 2 sessões.** O limite é `documents` ser serial, não falta de
histórias.
