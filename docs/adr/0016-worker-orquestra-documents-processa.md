# ADR-0016 — O worker orquestra, o Documents processa

- **Data:** 2026-09-08
- **Estado:** Aceita
- **Contexto:** US-18 (upload assíncrono)

## Contexto

A US-18 tira o OCR e a extração da requisição de upload: o `/upload` responde
`202 Accepted` e o trabalho vai para a fila Celery (ADR-0003). A pergunta de
desenho é **onde o pipeline de extração roda** — o mesmo pipeline que hoje vive
inteiro no `documents/app/` (Tesseract, conversão de PDF, chamada multimodal ao
Gemini, sanitização, heurística de venda/compra, pontuação de confiança).

O diagrama da arquitetura (`docs/arquitetura/README.md`, seção 4) desenhava o
`worker` lendo o arquivo do MinIO e chamando o Gemini diretamente. Levar isso a
sério exigiria:

- **copiar** ~300 linhas de pipeline (`processamento.py`, `armazenamento.py`,
  `repositorio.py`) para dentro do `worker`, com a regra do monorepo "sem pacote
  compartilhado, copie e mantenha em sincronia" (como `observability.py`);
- dar ao `worker` as dependências de SO do OCR (`tesseract-ocr`, `poppler`) e as
  bibliotecas (`pytesseract`, `pdf2image`, `pillow`, `google-genai`, `pymongo`,
  `boto3`);
- manter dois lugares que evoluem juntos toda vez que a extração muda — e a
  extração é a parte do sistema que mais muda.

## Decisão

O **worker não executa o pipeline** — ele o **orquestra**. A extração continua
inteira no `documents`, exposta numa rota interna:

```
POST /documents/_interno/processar/{documento_id}
```

`include_in_schema=False`, protegida por um segredo compartilhado opcional
(`INTERNO_TOKEN`; vazio em dev, como o resto de ADR-0011). Ela é idempotente: um
documento já `extraido` volta o estado atual sem reprocessar.

A tarefa `processar_documento` (fila `ocr`) faz só três coisas:

1. `POST` na rota interna;
2. `503` da rota (falha transitória do Gemini) → `self.retry` com recuo
   exponencial + jitter, no máximo 3 vezes;
3. esgotadas as tentativas → a rota é chamada com `?ultima_tentativa=true` e
   marca o documento em `erro` (a "fila morta" deste desenho — Redis Streams não
   tem DLQ nativa como o RabbitMQ).

`4xx` da rota = erro permanente (arquivo ausente/corrompido); o worker não
reagenda.

O ciclo de vida do documento no Mongo (`recebido → processando → extraido` /
`erro`) é a fonte da verdade do progresso. O frontend faz *polling* de
`GET /documents/documentos/{id}` e oferece "tentar de novo"
(`POST .../{id}/reprocessar`) quando o estado é `erro`.

## Consequências

**A favor**

- Um único lugar com o pipeline de extração. Nenhuma cópia para divergir.
- `worker` continua uma imagem magra (`celery`, `redis`, `httpx`, `structlog`) —
  sem Tesseract, sem Poppler, sem SDK do Gemini.
- Retentativa, recuo e fila morta ficam no Celery, que é onde esse tipo de
  política pertence; a regra fiscal fica no `documents`.
- O ganho que a US-18 mede — p95 do upload de 6 s para < 500 ms — não depende de
  **onde** o CPU do OCR roda, só de **não ser na requisição do usuário**. Roda
  num processo do `documents` acionado pela fila, não no que atende o `/upload`.

**Contra**

- Um salto HTTP `worker → documents` que o desenho original não tinha. É
  chamada de um executor para o serviço dono do domínio, não acoplamento
  produtor/consumidor — mas ainda é uma dependência de runtime a mais.
- O trabalho de CPU do OCR roda num pod de `documents`. Sob carga alta de
  upload, escalar `documents` passa a atender também a fila. Aceitável na escala
  do TG; se um dia doer, a rota interna é o ponto de corte natural para mover o
  pipeline para o worker (a cópia dos módulos passa a valer a pena).
- Diverge do diagrama da arquitetura, que foi atualizado para refletir esta
  decisão.

## Alternativas descartadas

**Worker executa o pipeline (o desenho original).** Descartado pelo custo de
manter o pipeline duplicado e sincronizado entre dois serviços, sendo ele a
parte de maior churn do sistema. A regra do monorepo permite a cópia, mas cada
cópia é dívida.

**Pacote Python compartilhado com o pipeline.** Resolveria a duplicação, mas
introduz acoplamento de versão entre `documents` e `worker` e contraria a
decisão de não ter pacote compartilhado (raiz do `CLAUDE.md`).

**Sem rota interna: o worker importa `documents.app` como biblioteca.** Traz
junto o FastAPI, o lifespan, os clientes — e amarra o worker ao processo de
build do `documents`. Pior dos dois mundos.
