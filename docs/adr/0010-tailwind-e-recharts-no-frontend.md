# ADR-0010 — Tailwind CSS e Recharts no frontend

- **Data:** 2026-08-22
- **Estado:** Aceita

## Contexto

O artigo afirma, em três seções distintas, que a interface foi construída com
React e **Tailwind CSS**. O código não usa Tailwind: `package.json` traz apenas
`react`, `react-dom` e `react-router-dom`, e a estilização vive em 248 linhas de
CSS escrito à mão em `index.css`, complementadas por objetos de estilo embutidos
espalhados pelos componentes. Só o `DashboardPage.tsx` tem dezenas de blocos
`style={{ ... }}` com cores hexadecimais repetidas.

Essa divergência precisa ser resolvida em uma das duas direções: ou o código
passa a usar Tailwind, ou o artigo passa a descrever CSS puro.

O segundo problema é que o dashboard novo exige gráficos de verdade — gauge do
limite, área acumulada com linha de ritmo ideal, cone de projeção, barras
mensais com linha de meta — e hoje a única visualização existente é uma barra de
progresso feita com uma `div` de largura percentual.

## Decisão

**Migrar a estilização para Tailwind CSS**, alinhando o código ao artigo, e
adotar **Recharts** para as visualizações.

**Tailwind.** A migração é incremental: o `index.css` atual continua válido
enquanto os componentes forem convertidos um a um, protegidos pela flag
`dashboard-v2`. Um `tailwind.config.js` define os tokens do sistema visual —
paleta, escala tipográfica, raios, sombras — de modo que as cores hoje
espalhadas em hexadecimais passem a ter nome semântico (`limite-ok`,
`limite-atencao`, `limite-risco`, `limite-estourado`).

**Recharts** para os gráficos, pelos motivos abaixo:

- É construído sobre D3, mas expõe uma API declarativa em componentes React, o
  que combina com o restante da base de código.
- Renderiza SVG, o que dá gráficos nítidos em qualquer densidade de tela e
  legíveis por leitor de tela quando anotados corretamente.
- Cobre com folga o que o dashboard precisa: `AreaChart` para o acumulado,
  `ComposedChart` para barras mensais com linha de meta, `RadialBarChart` para o
  gauge, `ReferenceLine` para o ritmo ideal e `ReferenceArea` para o cone de
  projeção.
- Adiciona aproximadamente 100 KB comprimidos ao pacote, contra cerca de 330 KB
  do ECharts completo.

**Regras de visualização** que valem para todo gráfico da plataforma:

1. Cor nunca é o único portador de significado. Todo estado crítico também tem
   rótulo textual, ícone ou padrão de preenchimento — exigência de acessibilidade
   e boa prática de visualização de dados.
2. Todo valor monetário é formatado em português do Brasil, com separador de
   milhar e duas casas decimais.
3. Todo gráfico tem alternativa textual: uma tabela equivalente acessível por
   teclado, também usada nos testes automatizados, que assertam sobre os dados e
   não sobre pixels.
4. A paleta de estados é a mesma em todos os componentes, vinda dos tokens do
   Tailwind.

## Consequências

**A favor**

- Código e artigo passam a dizer a mesma coisa.
- Os estilos embutidos somem, e com eles a repetição de cores literais.
- Tokens de design tornam a paleta de alerta consistente entre dashboard,
  relatório em PDF e notificações.
- Recharts entrega os gráficos pedidos sem escrever D3 na mão.

**Contra**

- Migrar 6 páginas e 3 componentes é trabalho real e sem valor visível ao
  usuário. Mitigado fazendo a conversão junto com a reformulação do dashboard,
  que é onde a maior parte do CSS vive.
- Classes utilitárias deixam o JSX mais verboso. Mitigado extraindo componentes
  de apresentação para os padrões repetidos.
- Recharts tem limitações em gráficos muito customizados. Nenhum dos gráficos
  planejados esbarra nelas.

## Alternativas descartadas

**Tailwind com Apache ECharts.** ECharts é mais poderoso — gauges elaborados,
mapas de calor, animações ricas. Descartado pelo tamanho do pacote e por uma
integração com React menos idiomática, baseada em referência imperativa a um
elemento do DOM.

**Manter CSS puro e apenas adicionar gráficos.** Seria mais rápido, mas
manteria a contradição com o artigo ou exigiria reescrever três trechos do
texto já revisado.

**Chart.js.** Renderiza em canvas: mais leve, porém pior em acessibilidade e em
nitidez em telas de alta densidade.

## Referências

- Documentação do Tailwind CSS sobre tokens de tema.
- Documentação do Recharts.
- WCAG 2.2, critério 1.4.1 (uso de cor).
