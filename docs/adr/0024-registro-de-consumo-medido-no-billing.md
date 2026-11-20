# ADR-0024 — Registro do consumo medido no billing, antes do débito proporcional

- **Data:** 2026-11-19
- **Estado:** Aceita
- **Relacionado:** ADR-0012 (medir tokens reais para o faturamento), US-45, flag `billing-tokens-reais`

## Contexto

O ADR-0012 decidiu medir o consumo real de tokens e cobrar por ele, no
servidor, com reserva e acerto. Até aqui só a primeira metade do item 1 foi
feita: os serviços leem o `usage_metadata` de cada chamada ao Gemini e
alimentam uma métrica do Prometheus. Faltava:

- guardar o consumo **por usuário** (a métrica é agregada por modelo e
  operação, sem dono);
- contar as chamadas de **embedding**, cuja resposta não traz contagem de
  tokens;
- ter um **extrato** que permita comparar o débito fixo atual (15 créditos por
  nota confirmada, 5 por mensagem) com um débito proporcional ao consumo.

Uma conferência em 19/11/2026 mostrou que o valor registrado coincide com o
da API e com uma contagem independente (`count_tokens`), então a medição é
confiável o bastante para ser guardada. A US-45 completa (débito no servidor,
reserva, devolução em falha) mexe no fluxo de confirmação e de chat e não
cabe no prazo da entrega do TG.

## Decisão

Fazer o registro e o extrato agora, e deixar o débito para depois.

1. **Billing ganha `POST /usage` e `GET /usage/{email}`.** Cada registro guarda
   serviço, operação, modelo, tokens de entrada e saída, os créditos que a
   operação custaria pela tabela de conversão versionada do ADR-0012 (versão
   `2026-11-v1`: 1 crédito por mil tokens de entrada e 3 por mil de saída no
   modelo gerador, 0,1 por mil no de embedding, margem de 1,5, mínimo de 1) e
   um custo estimado em reais pelo preço de referência das métricas. O saldo
   **não** é debitado por esse caminho.
2. **Documentos e Orquestrador do Agente chamam o billing diretamente por
   HTTP**, numa thread de um pool pequeno (`consumo.py`, copiado nos dois
   serviços). É uma dependência nova entre serviços, por isso este ADR.
3. **Melhor esforço.** Se o billing estiver fora, o registro se perde com um
   WARNING estruturado; a extração e o chat não esperam nem falham por isso.
4. **Embedding contado em segundo plano** pelo endpoint `count_tokens` da API,
   que não é cobrado. A semeadura da base de regras não tem usuário e não
   entra em extrato nenhum.
5. **Atrás da flag `billing-tokens-reais`**, já declarada no inventário, com
   padrão desligado.

## Consequências

**A favor**

- O artigo passa a ter consumo e custo por operação medidos por usuário, e a
  comparação entre a tabela fixa e a proporcional sai de dado, não de
  suposição.
- A US-45 completa reaproveita a tabela de conversão, o modelo de dados e o
  extrato; falta trocar o débito.

**Contra**

- Registro síncrono-em-thread, sem Outbox: se o serviço cair entre a chamada
  ao Gemini e o envio, o registro se perde. Aceitável para um extrato
  informativo; inaceitável quando virar cobrança, e aí o envio deve passar pelo
  Outbox (ADR-0006/0018), como o ADR-0012 previa.
- A contagem do embedding é uma chamada extra à API por embedding (gratuita,
  mas com latência, que fica fora da requisição do usuário).
- Os preços de referência do fornecedor estão no código e não foram
  conferidos com a fatura.

## Alternativas descartadas

**Publicar o consumo pelo Outbox desde já.** Mais correto, mas exige tabela de
outbox e consumidor em dois serviços que não têm PostgreSQL próprio para isso
(Documentos) ou que não publicam eventos hoje (Agente). Fica para a etapa de
cobrança.

**Ler o consumo do Prometheus.** A métrica não tem o usuário como rótulo, e
pôr o e-mail num rótulo violaria a regra de cardinalidade e de privacidade
das métricas.
