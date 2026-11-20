# ADR-0012 — Medir tokens reais do LLM para o faturamento

- **Data:** 2026-08-22
- **Estado:** Aceita

## Contexto

O artigo apresenta o faturamento por consumo de tokens como um dos pilares do
modelo de negócio e como contribuição para a pesquisa em SaaS baseado em
consumo. A implementação atual não mede consumo nenhum.

O Billing Service tem uma tabela fixa de preços:

```python
TOKEN_COSTS = {"document_confirm": 15, "chat_message": 5}
```

Confirmar um documento custa 15 tokens fictícios, independentemente de o arquivo
ser um recibo de três linhas ou um DANFE de duas páginas. Uma pergunta de cinco
palavras ao agente custa os mesmos 5 tokens que uma conversa longa com contexto
recuperado do RAG. Não há relação entre o que é cobrado e o que é gasto.

Pior: **o débito acontece no frontend**. É o `UploadPage.tsx` que chama
`POST /billing/tokens/consume` depois de confirmar. Nada impede consumir o
serviço sem passar pela interface e nunca ser cobrado — e nada garante que o
débito aconteça quando a interface falha no meio do fluxo.

A resposta da API do Gemini já traz `usage_metadata` com a contagem exata de
tokens de entrada, de saída e de raciocínio. O dado está disponível e está sendo
descartado.

## Decisão

Passar a medir e cobrar **consumo real**, e mover a cobrança para o servidor.

**1. Capturar o uso real.** Toda chamada ao Gemini — extração multimodal,
geração de embedding e chat — registra `prompt_token_count`,
`candidates_token_count` e `total_token_count`, junto do modelo usado e da
operação.

**2. Converter para unidades de plataforma.** O usuário não deve raciocinar em
tokens de um fornecedor específico. Uma tabela de conversão versionada traduz
tokens do modelo em créditos da plataforma, com margem explícita:

```yaml
gemini-2.5-flash:
  entrada:  { por_1k_tokens: 1 }
  saida:    { por_1k_tokens: 3 }
gemini-embedding-001:
  entrada:  { por_1k_tokens: 0.1 }
margem: 1.5
minimo_por_operacao: 1
```

**3. Cobrar no servidor, dentro da operação.** O débito deixa de ser chamada do
frontend e vira parte da transação do serviço que consumiu o recurso, publicando
`tokens.consumidos` pelo Outbox do ADR-0006. Impossível consumir sem ser
cobrado; impossível ser cobrado sem consumir.

**4. Reservar antes, acertar depois.** Antes de uma operação cara, o Billing
reserva uma estimativa. Após a resposta do modelo, o valor real substitui a
reserva. Isso evita saldo negativo e evita bloquear operação legítima por
estimativa pessimista.

**5. Tornar o consumo visível.** Extrato por operação com data, tipo, modelo,
tokens de entrada e saída, créditos debitados e custo estimado em reais. O
usuário passa a ver para onde foi o saldo, e o projeto passa a ter dado real de
custo por usuário.

**6. Métrica operacional.** Tokens e custo estimado viram séries no Prometheus,
rotuladas por modelo e operação. É assim que se responde quanto custa, de fato,
manter um MEI ativo na plataforma — número que o artigo hoje não tem.

## Consequências

**A favor**

- O modelo de faturamento por consumo deixa de ser afirmação e passa a ter
  medição, o que fortalece diretamente a contribuição declarada do trabalho.
- O custo real por operação vira dado observável, permitindo discutir viabilidade
  comercial com número em vez de suposição.
- A brecha de cobrança pelo cliente é fechada.
- Extrato transparente é boa prática de produto e evidência de UX na defesa.

**Contra**

- O custo de uma operação deixa de ser previsível antes de executá-la. Mitigado
  exibindo uma faixa estimada na interface antes da confirmação.
- Reserva e acerto adicionam um passo de estado no Billing.
- No modo demonstração, sem chave do Gemini, não há uso real. Nesse caso a
  tabela fixa atual continua valendo, sinalizada como estimativa.

## Alternativas descartadas

**Manter o custo fixo por ação.** Simples e previsível, mas desconectado do
consumo real — o que esvazia justamente a tese de faturamento por consumo que o
artigo defende.

**Repassar o custo do fornecedor em reais, sem crédito intermediário.** Amarra o
preço ao fornecedor e à variação cambial, e expõe ao usuário uma unidade que não
é dele.

## Referências

- Documentação da API Gemini sobre `usage_metadata`.
- Armbrust, M. et al. *A View of Cloud Computing*, 2010 — cobrança proporcional
  ao uso como característica definidora do modelo.
