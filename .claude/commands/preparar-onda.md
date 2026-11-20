---
description: Roda a PR de preparação de uma onda via o agente preparador-de-onda (landa os arquivos compartilhados antes do fan-out)
argument-hint: N (número da onda)
allowed-tools: Bash, Read, Grep, Glob, Task
---

Prepare o terreno da **Onda $1** para o fan-out paralelo.

1. Da raiz, com `main` atualizada, crie o branch/worktree de preparação:

   ```bash
   git worktree add ../ff-onda$1-prep -b chore/onda$1-preparacao origin/main
   ```

2. Invoque o agente `preparador-de-onda` com o alvo "Onda $1". Ele lê
   `docs/PLANO.md`, `.claude/PLAYBOOK.md` e `docs/BACKLOG.md`, e só toca os
   arquivos compartilhados listados no `CLAUDE.md`.
3. Quando ele terminar: `/revisar`, depois `/abrir-pr` (sem `US-XX` — o corpo do
   PR descreve a preparação, não uma história).
4. **Só depois desta PR mergear** as sessões de história podem rodar
   `/nova-historia` para a Onda $1.

Consulte `.claude/PLAYBOOK.md` §5 e §6 para o recorte concreto das Ondas 2 e 3.
