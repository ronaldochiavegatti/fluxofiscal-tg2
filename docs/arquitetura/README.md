# Arquitetura alvo

Este documento descreve para onde a plataforma vai. O estado atual está
descrito na seção "De onde partimos"; as decisões que produziram o desenho alvo
estão nos [ADRs](../adr/README.md).

---

## 1. De onde partimos

Seis serviços, comunicação exclusivamente síncrona, cada chamada conhecendo o
endereço do destino.

```mermaid
flowchart LR
    U["Navegador"] --> GW["API Gateway<br/>NGINX"]
    GW --> AU["auth"]
    GW --> BI["billing"]
    GW --> LI["limits"]
    GW --> DO["documents"]
    GW --> AG["agent-orchestrator"]

    AU --- AUDB[("auth_db")]
    BI --- BIDB[("billing_db")]
    LI --- LIDB[("limits_db")]
    AG --- AGDB[("agent_db<br/>pgvector")]
    DO --- VOL[["volume local<br/>/data/uploads"]]

    DO -->|"POST /transactions"| LI
    DO -->|"POST /index-document"| AG
    AG -->|"GET /summary"| LI
    DO --> GEM(["API Gemini"])
    AG --> GEM

    classDef externo fill:#1e293b,stroke:#64748b,color:#e2e8f0
    class GEM externo
```

**O que dói neste desenho**

| Problema | Onde aparece | Consequência |
| --- | --- | --- |
| OCR e LLM dentro da requisição HTTP | `documents/app/main.py` | 4,5 s por upload, worker bloqueado |
| Falha silenciosa na indexação | `except httpx.RequestError: pass` | Documento confirmado que nunca chega ao RAG |
| Arquivo em volume local | `UPLOAD_DIR = Path("/data/uploads")` | Serviço não replica, sem criptografia, sem retenção |
| Nenhum metadado persistido | Documents não tem banco | Reprocessar custa API de novo; lista vive no `localStorage` |
| Zero observabilidade | Todos | Nenhuma pergunta operacional tem resposta |
| Cálculo analítico no navegador | `DashboardPage.tsx` | Regra fiscal espalhada pela camada de apresentação |

---

## 2. Para onde vamos

```mermaid
flowchart TB
    U["Navegador<br/>React + Tailwind + Recharts"]
    U --> GW["API Gateway (NGINX)<br/>correlation-id, roteamento, limite de taxa"]

    subgraph sinc["Plano síncrono — o usuário está esperando"]
        AU["auth"]
        BI["billing<br/>medição real de tokens"]
        LI["limits<br/>fonte da verdade fiscal"]
        DO["documents<br/>responde 202 Accepted"]
        AG["agent-orchestrator<br/>montagem de contexto + RAG"]
        IN["insights<br/>projeções e ritmo"]
        NO["notifications<br/>feed in-app"]
    end

    GW --> AU & BI & LI & DO & AG & IN & NO

    subgraph assinc["Plano assíncrono — trabalho em segundo plano"]
        WK["worker Celery<br/>filas: ocr, llm, manutencao"]
        BUS{{"Redis Streams<br/>barramento de eventos"}}
    end

    DO -->|enfileira| WK
    WK -->|publica| BUS
    LI -->|outbox| BUS
    BI -->|outbox| BUS
    IN -->|publica alerta| BUS
    BUS -->|consome| IN
    BUS -->|consome| NO
    BUS -->|consome| AG
    BUS -->|consome| AUD["auditoria"]

    subgraph dados["Persistência"]
        AUDB[("PostgreSQL<br/>auth")]
        BIDB[("PostgreSQL<br/>billing")]
        LIDB[("PostgreSQL<br/>limits + outbox")]
        INDB[("PostgreSQL<br/>projeções")]
        AGDB[("PostgreSQL + pgvector<br/>embeddings + conversas")]
        MG[("MongoDB<br/>documentos + auditoria")]
        MN[["MinIO<br/>arquivos originais"]]
        RD[("Redis<br/>broker, cache, streams")]
    end

    AU --- AUDB
    BI --- BIDB
    LI --- LIDB
    IN --- INDB
    AG --- AGDB
    DO --- MG
    NO --- MG
    DO --- MN
    WK --- MN
    WK --- RD

    subgraph plataforma["Plataforma"]
        UN["Unleash<br/>feature flags"]
        OT["OpenTelemetry Collector"]
        PR["Prometheus"]
        TE["Tempo"]
        LO["Loki"]
        GR["Grafana"]
        AM["Alertmanager"]
    end

    sinc -.telemetria.-> OT
    assinc -.telemetria.-> OT
    OT --> PR & TE & LO
    PR & TE & LO --> GR
    PR --> AM
    sinc -.avalia flag.-> UN

    GEM(["API Gemini<br/>extração, embeddings, chat"])
    WK --> GEM
    AG --> GEM
```

### O que muda, em uma frase cada

| Mudança | ADR |
| --- | --- |
| Upload responde em milissegundos; OCR e LLM vão para fila Celery | [0003](../adr/0003-processamento-assincrono-redis-celery.md) |
| Arquivos saem do volume local e vão para o MinIO, com URL pré-assinada | [0004](../adr/0004-minio-como-object-storage.md) |
| Documentos e auditoria passam a ser persistidos no MongoDB | [0005](../adr/0005-mongodb-para-metadados-e-auditoria.md) |
| Serviços passam a conversar por eventos, com Outbox garantindo a publicação | [0006](../adr/0006-eventos-com-redis-streams-e-outbox.md) |
| Toda requisição vira métrica, rastro e log correlacionados | [0007](../adr/0007-observabilidade-otel-grafana.md) |
| Mudança arriscada nasce atrás de flag reversível em um clique | [0008](../adr/0008-unleash-para-feature-flags.md) |
| Cálculo analítico sai do navegador e vira modelo de leitura | [0009](../adr/0009-servico-de-insights-com-cqrs.md) |
| Cobrança passa a refletir consumo real de tokens do modelo | [0012](../adr/0012-medicao-real-de-tokens-do-llm.md) |

---

## 3. Contextos delimitados e mapa de contexto

Antes de desenhar serviços, é preciso desenhar fronteiras de significado. A
palavra "documento" quer dizer coisas diferentes em partes diferentes do
sistema, e é exatamente por isso que cada contexto tem o seu próprio modelo.

```mermaid
flowchart TB
    subgraph nucleo["Núcleo — onde está a vantagem do produto"]
        CF["Conformidade Fiscal<br/><i>limits</i><br/>Transacao, ResumoAnual,<br/>LimiteDoMEI"]
        AN["Análise e Alertas<br/><i>insights</i><br/>RitmoDeVendas, Projecao,<br/>RegraDeAlerta"]
        AS["Assistente Conversacional<br/><i>agent-orchestrator</i><br/>Conversa, JanelaDeContexto,<br/>TrechoRecuperado"]
    end

    subgraph suporte["Suporte — necessário, não diferenciador"]
        PD["Processamento Documental<br/><i>documents + worker</i><br/>DocumentoEnviado,<br/>ExtracaoEstruturada"]
        MD["Medição e Faturamento<br/><i>billing</i><br/>ContaDeCreditos,<br/>EventoDeConsumo"]
    end

    subgraph generico["Genérico — resolvido por terceiros"]
        ID["Identidade<br/><i>auth</i>"]
        NT["Notificação<br/><i>notifications</i>"]
        PL["Plataforma<br/><i>gateway, Unleash, observabilidade</i>"]
    end

    PD -->|"Cliente/Fornecedor<br/>documento.confirmado"| CF
    CF -->|"Cliente/Fornecedor<br/>transacao.*"| AN
    AN -->|"Cliente/Fornecedor<br/>alerta.disparado"| NT
    CF -->|"ACL — traduz ResumoAnual<br/>em RetratoFiscal"| AS
    AN -->|"ACL"| AS
    PD -->|"Conformista<br/>trecho indexável"| AS
    AS -->|"tokens.consumidos"| MD
    PD -->|"tokens.consumidos"| MD
    ID -->|"Núcleo Compartilhado<br/>apenas identidade"| CF & PD & AN & AS & MD

    classDef nucleoC fill:#0c4a6e,stroke:#0ea5e9,color:#f0f9ff
    classDef suporteC fill:#3f2d0b,stroke:#d97706,color:#fffbeb
    classDef genericoC fill:#1e293b,stroke:#64748b,color:#f1f5f9
    class CF,AN,AS nucleoC
    class PD,MD suporteC
    class ID,NT,PL genericoC
```

### Linguagem ubíqua, por contexto

O mesmo termo muda de sentido conforme a fronteira. Confundir esses sentidos é
a origem mais comum de bug em sistema fiscal.

| Termo | Processamento Documental | Conformidade Fiscal | Análise e Alertas |
| --- | --- | --- | --- |
| **Documento** | Arquivo enviado, com OCR, extração e estados | Não existe — só a `origem` da transação | Não existe |
| **Valor** | Número extraído, com grau de confiança | Valor confirmado, imutável após revisão | Ponto de uma série temporal |
| **Venda** | Sugestão derivada do confronto de CNPJ | Fato: `tx_type = venda`, conta para o teto | Componente do ritmo |
| **Confiança** | Qualidade da extração (0 a 1) | Não existe — o dado confirmado é certo | Não existe |
| **Limite** | Não existe | R$ 81.000,00, ou proporcional ao mês de abertura | Referência das projeções |

**Regra de fronteira:** o grau de confiança da extração **nunca** atravessa para
a Conformidade Fiscal. Uma transação registrada é um fato confirmado por um
humano, não uma estimativa. É a revisão manual que transforma incerteza em fato,
e é essa fronteira que torna o dado fiscal defensável.

### Camadas anticorrupção

Três traduções explícitas impedem que um modelo externo contamine o domínio:

1. **Gemini → Documento.** A resposta do modelo é texto que se parece com JSON.
   A tradução valida tipos, normaliza CNPJ, rejeita valor não positivo e data
   fora do formato. É o que `sanitize_gemini_result` já faz hoje, e que passa a
   ser uma camada nomeada e testada.
2. **Limits → Assistente.** O `ResumoAnual` do Limits vira um `RetratoFiscal`
   com a linguagem do agente. Mudar o formato do resumo não deve exigir
   reescrever prompt.
3. **Documento → Trecho indexável.** O que entra no índice vetorial é texto
   limpo e segmentado, não a estrutura do documento.

---

## 4. Fluxo de upload, do envio à projeção

```mermaid
sequenceDiagram
    autonumber
    actor MEI
    participant FE as Frontend
    participant GW as Gateway
    participant DO as documents
    participant MN as MinIO
    participant MG as MongoDB
    participant WK as worker
    participant GE as Gemini
    participant BUS as Redis Streams
    participant LI as limits
    participant IN as insights
    participant NO as notifications

    MEI->>FE: seleciona a nota fiscal
    FE->>GW: POST /documents/upload
    GW->>DO: encaminha com correlation-id
    DO->>DO: calcula hash SHA-256
    alt hash já existe
        DO-->>FE: 200 com o documento anterior
        Note over DO,FE: deduplicação evita<br/>cobrar a API duas vezes
    else documento novo
        DO->>MN: grava o arquivo original
        DO->>MG: cria registro, estado "recebido"
        DO->>WK: enfileira processar_documento (fila ocr)
        DO-->>FE: 202 Accepted + id + URL de acompanhamento
        FE-->>MEI: "Processando..." com barra de progresso
        WK->>DO: POST /_interno/processar/{id}
        Note over WK,DO: o worker orquestra;<br/>o pipeline fica no Documents<br/>(ADR-0016)
        DO->>MN: lê o arquivo original
        DO->>DO: Tesseract + extração multimodal (Gemini)
        DO->>MG: estado "extraido", campos, confiança
        DO-->>WK: 200 (ou 503 -> retry com recuo, 3x -> estado "erro")
        WK->>BUS: publica documento.extraido
        FE->>GW: GET /documents/documentos/{id} (polling)
        FE-->>MEI: tela de revisão preenchida (ou falha + "tentar de novo")
    end

    MEI->>FE: corrige o valor e confirma como venda
    FE->>GW: POST /documents/confirm
    GW->>DO: encaminha
    DO->>MG: estado "confirmado" + revisão humana
    DO->>BUS: outbox publica documento.confirmado

    par consumidores reagem em paralelo
        BUS->>LI: registra a transação
        LI->>BUS: outbox publica transacao.criada
    and
        BUS->>IN: atualiza projeções e ritmo
        IN->>IN: avalia as regras de alerta
        IN->>BUS: publica alerta.disparado
        BUS->>NO: grava no feed in-app
    end

    NO-->>FE: badge de notificação
    FE-->>MEI: "No ritmo atual, você atinge o teto em 12/nov"
```

O ponto central do desenho: entre o passo 8 (`202 Accepted`) e o passo 20 o
usuário nunca fica bloqueado, e nenhuma falha de consumidor derruba a
confirmação dele.

---

## 5. Fluxo do chat, com contexto montado

```mermaid
sequenceDiagram
    autonumber
    actor MEI
    participant FE as Frontend
    participant AG as agent-orchestrator
    participant CV as Conversas (pgvector)
    participant LI as limits
    participant IN as insights
    participant BI as billing
    participant GE as Gemini

    MEI->>FE: "Posso aceitar um contrato de R$ 12.000?"
    FE->>AG: POST /agent/chat

    AG->>BI: reserva estimativa de créditos
    BI-->>AG: reserva confirmada

    par montagem do contexto em paralelo
        AG->>LI: GET /summary
    and
        AG->>IN: GET /insights/retrato-fiscal
    and
        AG->>CV: histórico e memória de longo prazo
    end

    AG->>GE: embedding da pergunta
    AG->>CV: busca híbrida (vetorial + textual)
    AG->>AG: reordena por relevância e diversidade
    AG->>AG: monta a janela dentro do orçamento de tokens

    AG->>GE: prompt aumentado
    GE-->>AG: resposta + usage_metadata

    AG->>BI: acerta a reserva pelo consumo real
    AG->>CV: grava o turno
    AG-->>FE: resposta + fontes citadas
    FE-->>MEI: resposta com as regras usadas

    Note over AG,CV: a cada 10 turnos, tarefa Celery<br/>resume a conversa e libera janela
```

---

## 6. Portas de rede

| Serviço | Porta interna | Exposta | Observação |
| --- | --- | --- | --- |
| api-gateway | 80 | 8000 | única entrada da aplicação |
| frontend | 5173 | 3000 | Vite em desenvolvimento |
| auth, billing, limits, documents, agent, insights, notifications | 8000 | — | só pela rede interna |
| worker | — | — | sem porta, consome fila |
| PostgreSQL (5 instâncias) | 5432 | — | uma por serviço |
| MongoDB | 27017 | — | |
| Redis | 6379 | — | broker, cache e streams |
| MinIO | 9000 / 9001 | 9001 | console administrativo |
| Unleash | 4242 | 4242 | interface de flags |
| Grafana | 3000 | 3001 | painéis |
| Prometheus | 9090 | 9090 | perfil de observabilidade |
| Tempo | 3200 | — | |
| Loki | 3100 | — | |
| Alertmanager | 9093 | 9093 | |
| OTel Collector | 4317 / 4318 | — | gRPC e HTTP |

---

## 7. Perfis do Compose

```bash
# só a aplicação
docker compose up -d

# aplicação + pilha de observabilidade
docker compose --profile observability up -d

# demonstração, com imagens publicadas na CI
docker compose -f docker-compose.release.yml pull
docker compose -f docker-compose.release.yml up -d
```

Separar o perfil de observabilidade importa: são sete contêineres a mais, e quem
só quer executar a aplicação não deveria pagar esse custo de memória.
