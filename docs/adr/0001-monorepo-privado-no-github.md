# ADR-0001 — Monorepo privado no GitHub

- **Data:** 2026-08-22
- **Estado:** Aceita
- **Decisor:** Ronaldo Chiavegatti

## Contexto

Até aqui o projeto viveu numa pasta local, sem versionamento. O código chegou
como um `.zip` chamado `fiscalflowbackend-main`, nome que denuncia origem em um
download de repositório. Não existe histórico: nenhum commit registra quando o
RAG foi implementado, quando o `tx_type` foi introduzido ou por que o OCR ganhou
um caminho de contingência por expressões regulares.

Para um Trabalho de Graduação isso é uma perda dupla. A primeira é técnica: sem
histórico não há como reverter, comparar ou bissectar um defeito. A segunda é
acadêmica: o artigo afirma que o projeto seguiu SCRUM com sprints e entregas
incrementais, e o histórico do Git é justamente a evidência empírica disso.

Há ainda um problema urgente: o arquivo `.env` na raiz da aplicação contém uma
chave real da API do Gemini, em texto puro.

## Decisão

Criar **um único repositório privado** no GitHub contendo aplicação,
infraestrutura, documentação de engenharia e os artefatos do TG (artigo e termo
de orientação).

O `.env` entra no `.gitignore` desde o primeiro commit e é substituído por um
`.env.example` sem valores. A chave já exposta deve ser revogada e rotacionada
no console do Google AI Studio.

## Consequências

**A favor**

- Uma mudança que atravessa backend, frontend e infraestrutura cabe em um único
  commit e em um único PR — que é o caso da maioria das entregas planejadas.
- A CI enxerga o sistema inteiro e consegue subir o `docker compose` completo
  para testar integração de verdade.
- O histórico conta a história do trabalho de forma linear e defensável.
- O repositório privado remove a urgência de vazamento de segredo, sem eliminar
  a necessidade de rotacionar a chave.

**Contra**

- Todo pipeline é acionado por qualquer mudança. Mitigado com filtros de
  caminho e cache por serviço no GitHub Actions.
- Repositório privado não serve como portfólio público. Aceito: o repositório
  pode ser tornado público após a defesa, depois da limpeza de segredos.

## Alternativas descartadas

**Um repositório por microsserviço.** É o que a literatura de microsserviços
costuma recomendar, porque reforça a autonomia dos times. Aqui não existe time:
existe um autor. Sete repositórios significariam sete pipelines, sete conjuntos
de segredos e mudanças coordenadas manualmente — todo o custo do modelo, nenhum
dos benefícios.

**Repositório público desde já.** Descartado por causa da chave exposta e
porque o texto do artigo ainda está em revisão.

## Referências

- Newman, S. *Building Microservices*, 2ª ed., cap. 4 (custo real do
  multi-repo em equipes pequenas).
- Documentação do GitHub sobre `CODEOWNERS` e rulesets de branch.
