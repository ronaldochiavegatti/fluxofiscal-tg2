# ADR-0013 — Pirâmide de testes e portões de qualidade

- **Data:** 2026-08-22
- **Estado:** Aceita

## Contexto

O projeto tem **zero teste automatizado**. O arquivo `TESTING.md` descreve um
roteiro manual com comandos `curl`, o que funciona como documentação mas não
protege contra regressão: nada impede que uma mudança no Limits quebre o cálculo
do limite anual sem que ninguém perceba antes da apresentação.

O risco é concreto e assimétrico. A regra de que apenas vendas contam para o
teto de R$ 81.000,00 está codificada em três lugares diferentes — na consulta do
`get_summary`, no filtro do frontend em `DashboardPage.tsx` e nas instruções do
prompt do agente. Se um deles divergir, o sistema passa a dar orientação fiscal
errada, que é a pior falha possível neste domínio.

O artigo afirma que houve "testes cobrindo os principais fluxos" e cita testes
unitários, de integração e de usabilidade na metodologia. Isso precisa deixar de
ser afirmação.

## Decisão

Adotar a pirâmide de testes com cinco níveis, cada um com um alvo distinto:

| Nível | Ferramenta | O que cobre | Onde roda |
| --- | --- | --- | --- |
| Unitário | pytest, Vitest | Regra de domínio pura, sem entrada e saída | Todo PR |
| Integração | pytest + testcontainers | Serviço com seu banco, fila e armazenamento reais | Todo PR |
| Contrato | Schemathesis | Toda rota contra o próprio OpenAPI | Todo PR |
| Ponta a ponta | Playwright | Jornadas do usuário no navegador | Todo PR na main |
| Carga | k6 | SLOs sob carga | Noturno |

**Núcleo de domínio isolado.** A regra fiscal do MEI sai dos endpoints e vai
para um módulo `dominio/` sem dependência de framework ou banco. Cálculo de
limite, classificação de nível de alerta, limite proporcional por mês de
abertura, ritmo de vendas e projeção viram funções puras — testáveis em
milissegundos, com cobertura exigida de 95%.

**Testcontainers em vez de simulação.** Testar o Limits contra um SQLite ou um
dublê de banco esconde justamente as diferenças que importam: `func.extract` do
PostgreSQL, `Numeric(10,2)`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. O teste
sobe um PostgreSQL 16 real em contêiner.

**Teste de mutação no núcleo fiscal.** `mutmut` roda sobre `dominio/` no
pipeline noturno. Cobertura diz que a linha foi executada; mutação diz se o
teste realmente notaria se ela estivesse errada. Alvo: 80% de mutantes mortos no
módulo fiscal. É o argumento mais forte disponível para sustentar, no artigo,
que a regra de negócio está de fato verificada.

**Conjunto de referência para OCR e RAG.** Os 12 documentos sintéticos já usados
no experimento do artigo viram um conjunto versionado com gabarito, expandido
para 40 casos incluindo fotos tortas, com ruído e de baixo contraste. O conjunto
do RAG cresce de 5 para 30 perguntas parafraseadas. Ambos rodam no pipeline
noturno e produzem as tabelas do artigo automaticamente.

**Portões de qualidade** exigidos para integrar na `main`:

1. `ruff check` e `ruff format --check` sem violação
2. `mypy` sem erro nos módulos de domínio
3. Cobertura mínima: 95% em `dominio/`, 80% por serviço, 70% no frontend
4. Nenhuma vulnerabilidade crítica ou alta com correção disponível (Trivy)
5. Nenhum segredo detectado (gitleaks)
6. Todos os testes de contrato passando
7. O `docker compose` sobe e os healthchecks respondem

A cobertura mínima começa em zero e sobe conforme cada suíte é escrita. Portão
que trava o trabalho sem proteger nada é abandonado; portão que sobe junto com a
cobertura é respeitado.

## Consequências

**A favor**

- A regra fiscal passa a ter verificação automática, e a afirmação do artigo
  sobre testes passa a ser verdadeira e demonstrável.
- Teste de contrato pega quebra de API entre serviços antes da execução.
- O conjunto de referência transforma "a extração acertou 100%" em medição
  repetível a cada noite, com histórico de série temporal.
- Refatorar deixa de ser aposta, o que é pré-requisito para extrair o núcleo de
  domínio e introduzir os eventos.

**Contra**

- Escrever a suíte inicial é um esforço concentrado e sem funcionalidade nova.
- Testcontainers deixa a CI mais lenta. Mitigado com cache de camadas e execução
  em paralelo por serviço.
- Playwright é frágil por natureza. Mitigado usando seletores por papel de
  acessibilidade e evitando espera por tempo fixo.

## Alternativas descartadas

**Só testes unitários.** Baratos e rápidos, mas cegos justamente para o tipo de
falha que uma arquitetura de microsserviços produz: incompatibilidade de
contrato e erro de integração.

**Só testes ponta a ponta.** Cobertura ampla com diagnóstico péssimo — um teste
vermelho não diz qual dos seis serviços quebrou.

**Manter o roteiro manual do `TESTING.md`.** Não protege contra regressão e não
escala. O arquivo continua útil como documentação de exploração manual.

## Referências

- Fowler, M. *The Practical Test Pyramid*, 2018.
- Documentação do Schemathesis sobre testes baseados em propriedades a partir do
  OpenAPI.
- Documentação do testcontainers-python.
