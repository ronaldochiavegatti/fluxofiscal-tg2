# FluxoFiscal — TG II · ADS FATEC · Ronaldo Chiavegatti

Plataforma SaaS em microsserviços com agentes de IA verticalizados. Como prova
de conceito, um agente contábil para Microempreendedores Individuais que lê
notas fiscais por OCR, extrai dados com LLM multimodal, acompanha o limite anual
do MEI e responde dúvidas fiscais por RAG.

Este repositório contém a aplicação, a infraestrutura, a documentação de
engenharia e o material de avaliação do Trabalho de Graduação II. É a cópia
pública da versão entregue (tag `tg2-entrega-2026-11`), sem histórico de
desenvolvimento; o texto do artigo é entregue à parte.

> **Atenção — modo demonstração.** A autenticação está deliberadamente
> simplificada: **todos os endpoints são públicos e a identidade é
> autodeclarada**. Não exponha esta aplicação em endereço público e não envie
> documentos com dados reais de terceiros. A decisão, com seu critério de
> revisão, está registrada no [ADR-0011](docs/adr/0011-manter-autenticacao-simplificada.md).

---

## Estrutura

```
TG 2/
├── docs/                       Documentação de engenharia
│   ├── PLANO.md                Diagnóstico, roadmap por ondas, medição
│   ├── BACKLOG.md              56 histórias de usuário com Gherkin
│   ├── arquitetura/            Arquitetura alvo e contextos delimitados
│   ├── adr/                    14 decisões arquiteturais registradas
│   ├── dashboard-v2.md         Dashboard e motor de ritmo de vendas
│   ├── contexto-do-agente.md   Janela de contexto, memória e RAG
│   ├── observabilidade/        Telemetria, painéis e SLOs
│   ├── feature-flags.yaml      Inventário de flags, auditado pela CI
│   ├── versionamento.md        Ramos, commits, tags, rastreabilidade
│   └── IMPACTO-ARTIGO.md       O que muda em cada seção do artigo
├── app/                        Aplicação
│   ├── services/               Sete serviços containerizados
│   ├── docker-compose.yml      Ambiente de desenvolvimento
│   ├── docker-compose.release.yml  Demonstração com imagens do GHCR
│   ├── requirements-dev.txt    Ferramentas de teste dos cinco serviços
│   ├── TESTING.md              Suíte automatizada e roteiro manual
│   └── .env.example
├── tools/                      Auditor de flags e coletor DORA
├── .githooks/                  commit-msg e pre-push versionados
├── docs_para_teste/            Documentos sintéticos com gabarito
└── CONTRIBUTING.md             Guia de contribuição
```

---

## Executando

Só é preciso Docker. Python e Node rodam dentro dos contêineres.

```bash
cd app
cp .env.example .env
docker compose up -d --build
```

| Endereço | O quê |
| --- | --- |
| http://localhost:3000 | Frontend |
| http://localhost:8000 | API Gateway |

```bash
# verificando
for s in auth billing documents limits agent; do
  curl -s http://localhost:8000/$s/health; echo
done
```

Cada um deve responder `{"status":"ok", ...}`.

**Sem `GEMINI_API_KEY`** a plataforma sobe em modo demonstração: o OCR do
Tesseract funciona, a extração cai para o caminho por expressões regulares e o
agente responde sem chamar o modelo. Nada quebra — é assim que a CI executa.

**Com a chave**, a extração multimodal e o RAG operam de verdade. Obtenha uma em
[aistudio.google.com](https://aistudio.google.com/apikey) e preencha o `.env` —
que está no `.gitignore` e nunca deve ser versionado.

```bash
docker compose logs -f agent    # acompanhar um serviço
docker compose down             # parar
docker compose down -v          # parar e apagar os dados
```

---

## Experimentando

```bash
# 1. criar um usuário
curl -X POST http://localhost:8000/auth/users \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@mei.com","password":"123456"}'

# 2. enviar uma nota fiscal — extrai e devolve para revisão, sem gravar
curl -X POST http://localhost:8000/documents/upload \
  -F "email=demo@mei.com" -F "file=@nf_txt_demo.txt"

# 3. confirmar o que foi extraído: é aqui que a transação é registrada
curl -X POST http://localhost:8000/documents/confirm \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@mei.com","amount":987.65,"tx_date":"2026-08-01","tx_type":"venda"}'

# 4. consultar o limite anual
curl http://localhost:8000/limits/summary/demo@mei.com

# 5. conversar com o agente
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@mei.com","message":"Quanto ainda posso faturar este ano?"}'
```

Ou acesse http://localhost:3000 e use a interface. Roteiro manual completo em
[`app/TESTING.md`](app/TESTING.md).

---

## Testes

265 testes automatizados, em quatro níveis: domínio puro, rotas contra SQLite em
memória, integração contra um PostgreSQL 16 real via testcontainers, e
verificação de contrato contra o OpenAPI que cada serviço publica. A suíte
inteira roda em menos de um minuto e meio, e **sem chamar a API do Gemini** —
sem chave, os serviços entram no caminho de contingência, que é o que a suíte
exercita.

```bash
docker run --rm -v "$PWD:/w" -w /w/app/services/limits python:3.12-slim sh -c '
  pip install -q -r requirements.txt -r ../../requirements-dev.txt &&
  pytest tests/ --cov=app --cov-report=term-missing'
```

| Serviço | Testes | Cobertura |
| --- | --- | --- |
| `auth` | 23 | 100% |
| `billing` | 22 | 100% |
| `limits` | 77 | 98% |
| `documents` | 100 | 96% |
| `agent-orchestrator` | 43 | 93% |

O frontend tem suíte própria, em Vitest com Testing Library, junto com `tsc` e
ESLint bloqueantes — `npm run test:cov` no diretório do serviço.

O portão da CI exige 80% por serviço e 95% no núcleo de domínio fiscal. Detalhes
dos quatro níveis, e a lista dos onze achados que escrever a suíte revelou, em
[`app/TESTING.md`](app/TESTING.md).

---

## Arquitetura

Sete serviços atrás de um API Gateway NGINX, cada um com seu próprio banco.

| Serviço | Responsabilidade | Estado |
| --- | --- | --- |
| `auth` | Cadastro e login | implementado (sem JWT) |
| `limits` | Transações e limite anual do MEI — fonte da verdade fiscal | implementado |
| `documents` | Upload, OCR e extração estruturada | implementado |
| `agent-orchestrator` | RAG com pgvector e chat com Gemini | implementado |
| `billing` | Créditos e consumo | implementado (custo fixo) |
| `api-gateway` | Roteamento e ponto único de entrada | implementado |
| `insights` | Projeções, ritmo de vendas e alertas | planejado (Onda 3) |
| `notifications` | Feed de notificações in-app | planejado (Onda 4) |
| `worker` | OCR e embeddings em segundo plano | planejado (Onda 3) |

Desenho alvo, contextos delimitados e diagramas de sequência em
[`docs/arquitetura/README.md`](docs/arquitetura/README.md).

---

## Para onde o projeto vai

O plano de evolução está em [`docs/PLANO.md`](docs/PLANO.md), organizado em oito
ondas de valor. Cada onda termina em algo demonstrável e produz evidência
utilizável no artigo.

| Onda | Entrega |
| --- | --- |
| 0 | Testes, CI/CD, núcleo de domínio isolado |
| 1 | Observabilidade, SLOs, testes de carga |
| 2 | Feature flags com Unleash |
| 3 | Processamento assíncrono, MinIO, MongoDB, eventos |
| 4 | Dashboard v2 e motor de ritmo de vendas |
| 5 | Controles de gestão do MEI |
| 6 | Engenharia de contexto do agente |
| 7 | Privacidade, LGPD e fechamento |

---

## Contribuindo

Leia [`CONTRIBUTING.md`](CONTRIBUTING.md). Ao clonar, ative os hooks do projeto
com `git config core.hooksPath .githooks`. Em resumo: ramo curto a partir da
`main`, commits no padrão Conventional Commits, PR com a CI verde, mudança
arriscada atrás de feature flag.

## Direitos

Copyright (c) 2026 Centro Estadual de Educação Tecnológica Paula Souza
(CEETEPS) — Fatec Rio Preto. Todos os direitos reservados. O código é público
só para consulta e verificação acadêmica do Trabalho de Graduação II; veja
[LICENSE](LICENSE).
