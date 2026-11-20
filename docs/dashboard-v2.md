# Dashboard MEI v2 — especificação

> Protegido pela flag `dashboard-v2`. Enquanto ela estiver desligada, a tela
> atual continua servindo. Ver [ADR-0008](adr/0008-unleash-para-feature-flags.md).

---

## 1. O problema com o dashboard atual

O dashboard de hoje mostra seis números e uma barra de progresso. Ele responde
bem a uma pergunta — *quanto já faturei?* — e não responde a nenhuma das outras
que um MEI realmente tem:

| Pergunta do MEI | O dashboard atual responde? |
| --- | --- |
| Quanto já faturei este ano? | Sim |
| **Estou indo rápido demais?** | Não |
| **Se continuar assim, quando estouro o teto?** | Não |
| **Quanto posso faturar por mês até dezembro sem estourar?** | Não |
| **Posso aceitar este contrato de R$ 12.000?** | Não |
| **Este mês foi melhor ou pior que o passado?** | Não |
| **De quais clientes vem meu faturamento?** | Não |
| Quanto tempo tenho até o próximo DAS? | Não |

Há também um problema técnico: o pouco de cálculo que existe mora no navegador.
O percentual do limite é um `useMemo` no `DashboardPage.tsx`, e o filtro que
separa venda de compra está reimplementado ali, em paralelo à mesma regra no
backend. Duas cópias da mesma regra fiscal divergem — é uma questão de tempo.

O motor de cálculo migra para o Insights Service
([ADR-0009](adr/0009-servico-de-insights-com-cqrs.md)).

---

## 2. Motor de ritmo de vendas

Esta é a parte nova mais importante. As definições abaixo são normativas: são
elas que os testes unitários do módulo `dominio/ritmo.py` verificam.

### 2.1 Limite aplicável

O teto não é sempre R$ 81.000,00. Para quem abriu o MEI durante o ano, ele é
proporcional aos meses de atividade — regra que já está na base de conhecimento
do RAG, mas que o cálculo do sistema ignora hoje.

```
limite_aplicavel = 81000,00                                 se abertura < ano corrente
limite_aplicavel = (81000,00 / 12) x meses_de_atividade     se abertura no ano corrente

meses_de_atividade = 12 - mes_de_abertura + 1
```

Um MEI aberto em julho tem limite de R$ 40.500,00 naquele ano. Aplicar
R$ 81.000,00 a ele seria dizer que está seguro quando não está.

### 2.2 Indicadores

Considerando `D` = dias decorridos no ano, `A` = total de dias do ano,
`F` = faturamento acumulado (apenas vendas) e `L` = limite aplicável:

| Indicador | Fórmula | Lê-se |
| --- | --- | --- |
| Taxa diária realizada | `td = F / D` | quanto o MEI fatura por dia, na média do ano |
| Taxa diária de referência | `tr = L / A` | quanto poderia faturar por dia para encostar no teto em 31/12 |
| **Índice de ritmo** | `IR = td / tr` | `1,0` = no ritmo exato do teto; `1,3` = 30% acima |
| Projeção anual | `P = td x A` | onde o ano termina, se nada mudar |
| Dias até o teto | `DT = (L - F) / td` | quantos dias de folga restam |
| Data prevista de estouro | `hoje + DT dias` | a data, se `DT` cair dentro do ano |
| Faturamento seguro por mês | `FS = (L - F) / meses_restantes` | teto mensal para pousar exatamente no limite |
| Taxa diária recente | `td30 = F_30d / 30` | ritmo dos últimos 30 dias |
| **Aceleração** | `AC = td30 / td` | `> 1` significa acelerando em relação ao ano |

O **índice de ritmo** é o número central do dashboard novo. Ele responde à
pergunta que o percentual acumulado não responde: *estar em 40% do limite é
tranquilo em outubro e é alarmante em março.* O percentual sozinho não distingue
os dois casos; o índice de ritmo sim.

### 2.3 Guardas contra número enganoso

Fórmula de projeção aplicada a dado insuficiente produz alarme falso, e alarme
falso destrói a confiança no sistema inteiro.

| Situação | Guarda |
| --- | --- |
| `D < 30` dias no ano | Não projeta. Exibe "dados insuficientes para projeção" |
| Menos de 3 transações no ano | Não projeta |
| `td = 0` | `DT` é infinito. Exibe "sem faturamento registrado" |
| Uma única venda representa > 60% do total | Projeção marcada como "influenciada por lançamento atípico" |
| MEI aberto há menos de 60 dias | Usa taxa diária desde a abertura, não desde 1º de janeiro |

### 2.4 Níveis de alerta

Combinam o **realizado** (o que já aconteceu) com o **projetado** (para onde
aponta). Um MEI em 30% do limite mas com ritmo de estourar em setembro precisa
saber disso em março, não em setembro.

| Nível | Condição | Mensagem |
| --- | --- | --- |
| `ok` | `P < 0,8 L` e `F < 0,8 L` | No ritmo. Projeção de R$ X até dezembro |
| `atencao_ritmo` | `P >= 0,8 L` e `F < 0,5 L` | Ainda longe do teto, mas o ritmo aponta para R$ X |
| `atencao` | `F >= 0,8 L` e `F < L` | Já usou N% do limite |
| `risco` | `P > L` e `F < L` | No ritmo atual, o teto chega em DD/MM |
| `estourado` | `F >= L` | Limite ultrapassado. DAS complementar devido |
| `desenquadramento` | `F > 1,2 L` | Acima de 20% do teto: desenquadramento retroativo |

O nível `desenquadramento` existe porque a consequência muda de natureza: até
20% de excesso, a migração para Microempresa vale a partir de janeiro seguinte;
acima de 20%, ela é retroativa ao mês do estouro, com juros. Essa regra já está
na base do RAG e passa a valer também para o alerta.

### 2.5 Outros alertas do motor

| Alerta | Gatilho | Por quê |
| --- | --- | --- |
| Mês atípico | Mês corrente acima de 2x a mediana dos anteriores | Pode ser erro de digitação ou de OCR |
| Inatividade | Sem lançamento há mais de 45 dias | Nota fiscal esquecida vira surpresa em dezembro |
| Concentração de cliente | Um CNPJ acima de 70% do faturamento | Risco de dependência, e possível indício de relação de emprego |
| DAS a vencer | Dia 15 de cada mês | Vence dia 20 |
| DASN-SIMEI | 1º de abril e 1º de maio | Prazo em 31 de maio |
| Margem negativa | Compras acima das vendas em 2 meses seguidos | O negócio está consumindo caixa |

### 2.6 Antirruído

Alerta demais é igual a alerta nenhum.

- **Silêncio por nível:** o mesmo alerta não repete por 7 dias, salvo mudança de
  nível.
- **Só escala:** de `atencao` para `risco` notifica; o caminho inverso apenas
  atualiza a tela, sem notificar.
- **Teto diário:** no máximo 3 notificações por dia por usuário.
- **Dispensa é lembrada:** alerta dispensado só reaparece se o nível piorar.

---

## 3. Estrutura da tela

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Bem-vindo, Ronaldo          [2026 ▾]   [Exportar ▾]  [+ Lançamento]  🔔 3   │
├──────────────────────────────────────────────────────────────────────────────┤
│  ⚠  No ritmo atual você atinge o teto do MEI em 15 de outubro.             │
│     Para chegar a dezembro dentro do limite, fature até R$ 5.131 por mês.        │
│                                        [Ver simulação]  [Dispensar]          │
├───────────────────────────────┬──────────────────────────────────────────────┤
│                               │  Ritmo de vendas                             │
│      ╭───────────────╮        │  ┌────────────────────────────────────────┐  │
│     ╭─╯   58,4%      ╰─╮      │  │ Índice de ritmo      1,27  ▲ acelerando│  │
│    │    R$ 47.304,00   │      │  │ Média diária         R$ 281,57         │  │
│    │  ─────────────    │      │  │ Referência do teto   R$ 221,92         │  │
│    │  restam           │      │  │ Projeção 2026        R$ 102.773,57 ⚠   │  │
│    │  R$ 33.696,00     │      │  │ Dias de folga        120               │  │
│     ╰─╮             ╭─╯       │  │ Últimos 30 dias      R$ 9.640,00       │  │
│      ╰───────────────╯        │  └────────────────────────────────────────┘  │
│    Teto anual R$ 81.000,00    │                                              │
├───────────────────────────────┴──────────────────────────────────────────────┤
│  Vendas    Despesas    Lucro      Ticket médio   Documentos   Créditos       │
│  R$ 47.304 R$ 12.180   R$ 35.124  R$ 1.183       38           842            │
│  ▁▂▃▅▆█    ▁▁▂▂▃▃      ▂▃▄▅▆█     ▃▃▄▄▅▅         ▂▄▅▆▇█       █▇▆▅▄▃         │
├──────────────────────────────────────────────────────────────────────────────┤
│  Corrida contra o limite                          [Ano] [12 meses] [Trimestre]│
│  R$                                                                          │
│  81k ┤─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ teto      │
│      │                                              ░░░░░░░▒▒▒▒▒▒▓▓▓▓        │
│  60k ┤                                      ░░░░▒▒▒▒▒▒▓▓▓▓▓▓▓▓▓             │
│      │                          ████████████▓▓▓▓▓▓▓▓▓  ← cone de projeção    │
│  40k ┤                ██████████                                             │
│      │      ██████████            ·········· ritmo de referência             │
│  20k ┤██████         ·············                                           │
│      │····███                                                                │
│    0 └┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬───            │
│      jan  fev  mar  abr  mai  jun  jul  ago  set  out  nov  dez              │
│      ██ realizado   ▓▓ projeção provável   ░░ faixa de incerteza             │
├──────────────────────────────────────────────────────────────────────────────┤
│  Mês a mês                              │  Origem do faturamento             │
│  R$                                     │                                    │
│  12k ┤        ▄▄                        │   Construtora Silva    38% ████    │
│      │    ▄▄  ██  ▄▄                    │   Mercado Bom Preço    24% ███     │
│   8k ┤▄▄  ██  ██  ██  ▄▄                │   Padaria do João      15% ██      │
│      │██──██──██──██──██── meta 6.750   │   Outros (12)          23% ██      │
│   4k ┤██  ██  ██  ██  ██                │                                    │
│      │██▁▁██▁▁██▁▁██▁▁██  ▁ despesas    │   ⚠ 38% em um só cliente           │
│    0 └────────────────────              │                                    │
│      abr mai jun jul ago                │                                    │
├──────────────────────────────────────────────────────────────────────────────┤
│  Calendário fiscal              │  Movimentação recente        [filtros ▾]   │
│  ● 20/set  DAS de agosto        │  20/08  Venda    R$ 3.200,00  NF-e 1042    │
│    R$ 76,60                     │  18/08  Compra   R$   480,00  Fornecedor   │
│  ● 31/05  DASN-SIMEI 2026       │  15/08  Venda    R$ 1.850,00  NF-e 1041    │
│    entregue ✓                   │  12/08  Venda    R$   940,00  Recibo       │
└─────────────────────────────────┴────────────────────────────────────────────┘
```

### 3.1 Faixa por faixa

**Barra de alertas.** Aparece apenas quando há algo acionável. Sempre traz uma
ação concreta ("Ver simulação"), nunca só um aviso. Dispensável, com a dispensa
lembrada.

**Termômetro do limite.** Gauge radial substituindo a barra linear atual.
Mostra três informações na mesma peça: percentual consumido, valor absoluto e
valor restante. A cor do arco segue o nível de alerta — e nunca é o único
sinal: o rótulo textual e o ícone acompanham.

**Painel de ritmo.** O bloco novo. Índice de ritmo com seta de tendência,
média diária contra a referência, projeção anual e dias de folga.

**Tiles com minigráficos.** Seis indicadores, cada um com uma faixa de
tendência dos últimos 6 meses. Número sozinho não diz direção; a faixa diz.

**Corrida contra o limite.** O gráfico principal. Área do acumulado real, linha
pontilhada do ritmo de referência (`tr x dia`) e cone de projeção do dia atual
até 31/12. O cone tem três faixas: pessimista (ritmo dos últimos 30 dias),
provável (ritmo do ano) e otimista (ritmo dos últimos 90 dias). Onde o cone
cruza a linha do teto está a data de estouro, marcada com anotação.

**Mês a mês.** Barras de vendas e despesas com linha de meta mensal
(`limite / 12`, ou a meta configurada pelo usuário). Mês acima da meta ganha
destaque visual.

**Origem do faturamento.** Concentração por CNPJ do cliente, extraída dos
documentos. Alerta de dependência acima de 70%.

**Calendário fiscal.** Próximos vencimentos, com marcação de entregue.

**Movimentação recente.** A tabela atual, ganhando filtro por tipo, período e
origem, busca textual e edição em linha.

---

## 4. Controles de gestão

Além de visualizar, o MEI precisa agir. Estes controles não existem hoje —
inclusive o mais básico: **não há como registrar uma venda sem enviar um
documento**, apesar de o endpoint `POST /limits/transactions` já existir.

| Controle | O que faz | História |
| --- | --- | --- |
| **Lançamento manual** | Registrar venda ou compra sem documento, em 3 campos | US-30 |
| **Simulador** | "Posso aceitar R$ 12.000 em outubro?" mostra o impacto na projeção antes de aceitar | US-31 |
| **Metas mensais** | Definir meta por mês; a linha do gráfico passa a ser a meta, não a média | US-32 |
| **Categorias** | Classificar lançamentos e ver a composição da despesa | US-33 |
| **Perfil do MEI** | CNPJ, ramo de atividade e data de abertura — que alimentam o limite proporcional e o valor do DAS | US-34 |
| **Edição em massa** | Corrigir tipo ou data de vários lançamentos de uma vez | US-35 |
| **Exportação** | CSV e XLSX além do PDF atual, com filtros aplicados | US-36 |
| **Comparativo anual** | Sobrepor a curva deste ano à do anterior | US-37 |
| **Centro de notificações** | Histórico de alertas, com marcação de lido | US-38 |

O **perfil do MEI** é pré-requisito de várias outras coisas: sem a data de
abertura não há limite proporcional; sem o ramo de atividade não há valor
correto do DAS (comércio recolhe ICMS, serviço recolhe ISS); sem o CNPJ a
detecção automática de venda contra compra não funciona — hoje ele é digitado
num campo da barra lateral e guardado no `localStorage`.

---

## 5. Contrato da API

Uma chamada devolve tudo que a tela precisa. Hoje o dashboard faz duas chamadas
e calcula o resto no navegador.

```http
GET /insights/dashboard/{email}?ano=2026
```

```json
{
  "email": "mei@exemplo.com",
  "ano": 2026,
  "calculado_em": "2026-08-22T13:04:11Z",

  "limite": {
    "aplicavel": 81000.00,
    "base_legal": "R$ 81.000,00 anuais (Resolução CGSN)",
    "proporcional": false,
    "mes_abertura": null
  },

  "realizado": {
    "vendas": 47304.00,
    "despesas": 12180.00,
    "lucro": 35124.00,
    "restante": 33696.00,
    "percentual_usado": 58.4,
    "transacoes": 38,
    "ticket_medio": 1183.00
  },

  "ritmo": {
    "indice": 1.27,
    "taxa_diaria": 281.57,
    "taxa_diaria_referencia": 221.92,
    "taxa_diaria_30d": 321.33,
    "aceleracao": 1.14,
    "tendencia": "acelerando",
    "projecao_anual": 102773.57,
    "projecao_confiavel": true,
    "dias_ate_o_teto": 120,
    "data_prevista_estouro": "2026-10-15",
    "faturamento_seguro_mensal": 5131.47
  },

  "nivel_alerta": "risco",

  "serie_acumulada": [
    { "data": "2026-01-31", "acumulado": 4820.00, "referencia": 6879.45 }
  ],

  "projecao": [
    { "data": "2026-09-30", "provavel": 56100.00, "pessimista": 58900.00, "otimista": 54200.00 }
  ],

  "mensal": [
    { "mes": 8, "vendas": 9640.00, "despesas": 2100.00, "meta": 6750.00 }
  ],

  "concentracao_clientes": [
    { "cnpj": "12.345.678/0001-90", "nome": "Construtora Silva", "valor": 17975.00, "percentual": 38.0 }
  ],

  "calendario_fiscal": [
    { "tipo": "DAS", "competencia": "2026-08", "vence_em": "2026-09-20", "valor": 76.60, "situacao": "pendente" }
  ],

  "alertas": [
    {
      "id": "uuid",
      "nivel": "risco",
      "codigo": "projecao_estouro",
      "titulo": "No ritmo atual você atinge o teto em 15 de outubro",
      "detalhe": "Para chegar a dezembro dentro do limite, fature até R$ 5.131,47 por mês.",
      "acao": { "rotulo": "Ver simulação", "rota": "/simulador?valor=5131" },
      "disparado_em": "2026-08-22T09:00:00Z",
      "dispensavel": true
    }
  ]
}
```

```http
POST /insights/simular
{ "email": "...", "valor": 12000.00, "data": "2026-10-15", "tipo": "venda" }
```

Devolve o retrato antes e depois, a mudança de nível de alerta e a nova data
prevista de estouro.

---

## 6. Acessibilidade e desempenho

**Acessibilidade**

- Nenhum estado depende só de cor. Todo nível tem rótulo, ícone e — nos
  gráficos — padrão de preenchimento distinto (`ReferenceArea` com hachura).
- Contraste mínimo 4,5:1 para texto e 3:1 para elementos gráficos (WCAG 2.2 AA).
- Todo gráfico tem tabela equivalente, alcançável por teclado, marcada com
  `aria-describedby`. Ela também é o alvo dos testes automatizados, que assertam
  sobre valores e não sobre pixels.
- Navegação completa por teclado, com ordem de foco visível.
- Formatação em `pt-BR` para moeda, data e número.

**Desempenho**

| Alvo | Valor |
| --- | --- |
| `GET /insights/dashboard` (p95) | < 300 ms |
| Primeira pintura com conteúdo | < 1,5 s |
| Maior elemento visível | < 2,5 s |
| Deslocamento cumulativo de layout | < 0,1 |
| Peso do pacote adicionado por gráficos | < 120 KB comprimidos |

A série acumulada é agregada por dia no servidor. Enviar 38 transações é
irrelevante; enviar 3.000 não é — e o modelo de leitura já entrega agregado.

---

## 7. Como saberemos que ficou melhor

O dashboard v2 sobe atrás de flag com liberação percentual, o que permite
comparar as duas variantes com dados em vez de opinião.

| Métrica | Como medir | Meta |
| --- | --- | --- |
| Tempo até a primeira ação | Evento de interface, do carregamento ao primeiro clique útil | queda de 30% |
| Uso do simulador | Sessões que abrem o simulador | acima de 25% |
| Alertas dispensados sem ação | Razão entre dispensa e ação | abaixo de 40% |
| Lançamentos manuais | Transações com origem `manual` | qualquer valor acima de zero já supera o estado atual |
| Satisfação | Questionário SUS com 8 a 10 MEIs, comparando as variantes | acima de 75 |

O questionário SUS fornece o dado quantitativo de usabilidade que a seção de
resultados do artigo hoje descreve apenas de forma qualitativa.
