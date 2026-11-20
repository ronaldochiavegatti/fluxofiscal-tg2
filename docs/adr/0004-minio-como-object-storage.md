# ADR-0004 — MinIO como armazenamento de objetos

- **Data:** 2026-08-22
- **Estado:** Aceita

## Contexto

O Documents Service grava os arquivos enviados em `/data/uploads`, dentro de um
volume Docker montado no contêiner. Isso amarra o serviço a uma única instância:
subir uma segunda réplica faria com que metade das requisições não encontrasse o
arquivo que a outra metade gravou.

Não há controle de acesso — qualquer processo dentro do contêiner lê qualquer
nota fiscal. Não há versionamento nem política de retenção, o que colide direto
com a seção de LGPD do artigo, que reconhece "definição de prazo de retenção e
exclusão de documentos" como pendência.

O artigo afirma que "os documentos enviados pelos usuários ficarão em um serviço
compatível com Amazon S3, usando o MinIO como alternativa local e open-source".

## Decisão

Adotar **MinIO** como armazenamento de objetos, acessado pelo SDK `boto3` com a
API S3.

Organização dos objetos:

```
fiscalflow-documents/
  {email_hash}/{ano}/{mes}/{document_id}{extensao}     original enviado
  {email_hash}/{ano}/{mes}/{document_id}_pagina1.png   derivado para o LLM
```

O `email_hash` é um SHA-256 truncado do e-mail: os caminhos deixam de expor
dado pessoal para quem apenas lista o bucket.

Configuração do bucket: versionamento ligado, criptografia em repouso com
SSE-S3, regra de ciclo de vida movendo objetos para expurgo após o prazo de
retenção definido na política de privacidade.

O download pela interface passa a usar **URL pré-assinada com validade de 15
minutos**, gerada pelo Documents. O arquivo nunca trafega pelo serviço de
aplicação.

## Consequências

**A favor**

- O Documents Service vira sem estado e pode ser replicado.
- Criptografia em repouso e retenção automática endereçam duas pendências
  declaradas de LGPD.
- URL pré-assinada tira o tráfego de arquivo do caminho da aplicação.
- Migrar para S3 real depois é troca de variável de ambiente, não reescrita.

**Contra**

- Mais um serviço no Compose, com credenciais próprias.
- Migração dos arquivos já existentes em `documents_data`. Mitigada por um
  comando `migrar_para_minio` idempotente, executável uma vez.
- A leitura local deixa de ser `Path.read_bytes()`. Mitigado isolando o acesso
  atrás de uma interface `ArmazenamentoDeDocumentos`, com implementação de
  sistema de arquivos preservada para testes.

## Alternativas descartadas

**Continuar com volume Docker.** Impede replicação, não oferece criptografia
nem retenção, e contradiz o artigo.

**Gravar os arquivos no PostgreSQL como `bytea`.** Simplifica a topologia, mas
infla o banco, degrada backup e restauração e desperdiça conexões do pool com
transferência de binário.

## Referências

- Documentação do MinIO sobre compatibilidade com a API S3 e ciclo de vida.
- Lei nº 13.709/2018 (LGPD), art. 46 (medidas de segurança) e art. 16
  (eliminação após o término do tratamento).
