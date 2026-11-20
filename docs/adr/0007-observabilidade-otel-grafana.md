# ADR-0007 — Observabilidade com OpenTelemetry e pilha Grafana

- **Data:** 2026-08-22
- **Estado:** Aceita

## Contexto

A plataforma tem seis serviços conversando entre si e nenhuma forma de observar
esse tráfego. O `auth` roda SQLAlchemy com `echo=True`, despejando SQL cru no
stdout; os demais não logam quase nada. Não há métrica, não há rastro
distribuído, não há painel.

Na prática isso significa que perguntas básicas de operação não têm resposta:
quanto tempo o Gemini realmente leva, qual serviço causou a lentidão de um
chat, quantos documentos caíram no caminho de contingência por regex em vez do
Gemini, quanto o projeto está gastando de token por dia.

Essa lacuna é também acadêmica. Dragoni et al. (2017), citado na fundamentação
do artigo, aponta observabilidade como um dos desafios centrais de
microsserviços. O artigo promete "logs centralizados e monitoramento via
Prometheus e Grafana" como etapa futura, e a seção de resultados precisa de
números de latência e escalabilidade que só existem se houver instrumentação.

## Decisão

Adotar **OpenTelemetry** como camada única de instrumentação — métricas, rastros
e logs saindo do mesmo SDK — exportando para um **OpenTelemetry Collector** que
distribui para a pilha Grafana:

| Sinal | Destino | Retenção |
| --- | --- | --- |
| Métricas | Prometheus | 30 dias |
| Rastros | Tempo | 7 dias |
| Logs | Loki | 14 dias |
| Painéis | Grafana | — |
| Alertas | Alertmanager | — |

Instrumentação automática de FastAPI, SQLAlchemy, httpx, Celery, Redis e
PyMongo, mais instrumentação manual nos pontos que só o domínio conhece:
chamada ao Gemini, busca vetorial no pgvector, execução do Tesseract.

**Três camadas de métricas**, porque cada uma responde a um público diferente:

1. **RED por serviço** — taxa de requisições, taxa de erro e distribuição de
   duração. Responde "o sistema está de pé".
2. **Recursos** — profundidade de fila, latência do banco, uso de conexões,
   memória. Responde "o que está apertando".
3. **Negócio** — documentos processados por método de extração, confiança média
   da extração, tokens de LLM consumidos e custo estimado em reais, razão de uso
   do limite do MEI por faixa, alertas disparados por nível. Responde "a
   plataforma está entregando valor".

**Correlação entre os três sinais.** O API Gateway gera um identificador de
correlação por requisição e o propaga no padrão W3C Trace Context. Todo log sai
em JSON estruturado carregando `trace_id` e `span_id`, o que permite saltar de
um pico no painel para o rastro exato e daí para as linhas de log daquela
requisição — dentro do Grafana, sem trocar de ferramenta.

**SLOs formais** ficam declarados em `docs/observabilidade/slos.yaml`, com
alertas de queima de orçamento de erro em janelas múltiplas (5 min com 1 h, e
30 min com 6 h), na forma recomendada pelo *Site Reliability Workbook*. Isso
evita tanto o alerta que dispara por ruído quanto o que só dispara tarde demais.

**Testes de carga com k6** produzem os números de escalabilidade do artigo, e o
mesmo arquivo de SLO serve de critério de aprovação da carga.

## Consequências

**A favor**

- A seção de resultados do artigo ganha dados medidos, com metodologia
  reprodutível, em vez de estimativas.
- O rastro distribuído torna o fluxo assíncrono do ADR-0006 depurável.
- Métricas de negócio como custo de token por usuário conectam engenharia e o
  modelo de faturamento que o artigo defende.
- OpenTelemetry é padrão aberto: trocar Prometheus por outro destino depois não
  exige reinstrumentar o código.

**Contra**

- Seis contêineres a mais no Compose. Isolados em um
  `docker-compose.observability.yml` separado, ativável por perfil, para que
  quem só quer rodar a aplicação não pague esse custo.
- Instrumentação tem custo de execução. Amostragem de rastros configurável, em
  100% no desenvolvimento e reduzida sob carga.
- Curva de aprendizado real de PromQL e LogQL. Mitigada entregando painéis
  prontos versionados como código.

## Alternativas descartadas

**Só Prometheus e Grafana**, sem rastros nem logs centralizados. É o mínimo que
o artigo promete e teria menor custo. Descartado porque métricas sozinhas não
respondem "por que este chat demorou 20 segundos" — e essa é justamente a
pergunta que um sistema com chamadas encadeadas a LLM precisa responder.

**Serviço gerenciado (Datadog, New Relic, Grafana Cloud).** Menos trabalho de
operação, mas custo recorrente e dependência de conta externa num trabalho que
precisa rodar offline na avaliação.

**Elastic Stack.** Excelente para logs, mais pesado em memória e com integração
menos natural com Prometheus e OpenTelemetry.

## Referências

- Beyer, B. et al. *The Site Reliability Workbook*, 2018, cap. 5 (alertas por
  queima de orçamento de erro).
- Dragoni, N. et al. *Microservices: Yesterday, Today, and Tomorrow*, 2017.
- Especificação OpenTelemetry e convenções semânticas de atributos.
