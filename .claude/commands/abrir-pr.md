---
description: Preenche o template de PR com os cenários Gherkin da história e abre o Pull Request
argument-hint: US-XX
allowed-tools: Bash, Read, Grep, Glob
---

Abra o PR da história **$1**. Pré-condições (confirme antes): portões verdes,
`/revisar` sem bloqueadores em aberto, `git rebase origin/main` feito.

1. Leia `.github/PULL_REQUEST_TEMPLATE.md` e a história `$1` em `docs/BACKLOG.md`.
2. Monte o corpo do PR a partir do template:
   - **O que muda:** uma frase.
   - **História relacionada:** `Closes #<nº>`.
   - **Tipo:** marque o tipo do commit.
   - **Critérios de aceite atendidos:** cole cada cenário Gherkin da história e
     marque `[x]` os que têm teste passando.
   - **Evidência:** saída resumida do `pytest` / `vitest`; caminho de screenshot
     se for frontend.
   - **Checklist de Definition of Done:** marque só o que é verdade.
   - **Feature flag:** nome, estratégia de rollout, data de remoção — ou `n/a`.
   - **Risco e plano de reversão:** desligar a flag / reverter o commit.
   - Termine com: `🤖 Generated with [Claude Code](https://claude.com/claude-code)`
3. Título no padrão Conventional Commits (`<tipo>(<escopo>): <resumo>`) — ele
   vira a mensagem do commit de squash na `main`.
4. `git push -u origin <branch>` e depois:

   ```bash
   gh pr create --title "<título>" --body-file <arquivo-temporário-com-o-corpo>
   ```

5. Reporte a URL do PR e lembre o operador: GitHub Actions está desativado
   (ADR-0020) — **não fazer merge sem os portões locais (`/portoes`) verdes**,
   já que não há mais check de CI para conferir isso automaticamente.
