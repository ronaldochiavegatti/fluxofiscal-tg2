# ADR-0017 — Trilha de auditoria encadeada por hash

- **Data:** 2026-09-08
- **Estado:** Aceita
- **Contexto:** US-22 (trilha de auditoria)

## Contexto

O ADR-0005 previu a coleção `auditoria` no MongoDB — "trilha imutável, apenas de
escrita" — mas não definiu **como** a imutabilidade é garantida. MongoDB não tem
tabela append-only nativa: `updateOne` e `deleteOne` funcionam em qualquer
documento.

A US-22 pede duas garantias:

1. **Rastreabilidade** — o histórico de uma transação mostra o valor extraído, o
   método, o valor corrigido pelo humano e quando.
2. **Imutabilidade** — tentar alterar um registro de auditoria é recusado.

## Decisão

**Onde.** A trilha vive no `documents`, que já é o dono do MongoDB (ADR-0005).
As mutações de dado fiscal que passam por ele — a extração de um documento
(`documento.extraido`) e a confirmação humana dos campos (`documento.confirmado`)
— viram registro. As mutações que acontecem só no `limits`
(`transacao.atualizada`, `transacao.removida`) entram como consumidor de evento
na US-21, quando o barramento existir; até lá a trilha cobre a origem do número
(extração → correção), que é o cenário da história.

**Como a imutabilidade é garantida.**

- **Nível da API.** `RepositorioAuditoriaMongo` expõe só `registrar`,
  `por_recurso`, `listar` e `verificar_integridade`. Não há método de alteração
  nem de remoção. As rotas HTTP de escrita não existem; `PUT`/`PATCH`/`DELETE`
  em `/auditoria/{id}` respondem `405`.
- **Nível do dado.** Cada registro carrega um `seq` monotônico, o `hash` do
  registro anterior (`hash_anterior`, começando na "gênese" `0…0`) e o próprio
  `hash` = `SHA-256(hash_anterior + corpo_canônico)`. `corpo_canônico` é o JSON
  do registro com chaves ordenadas e o timestamp como string ISO de
  milissegundos (round-trip exato pelo BSON).
- **Detecção.** `verificar_integridade()` recalcula a cadeia. Alterar qualquer
  campo de um registro, ou remover um registro do meio, muda um hash e a
  verificação falha. Exposto em `GET /auditoria/integridade`.

## Consequências

**A favor**

- Adulteração de um registro ou remoção do meio da cadeia é **detectável** sem
  depender de permissão de banco — a verificação é aritmética.
- A trilha responde "de onde veio este número" com o antes e o depois lado a
  lado — argumento direto na seção de LGPD do artigo.
- `registrar` é uma operação só (um `insert_one`), sem transação distribuída.

**Contra**

- **Truncamento da cauda não é detectável** pelo encadeamento sozinho: apagar os
  N últimos registros deixa uma cadeia mais curta porém consistente. Mitigação
  fora do escopo desta história — publicar periodicamente o hash da cabeça num
  meio externo (log de deploy, e-mail, um segundo armazenamento) dá o ponto de
  ancoragem. Anotado como dívida.
- `verificar_integridade()` global varre a coleção inteira. Aceitável na escala
  do TG; se crescer, verifica-se por janela ou incrementalmente a partir do
  último ponto validado.
- A cadeia global mistura recursos por ordem de escrita, então a verificação por
  recurso valida só o `hash` de cada registro daquele recurso, não o
  encadeamento entre eles.

## Alternativas descartadas

**Coleção capped do MongoDB.** É append-only e ordenada, mas tem tamanho fixo
(sobrescreve os mais antigos) e ainda permite `updateOne` que não cresça o
documento. Não resolve alteração.

**Validação de esquema + usuário de banco só-inserção.** Reduz o risco por
configuração, mas depende de a configuração estar certa em todo ambiente e não
deixa prova quando algo passa. O hash-chain deixa prova.

**Assinar cada registro com uma chave.** Mais forte contra adulteração por quem
não tem a chave, mas introduz gestão de chave — e o vetor real aqui é um
operador com acesso ao banco, que teria a chave também. O encadeamento é
proporcional à ameaça desta fase.

## Referências

- Haber, S.; Stornetta, W. S. *How to Time-Stamp a Digital Document*, 1991 (a
  ideia original de encadeamento por hash).
- Richardson, C. *Microservices Patterns*, 2018, cap. 11 (auditoria como
  consumidor de eventos de domínio — o destino na US-21).
