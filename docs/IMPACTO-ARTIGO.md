# Impacto no artigo

Este arquivo rastreia o que muda no texto do TG conforme o plano avança. Cada
entrega que altera uma afirmação do artigo deve atualizar a linha correspondente
aqui — assim, na hora de revisar o texto, a lista de mudanças já existe.

**Artigo:** entregue à parte (não incluído nesta cópia pública).

---

## 1. Afirmações que passam a se sustentar

Cada uma destas frases já está no artigo e hoje não sobrevive a uma verificação.
Ao final da onda indicada, ela passa a ser verdadeira.

| Seção | Afirmação atual | Onda | O que muda |
| --- | --- | --- | --- |
| Metodologia | "Tailwind CSS para estilização" | 4 | Passa a ser verdade (US-24) |
| Metodologia | "MongoDB para metadados e documentos estruturados" | 3 | Passa a ser verdade (US-20) |
| Metodologia | "Celery e Redis para OCR e LLM assíncronos" | 3 | Passa a ser verdade (US-18) |
| Metodologia | "MinIO como alternativa local ao S3" | 3 | Passa a ser verdade (US-19) |
| Metodologia | "REST e filas de mensagens" | 3 | Filas passam a existir (US-21) |
| Metodologia | "Testes unitários, de integração e de usabilidade" | 0 e 4 | Suíte real + SUS (US-04, US-05) |
| Resultados | "Testes cobrindo os principais fluxos" | 0 | Deixa de ser roteiro manual |
| Desenvolvimento | "Faturamento por consumo de tokens" | 6 | Consumo passa a ser medido (US-45) |
| Futuras etapas | "Logs centralizados e Prometheus/Grafana" | 1 | Sai de "futuro" para "implementado" |
| Conclusões | LGPD: retenção, criptografia e exclusão pendentes | 7 | As três deixam de ser pendência |

---

## 2. Seções que ganham conteúdo novo

### 2.1 Metodologia

Passa a poder descrever, com evidência:

- **Trunk-based development** com Conventional Commits e versionamento semântico,
  substituindo a menção genérica a SCRUM por um processo verificável no histórico
  do repositório.
- **Pirâmide de testes** em cinco níveis, incluindo teste de mutação no núcleo
  fiscal — instrumento raro em trabalho de graduação e forte na argumentação.
- **Feature flags** como viabilizador de integração contínua, ligando a prática à
  literatura de entrega contínua (Humble e Farley, Hodgson).
- **Modelagem estratégica com contextos delimitados**, com mapa de contexto e
  camadas anticorrupção — aprofunda a discussão de microsserviços, que hoje é
  apenas estrutural.

### 2.2 Desenvolvimento

- Arquitetura orientada a eventos com padrão Outbox, e a justificativa de por que
  Redis Streams em vez de Kafka. **US-21 entregue:** publicador e consumidor em
  processo (ADR-0018), escrita atômica transação+evento, consumo idempotente,
  e o teste de caos na CI (derruba o Insights, cria 10 transações, verifica que
  nenhuma se perde) — a evidência empírica de "zero evento perdido".
- Separação de modelo de leitura (CQRS) no Insights Service, com o argumento de
  fronteira: por que o motor analítico não ficou no Limits. **US-23 entregue:**
  projeção materializada alimentada por eventos, comando de reconstrução a partir
  do Limits (corrigir fórmula é código, não migração de dados) e conciliação
  noturna que alerta divergência acima de R$ 0,01 — o mecanismo que torna o dado
  duplicado defensável.
- Engenharia de contexto do agente: as sete camadas, o orçamento de tokens e a
  ordem de truncamento. Este é um tema atual e pouco explorado em TG.

### 2.3 Resultados e Discussões

O ganho maior está aqui. Os números atuais vêm de uma medição pontual; passam a
vir de um pipeline noturno reprodutível.

| Tabela nova | Conteúdo | Origem |
| --- | --- | --- |
| Latência antes e depois | Upload e chat, medidos com o mesmo instrumento | Ondas 1 e 3 |
| Acurácia por campo e formato | 40 documentos, série temporal noturna | Onda 1 em diante |
| Recuperação do RAG por técnica | 30 perguntas, com e sem cada flag | Onda 6 |
| Comportamento sob carga | Ponto de saturação identificado pelo k6 | Onda 1 |
| Métricas DORA | Série semanal do projeto inteiro | Onda 0 até 12/09/2026 (ADR-0020 — Actions desligado por cobrança; registrar o corte, não tratar como série contínua) |
| Custo operacional | Custo por documento e por conversa, em reais | Onda 1 em diante |
| Usabilidade | SUS comparando dashboard v1 e v2 | Onda 4 |

A tabela de **recuperação por técnica** merece destaque: como cada melhoria do
RAG está atrás da sua própria flag, é possível isolar a contribuição de cada uma.
Isso transforma "implementamos busca híbrida" em "a busca híbrida elevou o acerto
na primeira posição de X para Y" — que é uma afirmação de outra natureza.

### 2.4 Conclusões

As limitações declaradas mudam de lista. Saem retenção, criptografia e exclusão
(Onda 7). Permanece a autenticação simplificada — mas agora como **decisão
registrada com justificativa e critério de revisão**
([ADR-0011](adr/0011-manter-autenticacao-simplificada.md)), não como omissão.

---

## 3. Correções necessárias no texto atual

| Onde | Problema | Correção |
| --- | --- | --- |
| Resumo e Metodologia | Tailwind citado sem existir | Corrigir agora, ou aguardar a Onda 4 |
| Metodologia | MongoDB, Redis, Celery e MinIO citados sem existir | Idem, conforme a Onda 3 |
| Resultados | "cinco microsserviços de backend" | São cinco mais o gateway; passarão a sete com Insights e Notifications |
| Referências | LEWIS, P.; OGUNLANA, D.; LEE, H.; STABLES, R.; RIEDEL, S. | Autoria incorreta. O correto é LEWIS, P. et al., com PEREZ, PIKTUS, PETRONI, KARPUKHIN entre os autores |
| Referências | ROHAIME, KATTI, KRIEGER, PULIKONDA, VEMULAPALLI | Conferir DOI e dados de publicação antes da entrega |
| Fundamentação | "limite do MEI em 2026 é de R$ 81.000,00" | Confirmar se houve alteração legislativa até a data da defesa |

A linha das referências de Lewis et al. é a mais importante: citação com autoria
trocada é o tipo de erro que uma banca localiza rápido.

### 3.1 Alinhamento ao código em 15/11/2026 (já aplicado no `.docx`)

| Onde | Antes | Agora |
| --- | --- | --- |
| Fundamentação (RAG) | modelo gemini-2.5-flash | gemini-3.5-flash-lite; a Metodologia diz que o teste controlado foi medido com o modelo anterior |
| Fundamentação (API Gateway) | NGINX centraliza autenticação e controle de acesso | Só roteia e propaga o correlation-id |
| Desenvolvimento (telas) | Login com credenciais; dashboard com "agentes ativos"; upload aceita XLSX | Entrada só por demonstração; painel com ritmo, projeção, mês a mês e origem do faturamento; upload de PDF, JPG, PNG e TXT; tela de configurações |
| Desenvolvimento (backend) | Limits ausente da lista de serviços | Limits, worker, insights e notifications descritos |
| Integração frontend–backend | Axios e React Query | `fetch` nativo, sem biblioteca de cache |
| Justificativa | Registra o custo das chamadas ao modelo | Consumo de tokens por operação; custo só na leitura de notas |
| Resultados e Tabela 1 | Cinco serviços (texto) e seis (tabela) | Oito serviços de backend |
| Futuras etapas | Prometheus e Grafana como futuro | Prometheus e logs estruturados existem; só o Grafana é futuro |

### 3.2 Regras fiscais configuráveis (US-57, #91, ADR-0022)

O teto, a faixa de alerta, a meta mensal e os limiares da projeção deixam de
ser constantes: o usuário os ajusta na tela de Configurações (atrás da flag
`metricas-configuraveis`), e os valores oficiais são só o ponto de partida.
Consequências para o texto:

- A afirmação de que "o limite do MEI em 2026 é de R$ 81.000,00" continua
  verdadeira como valor oficial, mas o sistema não depende mais dela: se a lei
  mudar, o usuário altera o teto sem nova versão.
- Limitação a registrar: a base de conhecimento do RAG ainda cita o teto de
  R$ 81.000,00 como texto. Um usuário que configurar outro teto vê o número
  certo no painel e no prompt do agente, mas o trecho recuperado pode citar o
  valor oficial.

### 3.3 Foto da nota pela câmera, com barreira de qualidade (#100)

O upload ganha um botão que abre a câmera traseira do celular. Antes de gastar
OCR e Gemini, a foto passa por uma barreira de qualidade em dois lugares com as
mesmas contas: no próprio aparelho (a foto ruim nem sai do celular) e no
`documents`, que tem a palavra final. A barreira mede resolução, brilho,
contraste e nitidez (variância do Laplaciano e a razão de nitidez, isto é,
quanto a variância cai quando a foto é suavizada de novo). Uma foto recusada
mostra o motivo, como corrigir e a opção "enviar mesmo assim". Não há feature
flag: o envio forçado é a válvula de escape.

Consequências para o texto:

- **Desenvolvimento (telas):** a frase de 3.1, "upload de PDF, JPG, PNG e
  TXT", passa a incluir a captura pela câmera do celular, com a checagem de
  qualidade antes do envio.
- **Justificativa e custo:** a afirmação de que só a leitura de notas custa
  tokens ganha um mecanismo de contenção. Uma foto ilegível deixa de pagar uma
  chamada ao Gemini que não tinha como dar certo. A métrica
  `documentos_fotos_recusadas_total{motivo}` conta as recusas no servidor. As
  recusas feitas no celular não chegam a ele, então esse número é um piso da
  economia, não o total.
- **Resultados e Discussões (achado próprio):** na calibração, contra o
  Tesseract e depois contra o Gemini, o modelo **não falhou** diante de borrão
  forte. Ele devolveu valores plausíveis e errados (R$ 1.087 e R$ 1.450 para
  uma nota de R$ 1.557,80). A barreira, portanto, protege a integridade do dado,
  não só o custo, e liga o tema à literatura de alucinação em LLMs
  multimodais. Também vale registrar que o Gemini lê bem mais borrado que o
  Tesseract: um desfoque de raio 4 num cupom e de raio 6 numa DANFE. Por isso
  os cortes finais foram calibrados contra o Gemini.
- **Metodologia:** a calibração usou as 40 notas do lote de teste e 25 versões
  degradadas de cada uma (borrão, tremido, escuro, estourado, baixa
  resolução). Com o menor lado em 300 px nenhuma nota foi lida. Escuridão
  moderada quase não atrapalha o OCR. Os cortes finais foram razão de nitidez
  < 1,1 ou variância < 10.
- **Limitações a declarar:** os cortes foram calibrados com degradações
  sintéticas, não com fotos reais tremidas de celular. Parte do tremido de
  movimento forte ainda passa pela barreira. E uma DANFE com desfoque de raio 6,
  que o Gemini leu, seria recusada (falso positivo, contornável pelo "enviar
  mesmo assim").

---

## 4. Figuras a atualizar ou criar

| Figura | Situação | Ação |
| --- | --- | --- |
| Fig. 1 — Componentes | Refeita em 15/11/2026 | Oito serviços, Redis (fila e eventos), MinIO, MongoDB, Unleash, Prometheus e Gemini |
| Fig. 3 — Dashboard | Será substituído | Recapturar após a Onda 4; com o redesign (#86, flag `visual-novo`) decidir qual visual vai para a figura e dizer na legenda que o visual é controlado por flag |
| Fig. 7 — Sequência do upload | Refeita em 15/11/2026 no fluxo síncrono: extração (Gemini e OCR em paralelo), conferência pelo usuário e só então gravação no Limits e indexação no RAG | O caminho assíncrono (202 + worker, ADR-0016) aparece na Fig. 1 |
| **Nova** — Latência do upload antes/depois | US-18: p95 de ~6,0 s (síncrono) para < 500 ms (202 Accepted). Medir com o mesmo script k6 da US-14, flag `ocr-assincrono` on/off | Rodar antes da defesa |
| Fig. 8 — Sequência do chat | Refeita em 15/11/2026 com a etapa de RAG (embedding, busca no pgvector) e as fontes na resposta | Refazer de novo se a montagem de contexto da Onda 6 entrar |
| **Nova** — Mapa de contexto | — | Contextos delimitados e suas relações |
| **Nova** — Painel do Grafana | — | Evidência de observabilidade |
| **Nova** — Corrida contra o limite | — | O gráfico principal do dashboard novo |
| **Nova** — Régua do limite e telas responsivas | Redesign #86 (`docs/redesign-visual.md`) | Capturar painel no desktop e no celular com `visual-novo` ligada; útil se o artigo citar acessibilidade e responsividade |
| **Nova** — Aviso de foto ilegível | #100 | Capturar no celular a tela "Essa foto não vai dar para ler", com a prévia da foto, o motivo e a dica; opcional, ao lado de uma foto aceita |
| **Nova** — Interface do Unleash | — | Evidência de liberação gradual |
| **Nova** — Métricas DORA | — | Evidência do processo de engenharia; série com corte em 12/09/2026 (ADR-0020) |

---

## 5. Trabalhos correlatos

A Tabela 1 do artigo compara cinco trabalhos. Duas colunas novas fortaleceriam o
posicionamento, porque são justamente as dimensões em que este trabalho passa a
se distinguir: **observabilidade** e **entrega contínua**. Nenhum dos cinco
correlatos as trata.

Referências que valeria acrescentar à fundamentação, dada a nova ênfase:

- FORSGREN, N.; HUMBLE, J.; KIM, G. *Accelerate: The Science of Lean Software
  and DevOps.* IT Revolution, 2018. — base das métricas DORA.
- HUMBLE, J.; FARLEY, D. *Continuous Delivery.* Addison-Wesley, 2010.
- EVANS, E. *Domain-Driven Design.* Addison-Wesley, 2003. — contextos delimitados.
- BEYER, B. et al. *The Site Reliability Workbook.* O'Reilly, 2018. — SLOs e
  orçamento de erro.
- RICHARDSON, C. *Microservices Patterns.* Manning, 2018. — já citado como
  Richardson (2018) para API Gateway; passa a sustentar também Outbox e CQRS.

---

## 6. Registro de consumo no billing (ADR-0024, 19/11/2026)

Com a flag `billing-tokens-reais`, o consumo de cada chamada ao Gemini passa a
ser guardado por usuário no billing, com extrato (`GET /usage/{email}`). No
artigo: Objetivos (verificação do registro de tokens), Desenvolvimento do
Backend, Quadros 2 e 3, Figuras 1, 7 e 8, e uma tabela nos Resultados com a
rodada de medição (`docs_para_teste/teste_controlado/consumo_*.md`).

