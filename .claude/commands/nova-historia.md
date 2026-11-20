---
description: Cria um git worktree + branch para uma história e a implementa via o agente implementador-historia
argument-hint: US-XX [nº-issue]
---

Objetivo: começar a história **$1** num worktree isolado.

Passos:

1. Leia a história `$1` em `docs/BACKLOG.md`. Derive o tipo do commit (`feat`,
   `fix`, `refactor`…) e um resumo curto em kebab-case a partir do título.
2. Descubra o número da issue no GitHub para `$1` (se `$2` foi passado, use-o;
   senão `gh issue list --search "$1"` e confirme com o operador).
3. Da raiz do repo (`main` limpa e atualizada — `git fetch origin`), crie o
   worktree irmão:

   ```bash
   git worktree add ../ff-$1 -b <tipo>/<nº>-<resumo-kebab> origin/main
   ```

4. Confirme os hooks: dentro do worktree, `git config --get core.hooksPath` deve
   dar `.githooks`. Se não, `git config core.hooksPath .githooks`.
5. Diga ao operador para abrir uma nova sessão Claude Code **dentro de
   `../ff-$1`** e rodar lá o agente `implementador-historia` com o alvo `$1`.
   (Este worktree é uma pasta separada; a sessão nova nasce com o contexto
   limpo e herda o `CLAUDE.md`.)

Se preferir implementar nesta mesma sessão, invoque agora o agente
`implementador-historia` passando `$1` e o caminho do worktree.

Não abra PR — isso é `/abrir-pr` depois de `/portoes` e `/revisar`.
