# Testes

Duas coisas convivem neste arquivo: a **suíte automatizada**, que é o que a CI
executa e o que reprova um PR, e o **roteiro manual**, que continua útil para
conferir o ambiente com os olhos depois de subir o Compose.

O roteiro manual não substitui a suíte. Quando os dois discordarem, quem está
certo é a suíte — ela roda a cada PR, o roteiro roda quando alguém lembra.

---

## Suíte automatizada

### Executando

Não é preciso instalar Python na máquina: a imagem oficial serve.

```bash
# um serviço
docker run --rm -v "$PWD:/w" -w /w/app/services/limits python:3.12-slim sh -c '
  pip install -q -r requirements.txt -r ../../requirements-dev.txt &&
  pytest tests/ --cov=app --cov-report=term-missing'
```

Com Python 3.12 local, do diretório do serviço:

```bash
pip install -r requirements.txt -r ../../requirements-dev.txt
pytest                       # a suíte inteira
pytest -m "not integracao"   # sem Docker
pytest -m contrato           # só a verificação de contrato
```

### Onde estão

| Serviço | Testes | Cobertura |
| --- | --- | --- |
| `auth` | 23 | 100% |
| `billing` | 22 | 100% |
| `limits` | 77 | 98% |
| `documents` | 100 | 96% |
| `agent-orchestrator` | 43 | 93% |

O portão da CI exige **80% por serviço** e **95% no núcleo de domínio fiscal**
([ADR-0013](../docs/adr/0013-piramide-de-testes-e-portoes.md)). A suíte completa
roda em menos de um minuto e meio.

### Os quatro níveis

**Domínio** — `limits/tests/test_dominio_limites.py`. Sem banco, sem HTTP, sem
framework. É onde a regra fiscal do MEI é verificada, e roda em milissegundos.

**Rotas** — `test_api_*.py`. Cada serviço apontado para um SQLite em memória, com
o `lifespan` rodando como roda em produção. Rápido o bastante para executar a
cada salvamento.

**Integração** — `limits/tests/test_integracao_postgres.py`, marcado
`@pytest.mark.integracao`. Sobe um PostgreSQL 16 real com testcontainers, porque
SQLite não é PostgreSQL justamente onde importa: `func.extract` compila para
dialetos diferentes, e `Numeric(10, 2)` é decimal nativo lá e ponto flutuante
aqui. Sem Docker disponível, a suíte é pulada em vez de reprovar.

**Contrato** — `test_contrato_openapi.py`, marcado `@pytest.mark.contrato`. O
Schemathesis lê o `/openapi.json` que o próprio serviço publica, gera entradas
válidas para cada operação e cobra que nenhuma rota devolva 500 para entrada
válida nem responda fora do esquema declarado. É a única camada que não depende
da imaginação de quem escreveu o teste.

### Nenhum teste chama o Gemini

A suíte inteira roda sem `GEMINI_API_KEY`. Sem a chave, o cliente nasce `None` e
os serviços entram no caminho de contingência — que não é um artifício de teste:
é o que atende de verdade quando a cota acaba. Onde o caminho com modelo precisa
ser exercitado, o cliente é substituído por um duplo.

### O que a suíte encontrou

Escrever os testes revelou onze achados no protótipo, seis deles capazes de
devolver **500 em rota de usuário**:

| Onde | Defeito |
| --- | --- |
| `billing` | `orm_mode` é chave ignorada no Pydantic v2: as duas rotas de assinatura devolviam 500 |
| `billing` | `created_at` sem fuso violava o `format: date-time` que o próprio contrato declara |
| `limits` | `Query(default=datetime.utcnow().year)` congela o ano na importação do módulo |
| `limits` | valor acima de `Numeric(10, 2)` estourava no banco em vez de virar 422 |
| `limits` | `tx_id` e `year` sem borda estouravam o `int4` do PostgreSQL |
| `limits` | e-mail internacionalizado derrubava o `Content-Disposition`, que é latin-1 |
| `limits` | o OpenAPI prometia `application/json` numa rota que devolve PDF |
| `auth` | senha com byte nulo levantava exceção dentro do bcrypt |
| `documents` | foto corrompida ou PDF truncado derrubavam o upload |
| `documents` | a expressão de data exigia dois dígitos no dia, e o `zfill` nunca era alcançado |
| todos | status 400, 401, 404 e 502 devolvidos, mas ausentes do OpenAPI publicado |

Nenhum deles apareceria em teste manual: todos exigem entrada que ninguém digita
de propósito.

---

## Roteiro manual

Sobe o ambiente e confere pelo Gateway (`http://localhost:8000`):

```bash
cd app && cp .env.example .env && docker compose up -d --build --wait
```

Use `demo@mei.com`. Os arquivos de apoio para o fluxo de upload estão em
`docs_para_teste/`, com gabarito.

### Healthchecks

```bash
for s in auth billing documents limits agent; do
  curl -s http://localhost:8000/$s/health; echo
done
```

Cada um responde `{"status":"ok", ...}`. O `documents` informa ainda
`gemini_extraction`, e o `agent`, `rag_enabled` — é assim que se sabe, de fora,
se a plataforma está em modo demonstração.

### Auth

```bash
curl -X POST http://localhost:8000/auth/users \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@mei.com","password":"senha-de-demo"}'

curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@mei.com","password":"senha-de-demo"}'
```

201 no cadastro, 200 no login. Senha errada e usuário inexistente devolvem o
mesmo 401, de propósito.

### Billing

```bash
curl -X POST http://localhost:8000/billing/subscriptions \
  -H "Content-Type: application/json" -d '{"email":"demo@mei.com","plan":"pro"}'

curl http://localhost:8000/billing/tokens/demo@mei.com
curl -X POST http://localhost:8000/billing/tokens/consume \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@mei.com","reason":"chat_message"}'
```

Saldo inicial de 1000 tokens. Consumo insuficiente devolve `insufficient: true`
sem debitar nada.

### Limits

```bash
curl -X POST http://localhost:8000/limits/transactions \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@mei.com","amount":1500.00,"tx_date":"2026-08-01","tx_type":"venda"}'

curl http://localhost:8000/limits/summary/demo@mei.com
curl "http://localhost:8000/limits/transactions?email=demo@mei.com&year=2026&month=8"
curl -o relatorio.pdf http://localhost:8000/limits/report/demo@mei.com
```

No resumo, `total_revenue` soma apenas as vendas; compras entram em
`total_despesas` e não contam para o teto.

### Documents

```bash
curl -X POST http://localhost:8000/documents/upload \
  -F "email=demo@mei.com" -F "file=@nf_txt_demo.txt"
```

O upload **não grava nada**: ele extrai e devolve para o usuário revisar. Quem
persiste é o `/confirm`:

```bash
curl -X POST http://localhost:8000/documents/confirm \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@mei.com","amount":987.65,"tx_date":"2026-08-01","tx_type":"venda"}'

curl http://localhost:8000/limits/summary/demo@mei.com   # agora inclui o valor
```

### Agent

```bash
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@mei.com","message":"Quanto ainda posso faturar este ano?"}'
```

Resposta em português com o resumo do limite. Sem `GEMINI_API_KEY`, o serviço
responde em modo demonstração.

### Frontend

`http://localhost:3000` → “Entrar na Demo”. O dashboard lê os totais reais do
Limits; o upload usa `/documents/upload`; o chat usa `/agent/chat` com o
contexto do Limits.

### Validações que valem conferir

| Requisição | Esperado |
| --- | --- |
| `tx_type` fora de `venda`/`compra` | 400 |
| `amount` acima de 99.999.999,99 | 422 |
| `year` fora de 2000–2100 | 422 |
| e-mail malformado em qualquer rota | 422 |
| assinatura ou transação inexistente | 404 |
| Limits fora do ar, consultado pelo Agent | 502 |
