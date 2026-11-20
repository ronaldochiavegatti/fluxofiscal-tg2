# FiscalFlow Backend (Demo)

Backend em microsserviços para demonstrar um assistente fiscal de MEI (limites, documentos, billing e chat com LLM). A autenticação está propositalmente simplificada para fins de demo.

## Arquitetura
- **API Gateway (Nginx)**: expõe `http://localhost:8000` e roteia para os serviços (`/auth`, `/billing`, `/documents`, `/limits`, `/agent`).
- **Auth (FastAPI + Postgres)**: cadastro/login básico com senha hash (sem JWT).
- **Billing (FastAPI + Postgres)**: gerencia assinaturas e status ativo/inativo.
- **Limits (FastAPI + Postgres)**: registra transações e calcula resumo anual do MEI (teto fixo R$81.000,00).
- **Documents (FastAPI)**: upload com OCR (pytesseract/pdf2image) e extração estruturada. O upload só extrai e devolve; quem registra a transação no Limits é o `POST /confirm`, depois de o usuário revisar.
- **Agent Orchestrator (FastAPI + Gemini)**: recebe mensagem do usuário, busca o resumo no Limits, monta prompt e chama Gemini (fallback se a chave não estiver configurada).
- **Insights (FastAPI + Postgres)**: modelo de leitura (CQRS) para o dashboard e o motor de ritmo — ADR-0009. Esqueleto na preparação da Onda 3; as projeções entram na US-23.
- **Worker (Celery + Redis)**: executor de tarefas em segundo plano (OCR, LLM, manutenção) — ADR-0003. Esqueleto na preparação da Onda 3.
- **Frontend (React + Vite)**: SPA demo com login fake, dashboard com dados reais do Limits, upload com OCR, chat com IA e listagem mock de documentos.

Infraestrutura da Onda 3 (ADRs 0003–0006, 0009): **Redis** (broker Celery, cache,
Streams), **MinIO** (armazenamento de objetos S3, console em `:9001`), **MongoDB**
(metadados de documentos e trilha de auditoria). Sobem no Compose padrão e ficam
saudáveis; a lógica que os usa entra nas US-18 a US-23.

## Pré-requisitos
- Docker e Docker Compose.
- Arquivo `.env` na raiz (já existe um exemplo). Variáveis usadas:
  - `GEMINI_API_KEY` (opcional; se não definida, o agente responde em modo demo).
  - `GEMINI_MODEL` (padrão `gemini-3.5-flash-lite`).
  - `BILLING_TOKENS_ILIMITADOS` (padrão `true` no compose): saldo de tokens nunca
    bloqueia nem é debitado — modo da demo. Use `false` para exercitar a cobrança.
  - `MINIO_KMS_SECRET_KEY`: chave de KMS do MinIO para a criptografia em repouso
    (SSE-S3). Vazia, o compose usa uma chave de desenvolvimento **pública**:
    serve só para a pilha local; fora dela, gere uma própria.

## Subindo o ambiente
```bash
docker compose up -d --build
```
- Gateway: `http://localhost:8000`
- Frontend: `http://localhost:3000` (usa `VITE_API_BASE_URL`, padrão `http://localhost:8000`)
- Healthchecks: `/<service>/health` (ex.: `http://localhost:8000/auth/health`)
- Dados persistidos em volumes Docker (`*_db_data`, `documents_data`).
- Prometheus: `http://localhost:9090` (métricas RED e de negócio — US-10, US-11).
- Unleash (feature flags): `http://localhost:4242` (US-15). Sem `depends_on` de
  nenhum serviço — a indisponibilidade dele nunca atrasa nem derruba a subida
  (ADR-0008). Inventário de flags: [`docs/feature-flags.yaml`](../docs/feature-flags.yaml).

### Observabilidade completa (opcional)
A pilha de rastreamento distribuído (OpenTelemetry Collector, Tempo, Loki,
Promtail, Grafana) fica num overlay separado — não sobe no Compose padrão:
```bash
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d --build
```
- Grafana: `http://localhost:3001` — datasources e dashboards já provisionados,
  com salto painel → rastro → log. Ver [`docs/observabilidade`](../docs/observabilidade/README.md).

## Rotas principais (via Gateway)
- **Auth**
  - `POST /auth/users` — cria usuário `{email, password}`
  - `GET /auth/users` — lista usuários
  - `POST /auth/login` — login básico (retorna mensagem, sem token)
- **Billing**
  - `POST /billing/subscriptions` — cria assinatura `{email, plan?}`
  - `GET /billing/subscriptions/{id}` — consulta assinatura
- **Limits**
  - `POST /limits/transactions` — registra transação `{email, amount, tx_date, source?}`
  - `GET /limits/summary/{email}?year=` — resumo anual do MEI
  - `GET /limits/transactions?email=...&year=&month=` — lista transações filtradas (para dashboard mensal)
- **Documents**
  - `POST /documents/upload` — multipart: `file` + `email`; salva o arquivo, roda OCR e devolve os campos extraídos para revisão
  - `POST /documents/confirm` — registra no Limits o que o usuário confirmou e indexa o texto no RAG
- **Agent**
  - `POST /agent/chat` — `{email, message}`; busca resumo no Limits e responde com Gemini/fallback

## Fluxo típico
1. Criar usuário (opcional para demo).
2. Registrar transações manualmente via Limits **ou** enviar um documento pelo Documents, revisar os campos extraídos e confirmar.
3. Consultar resumo em `/limits/summary/{email}`.
4. Conversar com o agente em `/agent/chat` para receber orientações com base no resumo.

## Exemplos rápidos
Registrar transação manual:
```bash
curl -X POST http://localhost:8000/limits/transactions \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@mei.com","amount":1234.56,"tx_date":"2024-08-10","source":"manual"}'
```

Resumo anual:
```bash
curl http://localhost:8000/limits/summary/demo@mei.com
```

Upload de nota (gera transação automática):
```bash
curl -X POST http://localhost:8000/documents/upload \
  -F "email=demo@mei.com" \
  -F "file=@nf_teste.txt"
```

Chat com o agente:
```bash
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@mei.com","message":"Quanto ainda posso faturar este ano?"}'
```

## Testes

Suíte automatizada e roteiro manual em [`TESTING.md`](TESTING.md).

## Observações
- Autenticação é apenas login por senha hash; não há JWT nem autorização entre serviços.
- O OCR usa pytesseract/pdf2image; em ambiente Docker, as dependências de sistema precisam estar presentes (imagem da pasta `documents` já inclui).
- O agente cai em modo demo se `GEMINI_API_KEY` não estiver setada.
