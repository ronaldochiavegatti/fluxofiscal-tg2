# Contratos entre serviços

Verificação de contrato da **US-47** (Onda 3). Quebra de contrato entre serviços
aparece no PR, não em execução.

## Peças

| Arquivo | O quê |
| --- | --- |
| `snapshots/<servico>.openapi.json` | OpenAPI publicado por cada serviço, congelado. Gerado de `app.openapi()`, sem subir o serviço. |
| `extrair.py` | Roda de dentro de `app/services/<servico>/` (com `PYTHONPATH=.`) e escreve o `app.openapi()` atual num arquivo. |
| `verificar.py` | Compara o OpenAPI atual com o snapshot e **reprova** quando some rota, operação ou campo de resposta `2xx`. Adicionar é compatível. A mensagem de erro lista os consumidores do serviço. |
| `consumidores.json` | Quem depende das respostas de cada serviço (HTTP síncrono de hoje + tabela de eventos do ADR-0006). |
| `eventos.py` | Contrato do envelope de eventos (ADR-0006): todo evento carrega `versao`; `ler_envelope` registra `WARNING` e ignora versão desconhecida sem quebrar. Base para a US-21. |
| `test_verificar.py`, `test_eventos.py` | Cobrem os dois cenários Gherkin da história. |

## Na CI

`.github/workflows/contratos.yml` roda em todo PR que toca `app/services/**` ou
`tools/contratos/**`:

- **`Contrato OpenAPI · <servico>`** (matriz) — instala o serviço, extrai o
  OpenAPI e compara com o snapshot.
- **`Contrato de eventos`** — `pytest tools/contratos/`.

## Quando o contrato muda de propósito

Se a quebra é intencional, alinhe com os consumidores e **regrave o snapshot no
mesmo PR** — ele entra no diff e passa pela revisão junto:

```bash
cd app/services/<servico>
PYTHONPATH=. python ../../../tools/contratos/extrair.py openapi-atual.json
python ../../../tools/contratos/verificar.py --servico <servico> \
  --atual openapi-atual.json --escrever
```

## Bootstrap dos snapshots

Enquanto `snapshots/<servico>.openapi.json` não existe, `verificar.py` o cria e
passa com `WARNING`. O workflow publica o OpenAPI atual de cada serviço como
artefato (`schema-<servico>`); baixe, mova para `snapshots/<servico>.openapi.json`
e comite no mesmo PR. O mesmo artefato serve para regravar um snapshot quando a
mudança de contrato é intencional.
