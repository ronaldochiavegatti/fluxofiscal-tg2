# ADR-0002 — Trunk-based development com Conventional Commits e SemVer

- **Data:** 2026-08-22
- **Estado:** Aceita

## Contexto

O projeto tem um único desenvolvedor e um fluxo de entrega contínua planejado.
Precisamos de um modelo de ramificação que sustente integração frequente sem
cerimônia, e de um padrão de mensagem de commit que sirva simultaneamente para
gerar changelog automático e para provar, na defesa do TG, a rastreabilidade
entre história de usuário, commit e entrega.

O GitFlow clássico (`develop`, `release/*`, `hotfix/*`) resolve um problema que
este projeto não tem: coordenar várias equipes em torno de datas de release
espaçadas. Aqui ele só adicionaria ramos de longa duração e conflitos de merge.

## Decisão

**Trunk-based development.** A `main` é a única linha de longa duração e está
sempre implantável. Todo trabalho acontece em ramos curtos, com vida máxima de
72 horas, integrados por Pull Request com squash merge.

Nomenclatura de ramos: `<tipo>/<numero-issue>-<resumo-em-kebab>`, por exemplo
`feat/42-gauge-limite-anual`.

**Conventional Commits** para as mensagens, com escopo obrigatório quando a
mudança é de um serviço específico:

```
feat(dashboard): adiciona gauge radial do limite anual

Substitui a barra de progresso linear por um gauge que mostra
simultaneamente percentual consumido, valor restante e a data
projetada de estouro.

Refs #42
```

Tipos aceitos: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`,
`build`, `ci`, `chore`, `revert`.

**Versionamento semântico** derivado dos commits: `feat` incrementa a minor,
`fix` a patch, `!` ou `BREAKING CHANGE` a major. Enquanto a plataforma estiver
em `0.x`, quebras de contrato incrementam a minor.

Tags acadêmicas paralelas marcam os marcos do TG: `tg2-qualificacao`,
`tg2-entrega-parcial`, `tg2-final`.

## Consequências

**A favor**

- Ramos curtos praticamente eliminam conflito de merge e mantêm o lead time
  baixo — uma das quatro métricas DORA que o projeto se propõe a medir.
- O `CHANGELOG.md` passa a ser gerado a partir do histórico, sem manutenção
  manual.
- `Refs #<issue>` conecta cada commit à história de usuário correspondente, o
  que torna o board do GitHub Projects uma evidência direta do processo ágil
  descrito na metodologia do artigo.

**Contra**

- Integrar na `main` várias vezes por dia exige que mudanças incompletas fiquem
  escondidas atrás de feature flags. É exatamente por isso que o ADR-0008 existe.
- Squash merge achata o histórico do ramo. Aceito: o valor está no histórico da
  `main`, e o detalhe fica preservado na conversa do PR.

## Alternativas descartadas

**GitFlow.** Cerimônia desproporcional para um autor só; ramos `develop` e
`release` de longa duração atrasariam a integração sem nenhum ganho.

**Commits em texto livre.** Impediria changelog automático e versionamento
derivado, e enfraqueceria a evidência de processo na defesa.

## Referências

- Fowler, M. *Patterns for Managing Source Code Branches*, 2020.
- Forsgren, N.; Humble, J.; Kim, G. *Accelerate*, 2018, cap. 4.
- Especificação Conventional Commits 1.0.0.
