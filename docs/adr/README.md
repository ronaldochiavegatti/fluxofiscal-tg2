# Registros de Decisão Arquitetural (ADR)

Cada arquivo aqui congela **uma** decisão: o contexto em que ela foi tomada, a
opção escolhida, o que se ganha e o que se perde com ela, e quais alternativas
foram descartadas.

O objetivo é que, meses depois, ninguém precise reconstruir por arqueologia de
código a razão de uma escolha — nem o autor, nem a banca avaliadora, nem quem
vier manter a plataforma depois.

O formato segue a proposta de Michael Nygard (*Documenting Architecture
Decisions*, 2011).

## Estados possíveis

| Estado | Significado |
| --- | --- |
| `Proposta` | Em discussão, ainda não vale |
| `Aceita` | Em vigor, o código deve refletir isso |
| `Substituída por ADR-XXXX` | Continua no histórico, mas outra decisão passou por cima |
| `Descartada` | Foi considerada e recusada |

## Índice

| ADR | Decisão | Estado |
| --- | --- | --- |
| [0001](0001-monorepo-privado-no-github.md) | Monorepo privado no GitHub | Aceita |
| [0002](0002-trunk-based-e-conventional-commits.md) | Trunk-based development com Conventional Commits e SemVer | Aceita |
| [0003](0003-processamento-assincrono-redis-celery.md) | Processamento assíncrono com Redis e Celery | Aceita |
| [0004](0004-minio-como-object-storage.md) | MinIO como armazenamento de objetos | Aceita |
| [0005](0005-mongodb-para-metadados-e-auditoria.md) | MongoDB para metadados de documentos e trilha de auditoria | Aceita |
| [0006](0006-eventos-com-redis-streams-e-outbox.md) | Barramento de eventos com Redis Streams e padrão Outbox | Aceita |
| [0007](0007-observabilidade-otel-grafana.md) | Observabilidade com OpenTelemetry e pilha Grafana | Aceita |
| [0008](0008-unleash-para-feature-flags.md) | Unleash auto-hospedado para feature flags | Aceita |
| [0009](0009-servico-de-insights-com-cqrs.md) | Serviço de Insights com modelo de leitura (CQRS) | Aceita |
| [0010](0010-tailwind-e-recharts-no-frontend.md) | Tailwind CSS e Recharts no frontend | Aceita |
| [0011](0011-manter-autenticacao-simplificada.md) | Manter autenticação simplificada nesta fase | Aceita |
| [0012](0012-medicao-real-de-tokens-do-llm.md) | Medir tokens reais do LLM para o faturamento | Aceita |
| [0013](0013-piramide-de-testes-e-portoes.md) | Pirâmide de testes e portões de qualidade | Aceita |
| [0014](0014-entrega-continua-ate-o-ghcr.md) | Entrega contínua até o GHCR, deploy via Compose | Aceita |
| [0015](0015-camadas-anticorrupcao-nas-fronteiras.md) | Camadas anticorrupção nas fronteiras entre serviços | Aceita |
| [0016](0016-worker-orquestra-documents-processa.md) | O worker orquestra, o Documents processa (upload assíncrono) | Aceita |
| [0017](0017-trilha-de-auditoria-encadeada-por-hash.md) | Trilha de auditoria encadeada por hash | Aceita |
| [0018](0018-outbox-e-consumidor-em-processo.md) | Publicador e consumidor de eventos em processo | Aceita |
| [0019](0019-servico-de-notificacoes-e-banco-proprio.md) | Serviço de Notificações com banco próprio | Aceita |
| [0020](0020-ci-local-sem-github-actions.md) | Portões locais como fonte da verdade, sem GitHub Actions | Aceita |
| [0021](0021-cnpj-do-cliente-em-limits-para-concentracao.md) | CNPJ do cliente em Limits, para concentração de cliente | Aceita |
| [0022](0022-regras-fiscais-parametrizaveis-por-usuario.md) | Regras fiscais parametrizáveis por usuário | Aceita |
| [0023](0023-versoes-fixadas-e-modo-demo-do-billing.md) | Versões fixadas de dependências transitivas e modo demonstração do billing | Aceita |
| [0024](0024-registro-de-consumo-medido-no-billing.md) | Registro do consumo medido no billing, antes do débito proporcional | Aceita |

## Quando abrir um ADR novo

Abra quando a decisão for cara de reverter: troca de banco, novo serviço,
mudança de protocolo entre serviços, adoção de dependência estrutural,
alteração de um contrato público. Escolha de biblioteca pequena e localizada
não precisa de ADR — precisa de um comentário no código.
