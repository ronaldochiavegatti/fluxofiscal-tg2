# Como contribuir

Guia operacional do dia a dia. As decisões por trás destas regras estão nos
[ADRs](docs/adr/README.md); o detalhe do versionamento está em
[`docs/versionamento.md`](docs/versionamento.md).

---

## Ambiente

Ao clonar, **ative os hooks do projeto** — eles não vêm ativos por padrão,
porque o Git não versiona `.git/hooks`:

```bash
git config core.hooksPath .githooks
```

Isso liga duas verificações locais: `commit-msg` valida a mensagem contra
Conventional Commits, e `pre-push` recusa push direto na `main`. Proteção de
ramo no servidor exige GitHub Pro em repositório privado, então esses hooks
fazem parte do papel dela — com as limitações descritas em
[`docs/versionamento.md`](docs/versionamento.md).

```bash
cd app
cp .env.example .env          # preencha GEMINI_API_KEY se for usar a IA real
docker compose up -d --build

# com a pilha de observabilidade
docker compose --profile observability up -d
```

| Endereço | O quê |
| --- | --- |
| http://localhost:3000 | Frontend |
| http://localhost:8000 | API Gateway |
| http://localhost:3001 | Grafana |
| http://localhost:4242 | Unleash |
| http://localhost:9001 | Console do MinIO |

Sem `GEMINI_API_KEY` a plataforma funciona em modo demonstração: nada quebra, e
os caminhos de contingência são exercitados. É assim que a CI roda.

---

## Ciclo de uma história

```bash
git switch main && git pull
git switch -c feat/42-gauge-limite-anual
# ... trabalho, com commits pequenos ...
git push -u origin feat/42-gauge-limite-anual
gh pr create --fill
```

Ramo vive no máximo 72 horas. Se está passando disso, a história é grande demais
— quebre a história, não estenda o ramo.

---

## Antes de abrir o PR

```bash
# backend
cd app/services/<servico>
ruff check app/ && ruff format app/
mypy app/ --ignore-missing-imports
pytest tests/ --cov=app --cov-report=term-missing

# frontend
cd app/services/frontend
npx tsc --noEmit && npx eslint src && npm test

# o ambiente ainda sobe?
cd app && docker compose up -d --build --wait
```

---

## Regras que a CI verifica

1. Título do PR em [Conventional Commits](https://www.conventionalcommits.org/pt-br/)
2. Nenhum segredo no diff (gitleaks)
3. Lint e formatação sem violação
4. Cobertura acima do mínimo do serviço
5. Contratos em conformidade com o OpenAPI declarado
6. O `docker compose` sobe e os healthchecks respondem
7. Nenhuma vulnerabilidade crítica ou alta com correção disponível
8. Toda flag usada está declarada em `docs/feature-flags.yaml`

---

## Ao criar uma rota nova

Quatro coisas, sempre:

```python
@router.get("/recurso/{id}")
async def obter_recurso(
    id: str,
    usuario: Usuario = Depends(obter_usuario_atual),   # 1. identidade por dependência
) -> RecursoOut:
    with tracer.start_as_current_span("recurso.obter"):  # 2. span nomeado
        logger.info("recurso.consultado", extra={"recurso_id": id})  # 3. log estruturado
        ...
```

4. Métrica: vem automática da instrumentação do FastAPI, **desde que a rota use
   parâmetro de caminho** (`/recurso/{id}`, nunca caminho concreto). Caso
   contrário, cada valor vira uma série temporal nova.

O item 1 merece explicação: a autenticação está simplificada nesta fase
([ADR-0011](docs/adr/0011-manter-autenticacao-simplificada.md)) e a dependência
hoje só lê o e-mail do parâmetro. Usá-la assim mesmo é o que fará a introdução de
JWT depois ser uma mudança em um arquivo, e não em trinta rotas.

---

## Ao criar uma feature flag

1. Declare em `docs/feature-flags.yaml`, com dono, tipo e **data de remoção**
2. Crie no Unleash com o mesmo nome
3. No código, o valor padrão é **sempre** o comportamento antigo:

```python
if flags.esta_ativa("dashboard-v2", contexto, padrao=False):
    return novo_comportamento()
return comportamento_atual()
```

4. Teste os dois caminhos
5. Abra a issue de remoção já com a data

Flag sem data de remoção é código com dois caminhos vivos para sempre.

---

## Ao mudar regra fiscal

Regra do MEI mora em `dominio/` e em nenhum outro lugar. Se você precisou
duplicar uma verificação no frontend, isso é sinal de que falta um endpoint.

```bash
pytest tests/dominio/ -v
mutmut run --paths-to-mutate dominio/    # antes de considerar pronto
```

Cobertura diz que a linha rodou. Mutação diz se o teste notaria caso ela
estivesse errada. Para cálculo fiscal, a segunda pergunta é a que importa.

---

## O que nunca fazer

- Versionar `.env`, chave de API ou dado pessoal real
- Registrar em log e-mail sem hash, CNPJ sem máscara ou texto de OCR
- Usar caminho concreto como rótulo de métrica
- Fazer push direto na `main`
- Adicionar dependência estrutural sem ADR
- Deixar `except Exception: pass` sem registrar nada
