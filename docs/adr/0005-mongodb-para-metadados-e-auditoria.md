# ADR-0005 — MongoDB para metadados de documentos e trilha de auditoria

- **Data:** 2026-08-22
- **Estado:** Aceita

## Contexto

O Documents Service não tem banco. O que ele extrai de uma nota fiscal existe
apenas no corpo da resposta HTTP: se o usuário fechar a aba antes de confirmar,
o resultado do OCR e da extração se perde e o documento precisa ser reprocessado
do zero — com novo custo de API do Gemini. A lista de documentos que a interface
exibe vive no `localStorage` do navegador, o que significa que trocar de máquina
apaga o histórico.

Também não existe trilha de auditoria. Quando um valor no dashboard está errado,
não há como responder: foi o OCR que leu errado, foi o Gemini que extraiu
errado, ou foi o usuário que editou? Para um sistema que manipula dado fiscal,
essa pergunta precisa ter resposta.

O formato do que se quer guardar é irregular por natureza: cada tipo de
documento produz campos diferentes, a saída do Gemini muda de forma conforme o
prompt evolui, e o texto bruto do OCR não tem esquema nenhum.

O artigo afirma que o MongoDB guardaria "metadados e documentos estruturados de
forma flexível" e "registros não estruturados e logs".

## Decisão

Adotar **MongoDB** para duas coleções, e apenas duas.

**Coleção `documentos`** — ciclo de vida completo de cada arquivo enviado:

```javascript
{
  _id: "uuid",
  usuario_email: "mei@exemplo.com",
  arquivo: { nome_original, chave_minio, tamanho_bytes, tipo_mime, hash_sha256 },
  estado: "recebido | processando | extraido | confirmado | descartado | erro",
  ocr: { motor: "tesseract", texto: "...", duracao_ms: 820 },
  extracao: {
    metodo: "gemini | regex",
    modelo: "gemini-2.5-flash",
    campos: { valor, data, cnpj_emitente, cnpj_destinatario, descricao },
    confianca: 0.95,
    duracao_ms: 3310,
    tokens: { entrada: 1204, saida: 88 }
  },
  revisao_humana: { campos_alterados: ["valor"], em: "..." },
  transacao_limits_id: 42,
  historico: [ { evento, em, por, detalhe } ],
  criado_em, atualizado_em
}
```

**Coleção `auditoria`** — trilha imutável, apenas de escrita, com retenção de 5
anos: quem fez, o quê, sobre qual recurso, quando, com qual `trace_id`, valor
anterior e valor novo.

O que **não** vai para o Mongo: transação financeira, saldo de tokens e usuário.
Esses continuam em PostgreSQL, onde consistência transacional e restrição de
integridade importam mais que flexibilidade de esquema.

Índices previstos: por usuário e data de criação, por estado, e um índice único
parcial sobre o hash SHA-256 do arquivo — que entrega deduplicação de reenvio
como efeito colateral.

## Consequências

**A favor**

- Reenviar o mesmo arquivo passa a ser detectado pelo hash, evitando cobrança
  duplicada de API e transação duplicada no Limits.
- A lista de documentos sai do `localStorage` e passa a ser real e portátil.
- A trilha de auditoria responde "de onde veio este número", que é requisito
  prático para dado fiscal e argumento direto na seção de LGPD do artigo.
- O histórico embutido no próprio documento registra a jornada completa sem
  precisar de junção entre tabelas.

**Contra**

- Mais um paradigma de banco para operar, monitorar e fazer backup.
- Ausência de esquema exige disciplina. Mitigada validando toda escrita com
  modelos Pydantic na aplicação e declarando validação de esquema no lado do
  Mongo.
- Consistência entre Mongo e PostgreSQL não é transacional. Resolvida pelo
  padrão Outbox descrito no ADR-0006.

## Alternativas descartadas

**Coluna JSONB no PostgreSQL.** Tecnicamente suficiente — o tipo JSONB do
Postgres é maduro e indexável. Descartada porque exigiria criar um banco novo
para o Documents de qualquer forma, e porque contradiria o artigo sem ganho
compensatório.

**Não persistir nada.** É o estado atual, e é a origem dos três problemas
descritos no contexto.

## Referências

- Documentação do MongoDB sobre validação de esquema e índices parciais.
- Kleppmann, M. *Designing Data-Intensive Applications*, cap. 2 (quando esquema
  flexível ajuda e quando atrapalha).
