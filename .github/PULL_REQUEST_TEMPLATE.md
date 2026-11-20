## O que muda

<!-- Uma frase objetiva. O título do PR segue Conventional Commits: feat(escopo): descrição -->

## História relacionada

Closes #<numero-da-issue>  <!-- ou: Refs #<numero> -->

## Tipo

- [ ] `feat` — nova funcionalidade
- [ ] `fix` — correção de defeito
- [ ] `refactor` — mudança interna sem alterar comportamento
- [ ] `perf` — melhoria de desempenho
- [ ] `test` — apenas testes
- [ ] `docs` — apenas documentação
- [ ] `ci` / `build` / `chore` — infraestrutura do projeto

## Critérios de aceite atendidos

<!-- Cole os cenários Gherkin da história e marque os que passam -->
- [ ]

## Evidência

<!-- Print do dashboard, saída de teste, painel do Grafana, trecho de log, resultado do k6 -->

## Checklist de Definition of Done

- [ ] Testes automatizados cobrindo o comportamento novo (unitário e/ou integração)
- [ ] `docker compose up -d --build` sobe o ambiente sem erro
- [ ] Pipeline de CI verde (lint, tipos, testes, cobertura, scan de segredos, scan de imagem)
- [ ] Endpoints novos instrumentados (métrica RED + span OTel + log estruturado)
- [ ] Mudança arriscada protegida por feature flag, com dono e data de expiração registrados
- [ ] Documentação atualizada (README, `docs/`, ADR quando houver decisão arquitetural)
- [ ] Sem segredo, chave ou dado pessoal real no diff
- [ ] Impacto no artigo do TG anotado em `docs/IMPACTO-ARTIGO.md` quando aplicável

## Feature flag

- Nome: `<flag>` — ou `n/a`
- Estratégia de rollout:
- Data de remoção prevista:

## Risco e plano de reversão

<!-- Como voltar atrás: desligar a flag? reverter o commit? restaurar volume? -->
