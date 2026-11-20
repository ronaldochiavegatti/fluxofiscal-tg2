# Versionamento

> Decisão: [ADR-0001](adr/0001-monorepo-privado-no-github.md) e
> [ADR-0002](adr/0002-trunk-based-e-conventional-commits.md).

O histórico do Git tem dois papéis neste projeto. O primeiro é técnico: permitir
reverter, comparar e localizar a origem de um defeito. O segundo é acadêmico: o
artigo afirma que o desenvolvimento seguiu SCRUM, com sprints e entregas
incrementais — e o histórico é a evidência empírica dessa afirmação. Um
histórico com três commits chamados "update" não sustenta o argumento.

---

## 1. Ramos

`main` é a única linha de longa duração e está sempre implantável.

```
main ──●──●──●────────●────●──●──▶
        \        /      \      /
         ●──●──●         ●──●──●
      feat/42-gauge   fix/47-limite-proporcional
      (menos de 72h)  (algumas horas)
```

**Nomenclatura:** `<tipo>/<numero-issue>-<resumo-em-kebab-case>`

```
feat/42-gauge-limite-anual
fix/47-limite-proporcional-mes-abertura
refactor/51-extrai-dominio-fiscal
docs/55-adr-observabilidade
ci/58-cache-de-camadas-docker
```

**Vida máxima de 72 horas.** Um ramo que passa disso é sinal de história grande
demais, e a resposta é quebrar a história, não estender o ramo.

**Como trabalho incompleto entra na `main`.** Atrás de feature flag
([ADR-0008](adr/0008-unleash-para-feature-flags.md)). É o que torna a integração
frequente compatível com entregas grandes.

---

## 2. Mensagens de commit

Formato [Conventional Commits](https://www.conventionalcommits.org/pt-br/):

```
<tipo>(<escopo>): <resumo no imperativo, minúscula, sem ponto final>

<corpo: por que a mudança existe, não o que o diff já mostra>

<rodapé: Refs #42, BREAKING CHANGE, Co-Authored-By>
```

### Tipos

| Tipo | Quando | Efeito na versão |
| --- | --- | --- |
| `feat` | Funcionalidade nova visível ao usuário | minor |
| `fix` | Correção de defeito | patch |
| `perf` | Melhoria de desempenho | patch |
| `refactor` | Mudança interna sem alterar comportamento | nenhum |
| `test` | Só testes | nenhum |
| `docs` | Só documentação | nenhum |
| `build` | Dependências, Dockerfile, Compose | nenhum |
| `ci` | Workflows e automação | nenhum |
| `chore` | Manutenção sem categoria | nenhum |
| `revert` | Desfaz um commit anterior | conforme o revertido |

### Escopos

`auth`, `billing`, `limits`, `documents`, `agent`, `insights`, `notifications`,
`worker`, `gateway`, `frontend`, `dashboard`, `rag`, `contexto`, `flags`,
`observabilidade`, `infra`, `adr`.

### Exemplo do que se espera

```
feat(insights): calcula indice de ritmo e projecao de estouro

O percentual acumulado nao distingue estar em 40% do limite em marco de
estar em 40% em outubro. O indice de ritmo compara a taxa diaria realizada
com a taxa de referencia do teto e responde, a qualquer altura do ano, se
o MEI esta indo rapido demais.

Nao projeta com menos de 30 dias de dados ou menos de 3 transacoes: fora
disso a projecao produz alarme falso, e alarme falso derruba a confianca
no sistema inteiro.

Refs #42
```

O corpo explica **por que**. O `git log -p` já mostra o que mudou; o que ele não
mostra é a razão, e é essa a parte que se perde.

### O que não fazer

```
update                      # atualizou o quê?
correcoes                   # quais?
feat: varias melhorias      # não é uma mudança, são várias
wip                         # não integra na main
```

---

## 3. Pull Requests

Todo PR usa o [template](../.github/PULL_REQUEST_TEMPLATE.md), com título no
mesmo padrão Conventional Commits — porque o squash merge transforma o título do
PR na mensagem do commit na `main`.

### Proteção da `main`

Regras de proteção de ramo e rulesets **exigem GitHub Pro em repositório
privado**. Como o repositório é privado no plano gratuito
([ADR-0001](adr/0001-monorepo-privado-no-github.md)), parte das regras é
imposta pelo servidor e parte é compensada no cliente.

| Regra | Onde é imposta | Estado |
| --- | --- | --- |
| Só squash merge (histórico linear) | Servidor | ativo |
| Ramo apagado após o merge | Servidor | ativo |
| Título do commit = título do PR | Servidor | ativo |
| Alertas de dependência vulnerável | Servidor | ativo |
| Correção automática de dependências | Servidor | ativo |
| Push direto na `main` bloqueado | Cliente (`pre-push`) | ativo |
| Mensagem em Conventional Commits (commit) | Cliente (`commit-msg`) | ativo |
| Título do PR em Conventional Commits | CI (`ci.yml`, job "Histórico e segredos") | **desativado — ver abaixo** |
| Verificação `CI aprovada` obrigatória | — | **indisponível** |
| Conversas resolvidas antes do merge | — | **indisponível** |
| Force push bloqueado | — | **indisponível** |

**GitHub Actions está desativado desde 12/09/2026**
([ADR-0020](adr/0020-ci-local-sem-github-actions.md), cobrança da conta) — o
que inclui a verificação de título de PR acima, que só existia na CI e não
tem hook cliente equivalente. Título de PR fora do padrão Conventional
Commits não é mais pego automaticamente; confira à mão antes do squash
merge, já que o título vira a mensagem do commit na `main`.

**Os hooks não são equivalentes à proteção do servidor.** Eles podem ser
contornados com `--no-verify`, não valem para merges feitos pela interface web
e dependem de cada clone rodar `git config core.hooksPath .githooks`. São rede
de segurança contra o engano honesto, não controle de acesso.

Ativação em um clone novo:

```bash
git config core.hooksPath .githooks
```

Três formas de obter as regras que faltam, se elas passarem a importar:

1. **Tornar o repositório público** — rulesets são gratuitos em repositório
   público. Exige a limpeza de segredos já prevista no ADR-0001.
2. **GitHub Pro** — cerca de US$ 4 por mês.
3. **Conviver com a lacuna** — que é a escolha atual, registrada aqui para não
   ser confundida com esquecimento.

---

## 4. Versões e tags

**Versão semântica** derivada dos commits desde a última tag.

Enquanto a plataforma estiver em `0.x`, quebra de contrato incrementa a minor —
convenção do SemVer para software antes da primeira versão estável.

```
v0.1.0  linha de base: protótipo importado
v0.2.0  esteira de CI/CD e suíte de testes
v0.3.0  observabilidade e SLOs
v0.4.0  feature flags
v0.5.0  arquitetura assíncrona
v0.6.0  dashboard v2 e motor de ritmo
v0.7.0  controles de gestão
v0.8.0  contexto do agente
v1.0.0  entrega do TG II
```

**Tags acadêmicas** marcam os pontos citados no artigo:

```
tg2-qualificacao     estado na qualificação
tg2-entrega-parcial  versão da entrega parcial
tg2-final            versão defendida
```

Uma tag acadêmica torna reproduzível qualquer afirmação do artigo: quem quiser
verificar um número basta fazer checkout da tag e rodar o pipeline de
benchmarks.

---

## 5. Rastreabilidade

A cadeia que liga um requisito a uma linha de código:

```
Épico (EP05)
  └── História (US-25, issue #42)
        └── Ramo  feat/42-gauge-limite-anual
              └── Commits com "Refs #42"
                    └── PR "feat(dashboard): adiciona gauge do limite anual"
                          └── Squash merge na main, fechando #42
                                └── Tag v0.6.0
                                      └── Imagens no GHCR marcadas por SHA
```

Isso é o que permite responder, na defesa, "onde está implementado o requisito
tal" com um link em vez de uma busca.

**GitHub Projects** organiza o board com as colunas do fluxo (Backlog, Pronto
para desenvolver, Em andamento, Em revisão, Concluído) e os campos Épico,
Estimativa, Onda e Feature flag. As capturas do board e do gráfico de burndown
são material direto para a seção de metodologia.

---

## 6. Rotina

```bash
# começar uma história
git switch main && git pull
git switch -c feat/42-gauge-limite-anual

# durante o trabalho, commits pequenos e frequentes
git add -p
git commit -m "feat(dashboard): adiciona gauge radial do limite

Refs #42"

# publicar e abrir o PR
git push -u origin feat/42-gauge-limite-anual
gh pr create --fill

# depois do merge
git switch main && git pull && git branch -d feat/42-gauge-limite-anual
```

---

## 7. Higiene

**Nunca versionar:** `.env`, chave de API, `node_modules/`, `__pycache__/`,
dados de volume, artefato de build.

**Se um segredo entrar no histórico:** revogar a credencial primeiro — reescrever
o histórico não desfaz o vazamento. Depois limpar com `git filter-repo` e forçar
a atualização do remoto.

A varredura do gitleaks roda em todo PR, mas ela é a segunda linha de defesa. A
primeira é o `.gitignore`, e ele foi o primeiro commit deste repositório
justamente por isso.
