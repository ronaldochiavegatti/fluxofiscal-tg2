# ADR-0023 — Versões fixadas de dependências transitivas e modo demonstração do billing

- **Data:** 2026-11-15
- **Estado:** Aceita
- **Issue:** #86 (preparação da apresentação)

## Contexto

Ao subir a pilha inteira para ensaiar a apresentação, três problemas
apareceram sem que nenhuma linha de código nosso tivesse mudado:

1. **`yggdrasil-engine` 2.0**, dependência transitiva do `UnleashClient` 6.8,
   mudou a ABI usada pelo SDK. `count_toggle` passou a levantar
   `ctypes.ArgumentError`, e toda flag caía no padrão seguro, em todos os
   serviços.
2. **`kombu` 5.7**, transitiva do Celery, passou a exigir redis-py >= 6.1. Com
   o `redis` 5.2 fixado no worker, a conexão falhava com `VersionMismatch`.
3. O saldo inicial de 1.000 tokens acabava no meio do roteiro da demonstração
   e bloqueava upload e chat.

Os dois primeiros não acrescentam dependência nova: mudam o que já era
instalado sem versão fixa.

## Decisão

1. **Fixar as transitivas que quebraram**, no `requirements.txt` de cada
   serviço que as usa, com um comentário dizendo por quê e o que destrava a
   remoção:
   - `yggdrasil-engine==1.3.1` em todos os serviços com `UnleashClient`, até
     subir o SDK do Unleash para uma versão compatível com a 2.0;
   - `kombu==5.4.2` no documents e no worker, até subir o `redis`.
2. **Modo demonstração do billing** (`BILLING_TOKENS_ILIMITADOS`): ligado, o
   saldo nunca bloqueia nem é debitado, mas o consumo continua registrado em
   log (`tokens.consumidos_demo`), e as respostas trazem `ilimitado: true`.
   O `docker-compose.yml` da pilha local liga o modo por padrão; para
   exercitar a cobrança, sobe-se com `BILLING_TOKENS_ILIMITADOS=false`.

## Consequências

- O comportamento volta a ser o esperado sem trocar de versão de nenhuma
  dependência direta. O custo é a dívida de desfazer os pins quando o SDK do
  Unleash e o `redis` forem atualizados; os comentários marcam onde.
- Na pilha local, o saldo de tokens deixa de ser um teste da cobrança. A
  contabilização por ação segue observável pelo log, e a suíte do billing
  cobre os dois modos.
- O modo demonstração não pode ir para um ambiente com usuários reais. Fora
  da pilha local, a variável não tem padrão: ausente, a cobrança vale.
