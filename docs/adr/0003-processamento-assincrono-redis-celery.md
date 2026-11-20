# ADR-0003 — Processamento assíncrono com Redis e Celery

- **Data:** 2026-08-22
- **Estado:** Aceita

## Contexto

Hoje o `POST /documents/upload` faz tudo dentro do ciclo da requisição HTTP:
grava o arquivo, roda o Tesseract, converte PDF em imagem, chama o Gemini
multimodal e só então responde. Os próprios números do artigo mostram o custo
disso — 4,51 segundos de média, com máximo de 6,00 segundos por documento. O
`POST /agent/chat` é pior: 8,54 segundos de média, porque encadeia geração de
embedding, busca vetorial e chamada ao modelo.

Enquanto uma requisição dessas ocupa um worker do Uvicorn, ele não atende mais
ninguém. Um MEI enviando dez notas em sequência trava o serviço para os demais.
Não há retentativa: se o Gemini devolver 429 ou 503, o `except Exception` cai
silenciosamente no caminho de contingência por expressões regulares e o usuário
recebe dados piores sem saber por quê.

O artigo afirma que "o processamento assíncrono de OCR e as consultas ao LLM
ficarão a cargo de Celery e Redis". Nenhum dos dois existe no código.

## Decisão

Introduzir **Redis** como broker e **Celery** como executor de tarefas em
segundo plano, num serviço `worker` novo que compartilha o código de domínio do
Documents.

O upload passa a ser um protocolo de duas fases:

1. `POST /documents/upload` grava o arquivo no MinIO, cria o registro com estado
   `recebido`, enfileira `processar_documento` e responde **202 Accepted** com o
   identificador do documento e a URL de acompanhamento.
2. O worker executa OCR e extração, atualiza o estado para `extraido` e publica
   o evento `documento.extraido`.
3. O frontend acompanha por *polling* no `GET /documents/{id}` (Server-Sent
   Events fica registrado como evolução).

Tarefas na fila: `processar_documento`, `gerar_embeddings`,
`reindexar_base_conhecimento`, `recalcular_insights`, `expurgar_documentos`.

Política de retentativa: no máximo 3 tentativas, recuo exponencial começando em
2 segundos com variação aleatória, apenas para falhas transitórias (429, 5xx,
timeout). Erro permanente (arquivo corrompido, formato não suportado) vai direto
para a fila morta, sem repetir.

Filas separadas por perfil de carga: `ocr` (uso intenso de CPU, concorrência 2),
`llm` (espera de entrada e saída, concorrência 8), `manutencao`.

## Consequências

**A favor**

- A API responde em dezenas de milissegundos, não em segundos.
- Falha transitória do Gemini deixa de virar degradação silenciosa da qualidade
  da extração.
- As filas ficam observáveis: profundidade, idade da mensagem mais antiga e taxa
  de falha viram métricas e alertas (ADR-0007).
- O Redis já entra no ambiente e serve também de cache de embeddings e de
  barramento de eventos (ADR-0006), sem trazer mais um servidor.

**Contra**

- Mais duas peças no `docker compose` (`redis`, `worker`) e a complexidade
  operacional que vem com elas.
- A interface precisa lidar com estado intermediário — telas de "processando",
  atualização por polling, tratamento de falha assíncrona.
- Depuração distribuída fica mais difícil. Mitigado propagando o `trace_id` da
  requisição para dentro da tarefa Celery, o que mantém o rastro contínuo no
  Tempo.

## Alternativas descartadas

**`BackgroundTasks` do FastAPI.** Roda no mesmo processo: não sobrevive a
reinício do contêiner, não tem retentativa, não tem visibilidade e não escala
para fora do processo. Serve para disparar um e-mail, não para um pipeline de
OCR.

**RabbitMQ ou Kafka.** Mais robustos, e Kafka daria retenção e reprocessamento
de eventos. Ambos foram descartados por peso: um broker a mais para operar e
justificar, quando o Redis já é exigido pelo artigo e cobre os três usos
necessários.

**Manter tudo síncrono.** Deixaria o código em contradição com o artigo e
manteria o gargalo que os próprios números do trabalho evidenciam.

## Referências

- Richardson, C. *Microservices Patterns*, 2018, cap. 3 (mensageria assíncrona).
- Documentação do Celery sobre roteamento de filas e políticas de retentativa.
