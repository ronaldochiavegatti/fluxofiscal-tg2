---
description: Roda os portões de qualidade locais (mesmos comandos da CI) para os serviços tocados no diff atual
allowed-tools: Bash, Read, Grep, Glob
---

Rode os portões de qualidade para o que mudou neste branch.

1. `git diff --name-only origin/main...HEAD` para descobrir os serviços tocados.
2. Para **cada serviço de backend** tocado (`app/services/<serviço>/`, exceto
   `frontend` e `api-gateway`), de dentro da pasta do serviço:

   ```bash
   ruff check app/ tests/
   ruff format --check app/ tests/
   mypy app/ --ignore-missing-imports
   pytest tests/ --cov=app --cov-report=term-missing --cov-fail-under=80
   ```

   Se o diff toca `app/services/limits/app/dominio/`, exija 95% e rode também
   `mutmut run --paths-to-mutate dominio/`.

3. Se `app/services/frontend/` foi tocado, de dentro dele:

   ```bash
   npx tsc --noEmit
   npm run lint -- --max-warnings=0
   npm run test:cov
   npm run build
   ```

4. **Não** rode `docker compose up` — esse portão é serializado entre worktrees
   e é responsabilidade do operador coordenar.

Reporte um resumo: cada comando, verde ou vermelho, e a primeira falha de cada
serviço se houver.
