# ADR-0021 — CNPJ do cliente em Limits, para concentração de cliente

- **Data:** 2026-09-12
- **Estado:** Aceita

## Contexto

A US-27 pede "origem do faturamento": de quais clientes vem o faturamento do
MEI, com aviso quando um único CNPJ passa de 70% (`docs/dashboard-v2.md`
§2.5 e §3.1). Calcular isso exige agrupar vendas por CNPJ do cliente — dado
que hoje só existe no serviço `documents`, extraído do documento
(`cnpj_emitente`/`cnpj_destinatario`, ver `processamento.py`).

A ACL `documents -> Limits` da US-46 (ADR-0015, `app/traducao.py`) monta o
payload da transação com uma lista de campos deliberadamente fechada —
`email`, `amount`, `tx_date`, `source`, `tx_type` — para que confiança, método
e modelo de extração não atravessem a fronteira. CNPJ nunca esteve nessa
lista, não por decisão de privacidade explícita, mas porque nenhuma história
até agora precisava dele do lado do Limits.

## Decisão

Estender a lista fechada da ACL com um sexto campo, **`cnpj_cliente`**, e
guardá-lo em `limits.Transaction` (coluna nova, `nullable`), só para
`tx_type == "venda"`.

**Por que só venda.** Numa venda o MEI é o emitente da nota e o cliente é o
destinatário (`processamento.py`: "usuário é emitente -> venda"). Numa
compra é o inverso — o CNPJ disponível (`cnpj_emitente`) é o do fornecedor,
não de um cliente. "De quais clientes vem meu faturamento" não faz pergunta
sobre fornecedor, então esse CNPJ nunca atravessa: menos dado guardado do
que o estritamente necessário para a história (minimização, no espírito do
"Nunca" do CLAUDE.md sobre dado pessoal).

**Por que não junta com `documents` em tempo de consulta, em vez de
duplicar.** `limits` não tem acesso ao MongoDB de `documents`, e criar essa
dependência (banco cruzando serviço) é exatamente o acoplamento estrutural
que o CLAUDE.md exige ADR para adicionar — o custo seria maior que uma
coluna opcional preenchida na escrita, pelo mesmo caminho que já preenche
`amount`/`tx_date`/`source`.

**Mascaramento.** Não é log de CNPJ — é dado de negócio do próprio usuário,
sobre o próprio cliente, mostrado só a ele. `observability.py` já mascara
qualquer string que bata com o padrão de CNPJ antes de qualquer log
estruturado (`CNPJ_REGEX` em `mask_sensitive_data`), então mesmo que o campo
apareça num `logger.info(...)` por engano, ele não vaza em texto puro.

**Nome do cliente (razão social) fica de fora.** Nenhum serviço extrai ou
guarda esse dado hoje — o Gemini/regex de `documents` só produz
`cnpj_emitente`/`cnpj_destinatario`, nunca um nome. O contrato de
`GET /concentracao/{email}` inclui um campo `nome` sempre `None`, para não
fechar a porta a uma fonte futura (ex.: consulta a uma API pública de CNPJ),
mas a interface usa o CNPJ formatado como rótulo até lá. Resolver isso de
verdade é outra história, não parte do escopo da US-27.

## Consequências

**A favor**

- Concentração de cliente calculada sem nova dependência entre serviços.
- O dado guardado é o mínimo necessário: um CNPJ por transação de venda, não
  o documento inteiro nem os dois CNPJs da nota.
- Segue o padrão já estabelecido para colunas novas em produção: `ALTER
  TABLE ... ADD COLUMN IF NOT EXISTS`, idempotente, sem migração formal
  (mesmo caminho de `tx_type`, ver `main.create_tables_with_retry`).

**Contra**

- A lista "fechada" da ACL (ADR-0015) deixa de ser tão fechada — cada campo
  novo é uma decisão própria, documentada aqui e no docstring de
  `traduzir_para_limits`, para não virar uma porta destrancada por
  acréscimo silencioso.
- Lançamento manual (US-30, ainda não implementada) e documento sem
  destinatário identificado não têm `cnpj_cliente` — a concentração calcula
  o percentual sobre o total **identificado**, não sobre o faturamento do
  ano inteiro (ver docstring de
  `dominio.faturamento.calcular_concentracao_clientes`), para não fazer
  essas vendas "desaparecerem" do denominador.

## Alternativas descartadas

**Guardar os dois CNPJs (emitente e destinatário) sempre.** Guardaria dado
que nenhuma história atual usa (o do fornecedor numa compra), contrariando
minimização de dado sem benefício concreto.

**Calcular concentração em `documents` (que já tem os CNPJs).** `documents`
não sabe o valor final confirmado por venda de forma agregável por ano do
jeito que `limits` já sabe (é `limits` quem tem a fonte da verdade de
`amount`/`tx_type`/`tx_date` pós-confirmação); duplicaria ali a soma que já
existe aqui, e a régua de "o que conta como faturamento" (CLAUDE.md) vive em
`limits/app/dominio`.

## Referências

- ADR-0015 (Camadas anticorrupção nas fronteiras) — a ACL que este ADR
  estende.
- `docs/dashboard-v2.md` §2.5 e §3.1 — a regra de concentração de cliente.
- `docs/BACKLOG.md`, US-27.
