# ADR-0015 — Camadas anticorrupção nas fronteiras entre serviços

- **Data:** 2026-09-08
- **Estado:** Aceita

## Contexto

Três fronteiras da plataforma passam dados de um modelo mental para outro sem
tradução, e cada uma já causou ou ameaça causar um acoplamento indevido:

1. **Gemini → Documents.** A resposta do modelo é lida quase crua em
   `sanitize_gemini_result`. O `amount` chega ora como número, ora como string
   com máscara brasileira (`"1.234,56"`), ora como texto livre. Um `float()`
   direto ou aceita o valor errado ou o descarta silenciosamente. O formato de
   uma API externa está ditando o comportamento do domínio.
2. **Documents → Limits.** O `POST /transactions` monta o payload a partir do
   dicionário de extração. Campos que são estimativa — grau de confiança, método
   e modelo de extração — ficam a um descuido de distância de atravessar a
   fronteira e contaminar um registro que, depois da confirmação humana, é fato.
3. **Limits → Agent.** O `build_prompt` lê `summary.get("total_revenue")`,
   `summary.get("annual_limit")` e mais seis chaves diretamente do JSON do
   Limits. Renomear ou remover um campo do resumo quebra o prompt do agente à
   distância, sem nada na CI apontando o consumidor afetado.

O padrão comum: o vocabulário e o formato de um contexto vazam para dentro de
outro, e a mudança em um lado propaga risco para o outro.

## Decisão

Introduzir uma **camada anticorrupção (ACL)** explícita em cada uma dessas
fronteiras — um módulo de tradução que é o único ponto do código que conhece os
dois lados.

**Documents — `app/traducao.py`**

- `traduzir_valor_monetario(bruto)` converte o `amount` do modelo em `float`
  positivo ou devolve `None`. Aceita número, máscara brasileira e americana;
  rejeita ausência, lixo, valor não positivo e acima do teto. O domínio nunca
  vê o formato bruto do modelo.
- `traduzir_para_limits(...)` monta o payload da transação com uma **lista de
  chaves fechada** (`email`, `amount`, `tx_date`, `source`, `tx_type`).
  Confiança, método e modelo de extração ficam do lado de cá por construção, não
  por disciplina.

**Agent — `app/acl.py`**

- `RetratoFiscal` é o modelo interno do agente para a situação fiscal do MEI,
  com o vocabulário do agente (`faturamento_vendas`, `limite_anual`,
  `falta_para_o_limite`), não o do Limits.
- `traduzir_resumo_limits(resposta)` converte o JSON do Limits em
  `RetratoFiscal`. Campo desconhecido é **ignorado**; campo ausente recebe um
  **padrão explícito**. O `build_prompt` passa a consumir o `RetratoFiscal` e
  não tem mais nenhuma referência ao formato do Limits.

A tradução é sempre para dentro: cada serviço protege o próprio modelo, e a
dependência de formato fica confinada a um arquivo testável isoladamente.

## Consequências

**A favor**

- Mudança de formato num serviço para na camada de tradução do consumidor, em
  vez de se espalhar. Adicionar um campo ao resumo do Limits não altera o prompt
  do agente — há teste que fixa isso.
- A regra "confiança não é fato" vira estrutura: o payload para o Limits não tem
  onde carregar a estimativa.
- O parsing frágil de valor monetário fica num único lugar, com uma bateria de
  casos de máscara e de lixo, em vez de repetido e incompleto.
- Prepara o terreno para a US-47: o contrato verificado na CI protege o
  produtor, a ACL protege o consumidor.

**Contra**

- Uma indireção a mais em cada fronteira. O `build_prompt` não lê mais o resumo
  direto; passa pelo `RetratoFiscal`.
- Dois vocabulários para o mesmo conceito (`total_revenue` no Limits,
  `faturamento_vendas` no agente), com o mapa vivendo só na tradução. É o custo
  esperado do padrão, e o glossário da US-48 registra a correspondência.

## Alternativas descartadas

**Contrato compartilhado (pacote de modelos Pydantic comum).** Um único
`SummaryModel` importado pelo Limits e pelo Agent elimina a tradução, mas troca
o acoplamento de formato por acoplamento de código: todo serviço passa a
depender do mesmo pacote e a subir de versão junto. Contradiz a autonomia que
motivou os microsserviços.

**Validar só com Pydantic na borda.** `LimitsTransaction` já valida tipo e
faixa, e continua fazendo isso. Não resolve as fronteiras 1 e 3: não normaliza a
máscara do Gemini nem impede o prompt de depender do nome de um campo do Limits.

**Deixar como está e cobrir com teste de contrato (US-47).** O teste de contrato
pega a quebra depois que ela é escrita. A ACL evita que a quebra chegue ao
código do consumidor. As duas medidas são complementares, não substitutas.

## Referências

- Evans, E. *Domain-Driven Design*, 2003, cap. 14 (Anticorruption Layer).
- Newman, S. *Building Microservices*, 2ª ed., 2021, cap. 4 (integração e
  acoplamento).
