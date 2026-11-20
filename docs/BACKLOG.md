# Backlog do produto

Formato INVEST, critérios de aceite em Gherkin. Cada história é uma issue no
GitHub ([template](../.github/ISSUE_TEMPLATE/01-user-story.yml)) e vira um ramo
com o padrão `<tipo>/<numero>-<resumo>`.

**Total no escopo:** 57 histórias em 10 épicos, 344 pontos. Mais 3 histórias
(21 pontos) ficam registradas fora de escopo no EP11.

---

## Personas

| Persona | Quem é | O que a incomoda hoje |
| --- | --- | --- |
| **Márcia** | MEI prestadora de serviços, 42 anos. Manicure com salão próprio. Não tem contador. | Descobre que está perto do teto quando já é tarde. Não sabe quanto pode faturar por mês. |
| **Douglas** | MEI comerciante, 29 anos. Loja de acessórios, alto volume de notas. | Enviar nota a nota é lento. Não consegue lançar uma venda sem documento. |
| **Ronaldo** | Desenvolvedor e mantenedor da plataforma. | Não tem teste, não tem métrica, não consegue reverter nada. |
| **Operador** | Quem opera a plataforma em execução. | Não sabe se está de pé nem por que está lento. |
| **Banca** | Orientador e avaliadores do TG. | Precisa de evidência verificável, não de afirmação. |

## Definição de pronto para desenvolver

- Critérios de aceite escritos, sem ambiguidade
- Dependências técnicas identificadas
- Forma de medir o resultado definida
- Cabe em uma onda; se não couber, foi quebrada

## Definição de concluído

> GitHub Actions desativado desde 12/09/2026 (ADR-0020, cobrança da conta) —
> os portões abaixo rodam localmente e o resultado vai documentado no commit.

- Critérios de aceite passando em teste automatizado
- Portões locais verdes: lint, tipos, cobertura, contrato, segredos, imagem —
  resultado registrado no commit (ADR-0020)
- Rota nova instrumentada com métrica, rastro e log estruturado
- Mudança arriscada atrás de flag declarada em `feature-flags.yaml`
- Documentação atualizada; ADR quando houver decisão arquitetural
- Sem segredo nem dado pessoal real no diff

---

# EP01 — Fundação de engenharia

**Objetivo:** sair de zero teste, zero automação e zero histórico. Nada nas
ondas seguintes é seguro sem isto. **47 pontos.**

### US-01 — Repositório versionado com histórico rastreável
**Como** Ronaldo, **quero** o projeto versionado no GitHub com padrão de commits
e proteção de ramo, **para** poder reverter mudanças e comprovar o processo
incremental na defesa.

```gherkin
Cenário: Nenhum segredo entra no histórico
  Dado que o arquivo .env contém uma chave real da API do Gemini
  Quando o repositório é inicializado e o primeiro push é feito
  Então o .env não está no histórico
  E existe um .env.example sem valores preenchidos
  E a varredura do gitleaks não encontra segredo

Cenário: Push direto na main é recusado
  Dado que a proteção de ramo está configurada
  Quando alguém tenta empurrar direto para a main
  Então o push é recusado
  E a mensagem indica que é necessário abrir um Pull Request

Cenário: Título de PR fora do padrão reprova
  Dado um PR intitulado "ajustes"
  Quando a CI executa
  Então o portão de histórico falha
  E o erro mostra um exemplo de título válido
```

**Medida:** 100% dos commits na `main` seguem Conventional Commits.
**Pontos:** 3 · **Flag:** n/a

---

### US-02 — Chave de API exposta revogada e rotacionada
**Como** Ronaldo, **quero** a chave do Gemini que estava em texto puro revogada e
substituída, **para** eliminar o risco de uso indevido por terceiros.

```gherkin
Cenário: A chave antiga deixa de funcionar
  Dado que a chave anterior estava versionada em um .zip distribuído
  Quando ela é revogada no console do Google AI Studio
  Então uma requisição usando a chave antiga retorna 401
  E a aplicação funciona normalmente com a chave nova

Cenário: A chave nova nunca toca o repositório
  Dado que a chave nova está apenas no .env local e nos GitHub Secrets
  Quando o repositório é varrido inteiro
  Então nenhuma ocorrência da chave é encontrada
```

**Medida:** zero segredo no histórico após varredura completa.
**Pontos:** 2 · **Flag:** n/a · **Prioridade:** faça isto primeiro

---

### US-03 — Núcleo de domínio fiscal isolado e testável
**Como** Ronaldo, **quero** a regra fiscal do MEI extraída dos endpoints para um
módulo puro, **para** que ela seja verificável em milissegundos e não esteja
duplicada em três lugares.

> A regra "só venda conta para o teto" hoje existe na consulta do `get_summary`,
> no filtro do `DashboardPage.tsx` e nas instruções do prompt do agente. Três
> cópias divergem — é questão de tempo.

```gherkin
Cenário: Só venda conta para o teto
  Dado um MEI com R$ 50.000,00 em vendas e R$ 30.000,00 em compras
  Quando o resumo anual é calculado
  Então o faturamento para o limite é R$ 50.000,00
  E as despesas são R$ 30.000,00
  E o saldo líquido é R$ 20.000,00

Cenário: Nível de alerta segue o realizado
  Dado o limite anual de R$ 81.000,00
  Quando o faturamento é <valor>
  Então o nível de alerta é <nivel>

  Exemplos:
    | valor     | nivel     |
    | 64799.99  | ok        |
    | 64800.00  | warning   |
    | 80999.99  | warning   |
    | 81000.00  | warning   |   # o teto exato ainda está dentro
    | 81000.01  | exceeded  |

Cenário: O módulo não conhece framework nem banco
  Quando o módulo dominio/ é importado
  Então ele não importa fastapi, sqlalchemy ou httpx
```

**Medida:** cobertura de 95% em `dominio/`; 80% de mutantes mortos.
**Pontos:** 8 · **Flag:** n/a

---

### US-04 — Suíte de testes dos serviços de backend
**Como** Ronaldo, **quero** testes unitários e de integração em cada serviço,
**para** que uma mudança não quebre silenciosamente o cálculo do limite.

```gherkin
Cenário: Integração roda contra PostgreSQL real
  Dado que os testes usam testcontainers
  Quando a suíte do Limits executa
  Então um PostgreSQL 16 sobe em contêiner
  E as consultas com func.extract são exercitadas de verdade
  E o contêiner é destruído ao final

Cenário: Contrato validado contra o próprio OpenAPI
  Dado que cada serviço expõe seu esquema OpenAPI
  Quando o Schemathesis executa contra ele
  Então nenhuma rota devolve 500 para entrada válida
  E nenhuma resposta viola o esquema declarado

Cenário: Nenhum teste chama a API do Gemini
  Quando a suíte completa executa sem GEMINI_API_KEY
  Então todos os testes passam
  E os caminhos de contingência são exercitados
```

**Medida:** 80% por serviço; suíte completa abaixo de 5 minutos.
**Pontos:** 13 · **Flag:** n/a

---

### US-05 — Qualidade e testes do frontend
**Como** Ronaldo, **quero** verificação de tipos, lint e testes de componente no
frontend, **para** que a camada que o usuário vê tenha o mesmo rigor do backend.

```gherkin
Cenário: Tipo inconsistente reprova a CI
  Dado um componente que lê summary.total_revenue como string
  Quando tsc --noEmit executa
  Então a compilação falha apontando o arquivo e a linha

Cenário: Formatação em pt-BR verificada
  Dado um valor de 47304.5
  Quando o componente de moeda renderiza
  Então o texto exibido é "R$ 47.304,50"
```

**Medida:** 70% de cobertura no frontend; zero erro de tipo.
**Pontos:** 5 · **Flag:** n/a

---

### US-06 — Esteira de integração contínua
**Como** Ronaldo, **quero** um pipeline que valide todo PR, **para** que só entre
na `main` código que constrói, passa nos testes e sobe de verdade.

```gherkin
Cenário: O ambiente sobe e responde
  Quando o pipeline executa docker compose up --wait
  Então os cinco healthchecks respondem status ok
  E um fluxo de transação a resumo anual funciona ponta a ponta
  E o ambiente é derrubado com os volumes ao final

Cenário: Falha entrega diagnóstico, não silêncio
  Dado que a integração falhou
  Quando o pipeline termina
  Então os últimos 200 registros de log de cada serviço estão publicados
```

**Medida:** pipeline abaixo de 10 minutos; taxa de falso vermelho abaixo de 5%.
**Pontos:** 8 · **Flag:** n/a

---

### US-07 — Entrega contínua até o registro de imagens
**Como** Ronaldo, **quero** que cada commit na `main` publique imagens marcadas,
**para** que a demonstração use exatamente o código que foi testado.

```gherkin
Cenário: Imagem rastreável até o commit
  Quando um commit é integrado na main
  Então sete imagens são publicadas no GHCR
  E cada uma está marcada com o SHA completo do commit
  E cada uma carrega SBOM e atestado de proveniência

Cenário: Demonstração sem reconstrução
  Dado o docker-compose.release.yml
  Quando executo pull e up
  Então o ambiente sobe a partir das imagens do registro
  E nenhuma imagem é construída localmente
```

**Medida:** 100% dos commits da `main` com imagem publicada.
**Pontos:** 5 · **Flag:** n/a

---

### US-08 — Métricas DORA do próprio processo
**Como** Banca, **quero** ver as quatro métricas DORA medidas ao longo do
projeto, **para** avaliar a maturidade do processo de engenharia com dado.

```gherkin
Cenário: Coleta semanal automática
  Quando o workflow dora.yml executa
  Então frequência de implantação, lead time, taxa de falha e tempo de
    restauração são calculados sobre uma janela de 28 dias
  E o resultado é publicado no resumo da execução
  E o histórico fica retido por 365 dias
```

**Medida:** série contínua desde a primeira semana até a defesa.
**Pontos:** 3 · **Flag:** n/a

---

# EP02 — Observabilidade e SLOs

**Objetivo:** tornar o sistema explicável. **36 pontos.**

### US-09 — Logs estruturados com identificador de correlação
**Como** Operador, **quero** seguir uma requisição pelos serviços por um
identificador único, **para** diagnosticar sem adivinhar.

```gherkin
Cenário: O identificador atravessa os serviços
  Dado um upload que passa por gateway, documents e limits
  Quando os logs são consultados pelo identificador de correlação
  Então há registros dos três serviços com o mesmo valor
  E o identificador também volta no cabeçalho X-Correlation-Id da resposta

Cenário: Dado pessoal não vaza para o log
  Quando um documento com CNPJ e e-mail é processado
  Então nenhum log contém e-mail em texto puro
  E o CNPJ aparece mascarado
  E o texto integral do OCR não é registrado

Cenário: O despejo de SQL some
  Dado que o auth roda com echo=True
  Quando esta história é concluída
  Então o SQL deixa de ser despejado no stdout
```

**Medida:** 100% dos registros em JSON com `trace_id`.
**Pontos:** 5 · **Flag:** n/a

---

### US-10 — Métricas RED e painel de saúde
**Como** Operador, **quero** taxa, erro e duração por serviço e por rota, **para**
saber o que está degradado antes de o usuário reclamar.

```gherkin
Cenário: Cardinalidade sob controle
  Dado que /summary/{email} recebe requisições de 500 usuários distintos
  Quando as métricas são consultadas
  Então existe uma única série com route="/summary/{email}"
  E nenhum e-mail aparece como valor de rótulo
```

**Medida:** todos os serviços emitindo RED; painel provisionado como código.
**Pontos:** 5 · **Flag:** n/a

---

### US-11 — Métricas de negócio
**Como** Ronaldo, **quero** medir extração, RAG, consumo de LLM e faixas de uso
do limite, **para** ter dado real de produto — e não só de infraestrutura.

```gherkin
Cenário: Método de extração é observável
  Dado que 100 documentos foram processados
  Quando a métrica documentos_processados_total é consultada
  Então há contagem separada por método gemini e regex
  E a razão de uso do caminho de contingência é calculável

Cenário: Custo de LLM é rastreável
  Quando uma extração via Gemini termina
  Então llm_tokens_total registra entrada e saída
  E llm_custo_estimado_reais_total é incrementado
```

**Medida:** 12 métricas de negócio ativas; painel de custo funcionando.
**Pontos:** 8 · **Flag:** n/a

---

### US-12 — Rastreamento distribuído
**Como** Operador, **quero** ver a linha do tempo completa de uma requisição
lenta, **para** identificar o trecho responsável em vez de suspeitar.

```gherkin
Cenário: O rastro atravessa a fila
  Dado um upload que enfileira processamento assíncrono
  Quando o rastro é aberto no Tempo
  Então ele inclui os spans da requisição e os da tarefa Celery
  E o vínculo entre eles está preservado

Cenário: Do painel ao log em dois cliques
  Dado um pico de latência no painel do Grafana
  Quando clico no ponto e depois no rastro
  Então chego aos registros de log daquela requisição específica
```

**Medida:** 100% das rotas rastreadas; caminho painel-rastro-log funcionando.
**Pontos:** 8 · **Flag:** n/a

---

### US-13 — SLOs e alertas por queima de orçamento
**Como** Operador, **quero** objetivos formais com alerta em janelas múltiplas,
**para** ser avisado de degradação real sem ser acordado por ruído.

```gherkin
Cenário: Queima rápida dispara
  Dado o SLO de disponibilidade do gateway em 99,5%
  Quando a taxa de erro consome 2% do orçamento mensal em uma hora
  E a janela curta de 5 minutos também está queimando
  Então o alerta de severidade página dispara
  E ele aponta para o runbook correspondente

Cenário: Ruído de curta duração não dispara
  Dado um pico de erro de 30 segundos
  Quando as janelas são avaliadas
  Então nenhum alerta dispara
```

**Medida:** todo alerta de severidade página com runbook; zero alerta sem ação.
**Pontos:** 5 · **Flag:** n/a

---

### US-14 — Testes de carga e evidência de escalabilidade
**Como** Banca, **quero** números medidos de comportamento sob carga, **para**
avaliar a afirmação de escalabilidade com evidência.

```gherkin
Cenário: Perfil realista de MEI
  Dado o cenário de 50 usuários simultâneos por 10 minutos
  Quando o k6 executa
  Então o p95 de /limits/summary fica abaixo de 300 ms
  E a taxa de erro fica abaixo de 1%

Cenário: Ponto de saturação identificado
  Dado o cenário de estresse com carga crescente
  Quando o k6 executa
  Então o relatório indica em qual carga o SLO passa a ser violado
```

**Medida:** relatório de carga com ponto de saturação, atualizado a cada noite.
**Pontos:** 5 · **Flag:** n/a

---

# EP03 — Feature flags e entrega segura

**Objetivo:** poder integrar trabalho incompleto e reverter em um clique.
**13 pontos.**

### US-15 — Unleash integrado aos serviços e ao frontend
**Como** Ronaldo, **quero** avaliar flags no backend e no frontend, **para**
liberar mudança de forma gradual e reversível.

```gherkin
Cenário: Indisponibilidade do Unleash não derruba nada
  Dado que o serviço de flags está fora do ar
  Quando a aplicação avalia qualquer flag
  Então o valor padrão declarado no código é usado
  E o padrão é sempre o comportamento antigo e conhecido
  E um WARNING é registrado, não um ERROR

Cenário: Liberação percentual é estável
  Dado a flag dashboard-v2 em 30% dos usuários
  Quando o mesmo usuário recarrega a página cinco vezes
  Então ele recebe sempre a mesma variante
```

**Medida:** avaliação de flag abaixo de 5 ms no percentil 99.
**Pontos:** 5 · **Flag:** n/a

---

### US-16 — Inventário de flags auditado automaticamente
**Como** Ronaldo, **quero** que flag sem declaração ou vencida seja detectada
pela CI, **para** que o inventário não vire débito permanente.

```gherkin
Cenário: Flag não declarada reprova o PR
  Dado um PR que usa is_enabled("recurso-novo")
  E que "recurso-novo" não está em docs/feature-flags.yaml
  Então a CI falha indicando a flag ausente

Cenário: Flag vencida gera issue
  Dado uma flag com remover_ate anterior a hoje
  Quando a auditoria semanal executa
  Então uma issue de débito técnico é aberta automaticamente
```

**Medida:** zero flag vencida em aberto por mais de 14 dias.
**Pontos:** 3 · **Flag:** n/a

---

### US-17 — Modo de avaliação para a defesa
**Como** Banca, **quero** ver cada cenário de alerta sem esperar acumular
transações reais, **para** avaliar o comportamento do sistema em minutos.

> **Adiada (2026-09-08).** Depende de infraestrutura de ondas posteriores: os
> "6 níveis de alerta" são do motor de ritmo (US-28/US-29, Onda 4) e os
> cenários sintéticos vivem no serviço Insights (US-23, Onda 3) — nenhum dos
> dois existe ainda. O domínio atual só tem 3 níveis (`ok`/`warning`/
> `exceeded`). A flag `perfil-modo-avaliacao` já está declarada e o SDK do
> Unleash já integrado (US-15); a história entra junto com o motor de ritmo.
> A Onda 2 fecha com US-15 e US-16.

```gherkin
Cenário: Cenário carregado sob demanda
  Dado que a flag perfil-modo-avaliacao está ativa para meu usuário
  Quando escolho o cenário "risco de estouro em novembro"
  Então transações sintéticas coerentes são criadas
  E o dashboard passa a exibir o alerta correspondente
  E os dados são identificados como sintéticos na interface
```

**Medida:** os 6 níveis de alerta demonstráveis em menos de 2 minutos.
**Pontos:** 5 · **Flag:** `perfil-modo-avaliacao`

---

# EP04 — Arquitetura assíncrona e persistência

**Objetivo:** tirar o trabalho pesado do caminho da requisição e parar de perder
dado. **60 pontos.**

### US-18 — Upload assíncrono
**Como** Douglas, **quero** que o envio de uma nota responda na hora, **para** não
ficar 5 segundos olhando uma tela travada a cada documento.

```gherkin
Cenário: Resposta imediata
  Quando envio uma nota fiscal
  Então recebo 202 Accepted em menos de 500 ms
  E a resposta traz o identificador do documento e a URL de acompanhamento
  E a tela mostra o progresso do processamento

Cenário: Falha transitória é reprocessada
  Dado que a API do Gemini devolve 429
  Quando a tarefa executa
  Então ela é reagendada com recuo exponencial
  E após 3 falhas o documento vai para a fila morta com estado "erro"
  E o usuário vê a falha, com opção de tentar de novo

Cenário: Erro permanente não é repetido
  Dado um arquivo corrompido
  Quando a tarefa executa
  Então ela falha na primeira tentativa, sem reagendar
```

**Medida:** p95 do upload abaixo de 500 ms, contra 6,00 s de linha de base.
**Pontos:** 13 · **Flag:** `ocr-assincrono`

---

### US-19 — Arquivos no MinIO com acesso temporário
**Como** Márcia, **quero** meus documentos guardados com segurança e acessíveis
de qualquer dispositivo, **para** não depender do navegador onde enviei.

```gherkin
Cenário: Download por URL temporária
  Quando peço para ver um documento enviado
  Então recebo uma URL pré-assinada com validade de 15 minutos
  E o arquivo não trafega pelo serviço de aplicação

Cenário: URL expirada não abre
  Dado uma URL gerada há 20 minutos
  Quando ela é acessada
  Então o acesso é negado

Cenário: Caminho não expõe dado pessoal
  Quando um arquivo é gravado
  Então a chave do objeto usa hash do e-mail, não o e-mail
```

**Medida:** 100% dos arquivos no MinIO; criptografia em repouso ativa.
**Pontos:** 8 · **Flag:** `storage-minio`

---

### US-20 — Documentos persistidos e desduplicados
**Como** Douglas, **quero** que o sistema reconheça um documento que já enviei,
**para** não pagar processamento nem gerar transação duplicada.

```gherkin
Cenário: Reenvio é reconhecido
  Dado que já enviei uma nota
  Quando envio o mesmo arquivo de novo
  Então recebo o documento anterior, com os dados já extraídos
  E nenhuma chamada à API do Gemini é feita
  E a resposta indica que foi reconhecido como duplicado

Cenário: Histórico sobrevive à troca de dispositivo
  Dado que enviei 10 documentos em um computador
  Quando acesso de outro dispositivo
  Então vejo os 10 documentos com seus estados
```

**Medida:** zero reprocessamento de arquivo idêntico.
**Pontos:** 8 · **Flag:** `documentos-persistidos`

---

### US-21 — Eventos de domínio com Outbox
**Como** Ronaldo, **quero** que fato consumado seja publicado de forma
transacional, **para** que consumidor indisponível não cause perda silenciosa.

```gherkin
Cenário: Publicação é atômica com a escrita
  Quando uma transação é criada no Limits
  Então o evento transacao.criada é gravado na mesma transação do banco
  E o publicador o envia ao Redis Streams em seguida

Cenário: Reentrega não duplica efeito
  Dado que o Insights já processou um evento
  Quando o mesmo evento é entregue de novo
  Então nenhuma alteração adicional ocorre
  E o evento é confirmado como processado

Cenário: Consumidor fora do ar não perde evento
  Dado que o Insights está parado
  Quando 5 transações são criadas
  E o Insights volta
  Então ele processa os 5 eventos pendentes
```

**Medida:** zero evento perdido em teste de caos com queda de consumidor.
**Pontos:** 13 · **Flag:** `eventos-outbox`

---

### US-22 — Trilha de auditoria
**Como** Márcia, **quero** saber de onde veio cada número do meu dashboard,
**para** confiar no que o sistema me diz sobre meu próprio faturamento.

```gherkin
Cenário: Origem do valor é rastreável
  Dado um valor extraído em R$ 1.200,00 e corrigido por mim para R$ 1.250,00
  Quando consulto o histórico da transação
  Então vejo o valor extraído, o método, o valor corrigido e quando

Cenário: A trilha não pode ser alterada
  Quando tento alterar um registro de auditoria
  Então a operação é recusada
```

**Medida:** 100% das mutações de dado fiscal auditadas.
**Pontos:** 5 · **Flag:** n/a

---

### US-23 — Serviço de Insights com projeções materializadas
**Como** Ronaldo, **quero** o cálculo analítico fora do navegador e do Limits,
**para** que o dashboard responda rápido e a regra fiscal viva num lugar só.

```gherkin
Cenário: Projeção reflete a transação
  Quando uma venda é registrada
  Então em até 2 segundos a projeção do usuário está atualizada
  E o dashboard exibe o horário do último recálculo

Cenário: Projeção pode ser reconstruída
  Dado que uma fórmula estava errada
  Quando o recálculo completo é disparado
  Então as projeções são refeitas a partir do Limits
  E os totais conferem com a fonte da verdade

Cenário: Divergência é detectada
  Dado uma projeção fora de sincronia
  Quando a conciliação noturna executa
  Então a divergência é alertada
```

**Medida:** frescor p95 abaixo de 2 s; divergência máxima de R$ 0,01.
**Pontos:** 13 · **Flag:** n/a

---

# EP05 — Dashboard MEI v2

**Objetivo:** responder às perguntas que a tela atual não responde.
**Especificação completa:** [`dashboard-v2.md`](dashboard-v2.md). **29 pontos.**

### US-24 — Migração para Tailwind e sistema visual
**Como** Ronaldo, **quero** a estilização em Tailwind com tokens nomeados,
**para** alinhar o código ao artigo e acabar com cores literais repetidas.

```gherkin
Cenário: A paleta de estados é única
  Dado os níveis ok, atenção, risco e estourado
  Quando qualquer componente exibe um deles
  Então a cor vem de um token do tema, não de um hexadecimal literal

Cenário: Nenhum estilo embutido resta no dashboard
  Quando o DashboardPage é inspecionado
  Então não há atributos style com valores de cor
```

**Medida:** zero hexadecimal literal fora do `tailwind.config.js`.
**Pontos:** 8 · **Flag:** `dashboard-v2`

---

### US-25 — Termômetro do limite e painel de ritmo
**Como** Márcia, **quero** ver de relance quanto do limite já usei e se estou
indo rápido demais, **para** decidir se posso aceitar mais trabalho.

```gherkin
Cenário: O gauge mostra três informações
  Dado faturamento de R$ 47.304,00 sobre limite de R$ 81.000,00
  Quando abro o dashboard
  Então o gauge exibe 58,4%, o valor acumulado e o restante
  E a cor do arco corresponde ao nível de alerta

Cenário: Cor não é o único sinal
  Dado o nível "risco"
  Quando o gauge é exibido
  Então há também rótulo textual e ícone indicando o estado

Cenário: Índice de ritmo com tendência
  Dado taxa diária de R$ 281,57 e referência de R$ 221,92
  Então o índice de ritmo exibido é 1,27
  E a tendência é "acelerando"
```

**Medida:** identificação correta do estado em teste com 8 usuários.
**Pontos:** 8 · **Flag:** `dashboard-v2`

---

### US-26 — Gráfico da corrida contra o limite
**Como** Márcia, **quero** ver a curva do meu faturamento contra o teto e a
projeção até dezembro, **para** entender a trajetória e não só o ponto atual.

```gherkin
Cenário: Três camadas na mesma área
  Quando o gráfico é exibido
  Então vejo a área do acumulado real até hoje
  E a linha pontilhada do ritmo de referência
  E o cone de projeção de hoje até 31 de dezembro

Cenário: O cruzamento é anotado
  Dado que a projeção cruza o teto em 15 de outubro
  Então há uma anotação nesse ponto do gráfico

Cenário: Dado insuficiente não projeta
  Dado um MEI com 2 transações e 18 dias de histórico
  Então o cone não é exibido
  E a mensagem é "dados insuficientes para projeção"

Cenário: Existe alternativa textual
  Quando navego por teclado até o gráfico
  Então alcanço uma tabela com os mesmos valores
```

**Medida:** p95 de renderização abaixo de 300 ms com 3 anos de dados.
**Pontos:** 8 · **Flag:** `dashboard-v2`

---

### US-27 — Mês a mês e origem do faturamento
**Como** Douglas, **quero** comparar meus meses e ver de quais clientes vem meu
faturamento, **para** saber onde estou concentrado.

```gherkin
Cenário: Barras com linha de meta
  Quando o gráfico mensal é exibido
  Então vejo vendas e despesas por mês
  E a linha de meta mensal está sobreposta
  E os meses acima da meta estão destacados

Cenário: Concentração é sinalizada
  Dado que um CNPJ representa 38% do faturamento
  Então ele aparece no topo da lista com o percentual
  E um aviso de concentração é exibido acima de 70%
```

**Medida:** origem identificada em pelo menos 80% das transações vindas de documento.
**Pontos:** 5 · **Flag:** `dashboard-v2`

---

# EP06 — Motor de ritmo e alertas

**Objetivo:** avisar a tempo, sem virar ruído. **26 pontos.**

### US-28 — Cálculo de ritmo, projeção e limite proporcional
**Como** Márcia, **quero** saber quanto posso faturar por mês até dezembro,
**para** planejar em vez de descobrir tarde.

```gherkin
Cenário: Projeção a partir do ritmo
  Dado R$ 47.304,00 em 168 dias decorridos
  Quando a projeção é calculada
  Então a taxa diária é R$ 281,57
  E a projeção anual é R$ 102.773,57
  E a data prevista de estouro é 15 de outubro de 2026

Cenário: Limite proporcional para abertura no ano
  Dado um MEI aberto em julho de 2026
  Quando o limite aplicável é calculado
  Então ele é R$ 40.500,00, e não R$ 81.000,00
  E a interface explica que o limite é proporcional a 6 meses

Cenário: Lançamento atípico é sinalizado
  Dado que uma única venda representa 65% do total do ano
  Então a projeção é marcada como influenciada por lançamento atípico
```

**Medida:** 100% de cobertura dos casos-limite; 80% de mutantes mortos.
**Pontos:** 8 · **Flag:** `alertas-ritmo-vendas`, `limite-proporcional`

---

### US-29 — Alertas acionáveis com controle de ruído
**Como** Márcia, **quero** ser avisada quando algo exigir minha atenção e só
então, **para** não aprender a ignorar os avisos.

```gherkin
Cenário: Alerta traz ação, não só aviso
  Dado o nível "risco"
  Quando o alerta é exibido
  Então ele informa a data prevista de estouro
  E informa quanto posso faturar por mês para não estourar
  E oferece um botão que abre o simulador

Cenário: O mesmo alerta não repete
  Dado que o alerta de risco foi disparado hoje
  Quando o motor reavalia amanhã, no mesmo nível
  Então nenhuma notificação nova é criada

Cenário: Só a escalada notifica
  Dado que o nível estava em "atenção"
  Quando ele passa para "risco"
  Então uma notificação é criada
  Mas se ele voltar para "atenção", nenhuma é criada

Cenário: Teto diário respeitado
  Dado que 3 notificações já foram enviadas hoje
  Quando um quarto alerta é avaliado
  Então ele é registrado no feed, mas não notifica
```

**Medida:** taxa de dispensa sem ação abaixo de 40%.
**Pontos:** 8 · **Flag:** `alertas-ritmo-vendas`

---

### US-29b — Alertas de contexto do negócio
**Como** Douglas, **quero** ser avisado de inatividade, mês atípico, margem
negativa e prazos fiscais, **para** não ser surpreendido em dezembro.

```gherkin
Cenário: Inatividade prolongada
  Dado que não registro nada há 45 dias
  Então recebo um alerta lembrando de registrar as notas do período

Cenário: Mês fora da curva
  Dado que o mês corrente está acima de 2x a mediana dos anteriores
  Então recebo um alerta sugerindo conferir os lançamentos

Cenário: Prazo do DAS
  Dado que hoje é dia 15
  Então o calendário fiscal destaca o DAS com vencimento no dia 20
```

**Medida:** 6 tipos de alerta ativos e testados.
**Pontos:** 5 · **Flag:** `alertas-ritmo-vendas`

---

### US-29c — Centro de notificações in-app
**Como** Márcia, **quero** um lugar com o histórico dos avisos, **para** reencontrar
algo que dispensei sem querer.

```gherkin
Cenário: Feed persistente
  Quando abro o centro de notificações
  Então vejo os alertas em ordem cronológica, com estado de lido
  E posso filtrar por nível

Cenário: Dispensa é lembrada
  Dado um alerta que dispensei
  Quando o motor reavalia no mesmo nível
  Então ele não reaparece como banner
  Mas continua acessível no centro de notificações
```

**Medida:** badge de não lidos correto em 100% dos casos.
**Pontos:** 5 · **Flag:** `alertas-ritmo-vendas`

---

### US-57 — Regras e metas do painel configuráveis pelo usuário
**Como** MEI, **quero** ajustar o teto anual, a faixa de alerta, a meta mensal
e os demais parâmetros que o painel usa, **para** acompanhar uma mudança no
regulamento do MEI ou uma meta própria sem esperar uma nova versão do sistema.
Issue #91 · [ADR-0022](adr/0022-regras-fiscais-parametrizaveis-por-usuario.md).

```gherkin
Cenário: Sem configuração, o painel usa os valores oficiais
  Dado um usuário que nunca configurou nada
  Quando ele abre o painel
  Então o teto é R$ 81.000,00 e a faixa de alerta começa em 80%

Cenário: Teto e faixa de alerta configurados mudam o painel
  Dado a flag ligada
  E o teto configurado em R$ 20.000,00 e a faixa de alerta em 60%
  Quando o faturamento do ano chega a R$ 13.000,00
  Então o resumo, o ritmo e o mês a mês usam R$ 20.000,00
  E o nível é de alerta a partir de 60%

Cenário: Valor fora da faixa é recusado pelo domínio
  Dado a flag ligada
  Quando o usuário grava a faixa de alerta em 150%
  Então a resposta é 422 com a mensagem do domínio
  E a tela mostra o erro embaixo do campo citado

Cenário: Voltar ao padrão
  Dado uma configuração personalizada
  Quando o usuário restaura os padrões
  Então todos os parâmetros voltam aos valores oficiais

Cenário: Flag desligada ignora a configuração gravada
  Dado uma configuração gravada e a flag desligada
  Quando o painel é calculado
  Então valem os valores oficiais
  E o item Configurações não aparece no menu

Cenário: Configuração gravada inválida não derruba o painel
  Dado uma configuração gravada que o domínio passou a recusar
  Quando o painel é calculado
  Então valem os valores oficiais e um aviso vai para o log
```

**Testes:** `limits/tests/test_dominio_parametros.py`,
`limits/tests/test_api_configuracao.py`,
`frontend/src/pages/ConfiguracoesPage.test.tsx`.
**Pontos:** 5 · **Flag:** `metricas-configuraveis`

---

# EP07 — Controles de gestão do MEI

**Objetivo:** deixar o MEI agir, não só olhar. **44 pontos.**

### US-30 — Lançamento manual de venda e compra
**Como** Márcia, **quero** registrar uma venda sem precisar de documento, **para**
lançar o serviço que recebi em dinheiro, sem nota.

> Hoje a única forma de registrar faturamento é enviar um documento — apesar de
> o endpoint `POST /limits/transactions` já existir e não estar exposto na
> interface. É a lacuna funcional mais básica do sistema atual.

```gherkin
Cenário: Lançamento em três campos
  Quando abro o formulário de lançamento
  Então informo valor, data e tipo
  E o lançamento aparece imediatamente na movimentação
  E o dashboard é atualizado

Cenário: Valor inválido é recusado
  Quando informo valor zero ou negativo
  Então a submissão é bloqueada com mensagem clara

Cenário: Data futura exige confirmação
  Quando informo uma data futura
  Então a interface pede confirmação antes de aceitar
```

**Medida:** lançamento completo em menos de 20 segundos.
**Pontos:** 5 · **Flag:** `lancamento-manual`

---

### US-31 — Simulador de faturamento
**Como** Márcia, **quero** simular o impacto de um contrato antes de aceitá-lo,
**para** decidir com informação em vez de intuição.

```gherkin
Cenário: Impacto antes e depois
  Dado faturamento de R$ 47.304,00
  Quando simulo R$ 12.000,00 em 15 de outubro
  Então vejo o percentual e o nível de alerta antes e depois
  E vejo a nova data prevista de estouro
  E nada é gravado

Cenário: Simulação que estoura o teto
  Quando simulo um valor que ultrapassa o limite
  Então o resultado explica a consequência: DAS complementar até 20% de
    excesso, desenquadramento retroativo acima disso
```

**Medida:** simulador usado em mais de 25% das sessões.
**Pontos:** 5 · **Flag:** `simulador-faturamento`

---

### US-32 — Metas mensais
**Como** Douglas, **quero** definir minha meta de faturamento por mês, **para**
acompanhar contra meu plano e não contra uma média genérica.

```gherkin
Cenário: Meta personalizada substitui a padrão
  Dado que defini R$ 8.000,00 para outubro
  Quando o gráfico mensal é exibido
  Então a linha de meta de outubro é R$ 8.000,00

Cenário: Meta acima do seguro é avisada
  Dado que a soma das metas ultrapassa o limite restante
  Então a interface avisa, sem impedir
```

**Pontos:** 3 · **Flag:** `dashboard-v2`

---

### US-33 — Categorias de lançamento
**Como** Douglas, **quero** classificar minhas vendas e despesas, **para** saber
para onde vai meu dinheiro.

```gherkin
Cenário: Categoria sugerida pela descrição
  Dado um documento com descrição "material de escritório"
  Quando reviso o lançamento
  Então a categoria "insumos" vem pré-selecionada, e posso alterar

Cenário: Composição da despesa
  Quando abro o relatório por categoria
  Então vejo a distribuição das despesas do período
```

**Pontos:** 5 · **Flag:** `dashboard-v2`

---

### US-34 — Perfil do MEI
**Como** Márcia, **quero** cadastrar meu CNPJ, ramo e data de abertura, **para**
que os cálculos usem meus dados reais.

> Pré-requisito de US-28 (limite proporcional), do valor correto do DAS e da
> detecção automática de venda contra compra — que hoje depende de um CNPJ
> digitado na barra lateral e guardado no `localStorage`.

```gherkin
Cenário: Data de abertura muda o limite
  Dado que informo abertura em julho de 2026
  Quando o dashboard recarrega
  Então o limite aplicável passa a ser R$ 40.500,00

Cenário: Ramo define o DAS
  Dado que informo o ramo "comércio"
  Então o calendário fiscal calcula o DAS com ICMS

Cenário: CNPJ deixa o localStorage
  Dado que informei meu CNPJ no perfil
  Quando acesso de outro dispositivo
  Então o CNPJ está lá
```

**Pontos:** 5 · **Flag:** n/a

---

### US-35 — Edição em massa
**Como** Douglas, **quero** corrigir vários lançamentos de uma vez, **para** não
repetir 20 vezes a mesma correção.

```gherkin
Cenário: Alteração em lote
  Dado que selecionei 12 lançamentos
  Quando altero o tipo para "compra"
  Então os 12 são atualizados em uma operação
  E o dashboard reflete a mudança
  E a auditoria registra as 12 alterações

Cenário: Desfazer disponível
  Quando a alteração em lote termina
  Então há opção de desfazer por 30 segundos
```

**Pontos:** 5 · **Flag:** `dashboard-v2`

---

### US-36 — Exportação em CSV e XLSX
**Como** Márcia, **quero** exportar meus lançamentos em planilha, **para** enviar
ao contador quando precisar.

```gherkin
Cenário: Exportação respeita os filtros
  Dado que filtrei por vendas do segundo semestre
  Quando exporto em XLSX
  Então o arquivo contém apenas esses lançamentos
  E os valores estão formatados como número, não texto

Cenário: PDF continua funcionando
  Quando exporto em PDF
  Então recebo o relatório anual que já existe hoje
```

**Pontos:** 3 · **Flag:** n/a

---

### US-37 — Comparativo entre anos
**Como** Douglas, **quero** comparar este ano com o anterior, **para** saber se
estou crescendo.

```gherkin
Cenário: Curvas sobrepostas
  Dado que tenho dados de 2025 e 2026
  Quando ativo a comparação
  Então as duas curvas acumuladas aparecem no mesmo gráfico
  E a variação percentual do período é exibida

Cenário: Sem histórico, sem comparação
  Dado que só tenho dados deste ano
  Então a opção fica desabilitada, com explicação
```

**Pontos:** 5 · **Flag:** `dashboard-v2`

---

### US-38 — Filtros e busca na movimentação
**Como** Douglas, **quero** encontrar um lançamento específico rapidamente,
**para** conferir uma nota antiga sem rolar a lista inteira.

```gherkin
Cenário: Filtro combinado
  Quando filtro por tipo "venda", período "agosto" e origem "upload"
  Então a tabela mostra apenas os lançamentos correspondentes
  E o total filtrado é exibido

Cenário: Busca por texto
  Quando busco por "Construtora"
  Então vejo os lançamentos cuja origem ou descrição contém o termo
```

**Pontos:** 3 · **Flag:** `dashboard-v2`

---

### US-38b — Edição em linha na movimentação
**Como** Márcia, **quero** corrigir um valor direto na tabela, **para** não
precisar abrir outra tela.

```gherkin
Cenário: Correção sem sair da tela
  Quando clico no valor de um lançamento
  Então ele vira campo editável
  E ao confirmar, o valor é salvo e o dashboard atualiza
  E a auditoria registra valor anterior e novo
```

**Pontos:** 5 · **Flag:** `dashboard-v2`

---

# EP08 — Gerenciamento de contexto do agente

**Objetivo:** um assistente que lembra, que sabe quando não sabe, e que cobra o
que consome. **Especificação:** [`contexto-do-agente.md`](contexto-do-agente.md).
**50 pontos.**

### US-39 — Conversas persistidas com memória de curto prazo
**Como** Márcia, **quero** que o agente lembre do que acabamos de conversar,
**para** poder dizer "e se eu fizer isso?" sem repetir tudo.

```gherkin
Cenário: Referência ao turno anterior
  Dado que perguntei "quanto ainda posso faturar?"
  Quando pergunto em seguida "e se eu receber R$ 10.000 em outubro?"
  Então a resposta considera a pergunta anterior

Cenário: Conversa sobrevive à recarga
  Dado uma conversa com 5 mensagens
  Quando recarrego a página
  Então o histórico continua visível
```

**Pontos:** 8 · **Flag:** `contexto-orcamento-tokens`

---

### US-40 — Montagem de contexto com orçamento de tokens
**Como** Ronaldo, **quero** que o contexto seja montado em camadas com orçamento,
**para** que documento longo nunca empurre a regra fiscal para fora da janela.

```gherkin
Cenário: Truncamento respeita a prioridade
  Dado um usuário com 40 documentos indexados e 30 turnos
  Quando o contexto é montado
  Então instruções, retrato fiscal e pergunta estão sempre presentes
  E os turnos antigos são os primeiros a ser reduzidos
  E o total fica abaixo de 8.000 tokens

Cenário: Contagem real, não estimada
  Quando o orçamento é verificado
  Então a contagem usa a API de contagem de tokens do modelo
```

**Pontos:** 8 · **Flag:** `contexto-orcamento-tokens`

---

### US-41 — Busca híbrida e segmentação semântica
**Como** Márcia, **quero** que o agente encontre a regra certa mesmo quando eu
uso outras palavras — ou o nome exato de um documento oficial.

```gherkin
Cenário: Paráfrase encontra a regra
  Quando pergunto "posso vender mais este ano?"
  Então o trecho sobre limite anual está entre os recuperados

Cenário: Termo exato encontra a regra
  Quando pergunto sobre "DASN-SIMEI"
  Então o trecho correspondente vem na primeira posição

Cenário: Segmento não corta no meio da regra
  Quando a base é reindexada
  Então nenhum trecho corta uma frase ao meio
  E cada trecho carrega o título da sua seção
```

**Medida:** acerto na primeira posição acima de 90% nas 30 perguntas.
**Pontos:** 8 · **Flag:** `rag-busca-hibrida`

---

### US-42 — Saber quando não sabe
**Como** Márcia, **quero** que o agente diga que não sabe em vez de inventar,
**para** poder confiar no que ele afirma.

```gherkin
Cenário: Pergunta fora do domínio
  Quando pergunto sobre declaração de imposto de renda pessoa física
  Então o agente informa que o assunto está fora da sua base
  E sugere procurar um contador
  E não cita trecho irrelevante como se fosse fonte

Cenário: Limiar descarta trecho ruim
  Dado que o melhor trecho tem distância de cosseno de 0,62
  Quando o contexto é montado
  Então nenhum trecho da base é incluído
```

**Medida:** abstenção correta acima de 90% nas 10 perguntas fora do domínio.
**Pontos:** 5 · **Flag:** `rag-limiar-similaridade`

---

### US-43 — Memória de longo prazo revisável
**Como** Márcia, **quero** que o agente lembre do meu ramo e da minha situação
entre conversas, **para** não repetir isso toda vez — e quero poder apagar.

```gherkin
Cenário: Fato estável é lembrado
  Dado que informei que sou prestadora de serviços
  Quando abro uma conversa nova na semana seguinte
  Então o agente considera isso sem que eu repita

Cenário: A memória é visível e removível
  Quando abro a tela de memória do agente
  Então vejo a lista do que ele guardou sobre mim
  E posso remover qualquer item
  E o item removido não volta

Cenário: Fato não é inventado
  Dado um histórico sem menção ao meu ramo
  Quando a extração de memória executa
  Então nenhum ramo é registrado por inferência
```

**Pontos:** 8 · **Flag:** `contexto-memoria-longa`

---

### US-44 — Resposta com fonte verificável
**Como** Márcia, **quero** ver de onde veio a regra que o agente citou, **para**
conferir antes de tomar uma decisão.

```gherkin
Cenário: Afirmação normativa tem fonte
  Quando o agente afirma que ultrapassar em até 20% gera DAS complementar
  Então a fonte é exibida junto da resposta
  E posso expandir para ver o trecho completo

Cenário: Afirmação sem fonte é sinalizada
  Quando o agente responde sem trecho de apoio
  Então a resposta indica que é orientação geral, não regra citada
```

**Medida:** fidelidade acima de 95% no conjunto de referência.
**Pontos:** 5 · **Flag:** n/a

---

### US-45 — Cobrança por consumo real de tokens
**Como** Ronaldo, **quero** que o faturamento reflita o consumo medido e seja
debitado no servidor, **para** que o modelo de negócio do artigo seja real.

```gherkin
Cenário: Débito proporcional ao consumo
  Dado uma extração que consumiu 1.204 tokens de entrada e 88 de saída
  Quando o débito é calculado
  Então ele usa a tabela de conversão versionada, não um custo fixo

Cenário: Não há como consumir sem ser cobrado
  Quando chamo o endpoint diretamente, sem passar pela interface
  Então o débito acontece de qualquer forma

Cenário: Extrato transparente
  Quando abro o extrato de créditos
  Então vejo data, operação, modelo, tokens de entrada e saída e o débito

Cenário: Reserva devolvida em caso de falha
  Dado que a chamada ao modelo falhou
  Então a reserva é liberada e nada é cobrado
```

**Pontos:** 8 · **Flag:** `billing-tokens-reais`

---

# EP09 — Contextos delimitados e contratos

**Objetivo:** fronteiras explícitas para que a arquitetura sobreviva à evolução.
**16 pontos.**

### US-46 — Camadas anticorrupção nas fronteiras
**Como** Ronaldo, **quero** tradução explícita entre modelos de contextos
diferentes, **para** que mudança no formato de um não vaze para o outro.

```gherkin
Cenário: Resposta do modelo é traduzida, não confiada
  Dado que o Gemini devolve amount como string "1.234,56"
  Quando a camada de tradução processa
  Então o valor vira decimal 1234.56, ou é rejeitado

Cenário: Confiança não atravessa a fronteira
  Quando um documento é confirmado
  Então o grau de confiança da extração não é enviado ao Limits
  Porque uma transação confirmada por um humano é fato, não estimativa

Cenário: Mudança no resumo não quebra o prompt
  Dado que o Limits adiciona um campo ao resumo
  Quando o agente monta o contexto
  Então o prompt não muda, porque a tradução absorve
```

**Pontos:** 5 · **Flag:** n/a

---

### US-47 — Contratos versionados e verificados
**Como** Ronaldo, **quero** que quebra de contrato entre serviços seja detectada
na CI, **para** não descobrir em execução.

```gherkin
Cenário: Campo removido reprova
  Dado um PR que remove total_despesas do resumo
  Quando o teste de contrato executa
  Então a CI falha indicando o consumidor afetado

Cenário: Evento versionado
  Quando um evento é publicado
  Então ele carrega o campo versao
  E consumidor que não reconhece a versão registra WARNING sem quebrar
```

**Pontos:** 5 · **Flag:** n/a

---

### US-48 — Glossário da linguagem ubíqua
**Como** Banca, **quero** ver os termos do domínio definidos por contexto,
**para** avaliar a modelagem estratégica do sistema.

```gherkin
Cenário: Termo ambíguo tem definição por contexto
  Quando consulto o glossário
  Então "documento", "valor", "venda" e "confiança" têm definição própria
    em cada contexto onde aparecem
  E as diferenças estão explicitadas

Cenário: Código usa a linguagem do glossário
  Quando reviso um serviço
  Então as classes de domínio usam os termos definidos para aquele contexto
```

**Pontos:** 3 · **Flag:** n/a

---

### US-48b — Mapa de contexto documentado
**Como** Banca, **quero** ver as relações entre os contextos delimitados,
**para** entender o acoplamento entre as partes do sistema.

```gherkin
Cenário: Relações classificadas
  Quando abro o mapa de contexto
  Então cada relação está classificada como Cliente/Fornecedor, Conformista,
    Núcleo Compartilhado ou Camada Anticorrupção
  E os contextos estão agrupados em núcleo, suporte e genérico
```

**Pontos:** 3 · **Flag:** n/a

---

# EP10 — Segurança, privacidade e LGPD

**Objetivo:** endereçar as pendências que o próprio artigo declara.
**18 pontos.**

### US-49 — Retenção e expurgo de documentos
**Como** Márcia, **quero** que meus documentos não fiquem guardados para sempre,
**para** reduzir a exposição dos meus dados.

```gherkin
Cenário: Expurgo após a retenção
  Dado uma retenção de 5 anos
  Quando a tarefa de expurgo executa
  Então documentos além do prazo são removidos do MinIO e do MongoDB
  E o registro de auditoria é preservado, sem o conteúdo

Cenário: A política é visível
  Quando abro as configurações de privacidade
  Então vejo o prazo de retenção e o que acontece ao final
```

**Pontos:** 5 · **Flag:** n/a

---

### US-50 — Exclusão a pedido do titular
**Como** Márcia, **quero** poder apagar todos os meus dados, **para** exercer meu
direito previsto na LGPD.

```gherkin
Cenário: Exclusão completa e verificável
  Quando solicito a exclusão e confirmo
  Então transações, documentos, arquivos, trechos indexados e memória do
    agente são removidos
  E recebo um comprovante com o que foi excluído
  E a auditoria registra a exclusão sem reter o dado excluído

Cenário: Exclusão exige confirmação explícita
  Quando solicito a exclusão
  Então preciso digitar uma palavra de confirmação antes de prosseguir
```

**Pontos:** 5 · **Flag:** n/a

---

### US-51 — Criptografia e mascaramento
**Como** Márcia, **quero** que meus dados fiscais estejam protegidos em repouso e
não apareçam em log, **para** que um incidente não exponha meu faturamento.

```gherkin
Cenário: Criptografia em repouso
  Quando um arquivo é gravado no MinIO
  Então ele é armazenado criptografado

Cenário: Dado pessoal mascarado na telemetria
  Quando qualquer log, métrica ou rastro é emitido
  Então e-mail aparece como hash
  E CNPJ aparece mascarado
  E texto de OCR nunca aparece
```

**Pontos:** 5 · **Flag:** n/a

---

### US-52 — Limite de taxa e proteção do gateway
**Como** Operador, **quero** limitar requisições por origem, **para** que um laço
descontrolado não esgote a cota da API do Gemini.

```gherkin
Cenário: Excesso é barrado
  Dado o limite de 60 requisições por minuto por origem
  Quando a 61ª chega dentro da janela
  Então a resposta é 429 com Retry-After

Cenário: Operação cara tem limite próprio
  Dado que upload e chat consomem API paga
  Então eles têm limite mais restritivo que as leituras
```

**Pontos:** 3 · **Flag:** `ops-limite-taxa-agressivo`

---

# EP11 — Autenticação real *(fora do escopo desta fase)*

**Registrado, não priorizado.** Ver
[ADR-0011](adr/0011-manter-autenticacao-simplificada.md). **21 pontos.**

Enquanto este épico não for feito, todo endpoint é público e a identidade é
autodeclarada: uma requisição com o e-mail de outra pessoa lê os dados dela.
A plataforma não deve ser exposta publicamente.

### US-53 — Autenticação com JWT e refresh — 8 pontos
### US-54 — Autorização no gateway e propagação de identidade — 8 pontos
### US-55 — Papéis: MEI, contador e administrador — 5 pontos

---

## Resumo por épico

| Épico | Histórias | Pontos | Onda |
| --- | --- | --- | --- |
| EP01 Fundação de engenharia | 8 | 47 | 0 |
| EP02 Observabilidade e SLOs | 6 | 36 | 1 |
| EP03 Feature flags | 3 | 13 | 2 |
| EP04 Arquitetura assíncrona | 6 | 60 | 3 |
| EP05 Dashboard v2 | 4 | 29 | 4 |
| EP06 Ritmo e alertas | 5 | 31 | 4 |
| EP07 Controles de gestão | 10 | 44 | 5 |
| EP08 Contexto do agente | 7 | 50 | 6 |
| EP09 Contextos delimitados | 4 | 16 | 3 e 6 |
| EP10 Segurança e LGPD | 4 | 18 | 7 |
| EP11 Autenticação *(fora de escopo)* | 3 | 21 | — |
| **Total no escopo** | **57** | **344** | — |
