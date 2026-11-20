# Redesign visual (flag `visual-novo`)

Identidade nova do frontend para a apresentação do TG II. Fica atrás da flag
`visual-novo` (declarada em `docs/feature-flags.yaml`); com ela desligada o
visual atual não muda.

## Por que mudar

O visual atual (fundo azul-noite, gradientes índigo → violeta → ciano, Inter +
Plus Jakarta Sans, cards iguais com sombra, rótulos em caixa alta, emojis como
ícone) é o conjunto de escolhas padrão de interfaces geradas por IA. Nada nele
vem do assunto do produto.

## Direção

**Para quem:** o microempreendedor que não é contador e abre o sistema com uma
pergunta: "estou perto do limite de R$ 81 mil? meu ritmo está ok?".

**Vocabulário visual:** papelada fiscal: papel de formulário, tinta preta,
caneta azul preenchendo campos.

| Token | Claro | Escuro | Uso |
| --- | --- | --- | --- |
| `fundo` (papel) | `#F5F6F2` | `#15181D` | fundo da página |
| `fundo-elevado` (folha) | `#FFFFFF` | `#1D2128` | superfícies |
| `tinta` | `#1A1D23` | `#E8E9E4` | texto |
| `tinta-suave` | `#5B606B` | `#9EA3AD` | texto secundário |
| `acento` (caneta) | `#1F3FB0` | `#8FA6FF` | **só** ação: link, botão, foco |
| `borda` (linha) | `#E2E3DD` | `#2C313A` | bordas e divisões |

Estados do limite: ok `#1E7A4C`, atenção `#9A6412`/`#B7791F`, risco `#C2410C`,
estourado `#B42318` (tons mais claros no escuro). Cor nunca é o único sinal.

**Tipo:** uma família, Instrument Sans. Valores em R$ usam a largura condensada
(`font-stretch: 80%`) com algarismos tabulares (classe `.valor`). Sem caixa alta
em rótulos.

**Elemento central:** a régua do limite (`components/ReguaLimite.tsx`), que
substitui gauge + fileira de KPIs no topo do painel: uma frase que responde a
pergunta, e a régua de 12 meses com o marcador de "hoje" (a mesma referência
linear do gráfico de corrida).

**Movimento:** um único movimento automático (a régua se preenche ao abrir o
painel). O resto responde a ação (botão pressionado, carregando). Tudo respeita
`prefers-reduced-motion`.

## Como funciona

- `tailwind.config.js` define três paletas como variáveis CSS (`:root`,
  `[data-visual="novo"]`, `[data-visual="novo"][data-tema="escuro"]`). Os nomes
  de token não mudaram, então componentes antigos pegam a paleta nova sem
  alteração. Hex continua só nesse arquivo (`theme.guard.test.ts`).
- `src/aparencia/AparenciaContext.tsx` lê a flag, aplica `data-visual` e
  `data-tema` no `<html>` e guarda a preferência de tema (claro / escuro /
  sistema) no navegador.
- `src/components/Botao.tsx` é o botão padrão (primário, secundário, discreto,
  perigo; estados de hover, foco, pressionado, desabilitado, carregando).
  `classesBotao()` dá a mesma aparência a `<Link>`/`<a>`.
- `.esqueleto` (index.css) é o placeholder de carregamento no formato do
  conteúdo.

## O que muda mesmo com a flag desligada

A regra é "flag desligada = visual atual intacto". Estas exceções são
intencionais:

- Nome do produto: "FiscalFlow" virou **FluxoFiscal** no título da aba, no menu
  e no login (correção do nome do projeto).
- Gráfico de corrida contra o limite: rótulos do eixo no dia 1º de cada mês
  (antes "Jan" aparecia duas vezes) e, abaixo de 520 px, um a cada três meses.
- `bg-white/[x]` virou `bg-veu/[x]`: no visual atual o token `veu` é branco,
  então a tela é a mesma.
- Tabelas ficam dentro de `.tabela-rolavel` (rolam no próprio painel em
  tela estreita).

Também valem com a flag desligada, mas vêm do frontend que já estava pendente
antes do redesign (primeiro commit do PR, não do visual novo): atualização
automática do painel a cada 60 s e ao voltar para a aba, resumo do agente só
quando pedido, navegação por mês e filtro venda/compra na movimentação, e as
dependências `react-markdown` e `remark-gfm` para formatar a resposta do agente
(sem HTML cru: não há `rehype-raw`).

A fonte Instrument Sans só é pedida ao Google Fonts com a flag ligada
(`AparenciaContext`); com ela desligada não há requisição a mais.

## Dívida conhecida

- A régua repete a conta da "referência linear de hoje"
  (`limite × dias_decorridos / total_dias_ano`), que o gráfico de corrida já
  fazia no frontend, e decide no cliente se o estouro previsto cai no ano
  corrente. Pelo CLAUDE.md isso deveria vir do `limits`: issue #87.

## Ligar localmente

Com o Unleash da pilha local no ar: a flag `visual-novo` já existe no projeto
`default`, ligada em `development` (http://localhost:4242). Sem Unleash, o build
com `VITE_VISUAL_NOVO=true` usa o visual novo como padrão.

## Interação e retorno visual (fase 2)

Regras da skill `ui-ux-pro-max` aplicadas (consultas `--domain ux`):

| Regra | Onde |
| --- | --- |
| Progresso em fluxo de várias etapas ("Etapa 2 de 4") | `Etapas` no envio de nota |
| Espera longa explicada, sem tela congelada nem spinner piscando | `ProgressoIndeterminado` + tempo decorrido no envio e no agente |
| Confirmar ação concluída, aviso some sozinho em 3-5 s | `Avisos` (toast de 4,5 s) ao salvar nota |
| Esqueleto no formato do conteúdo | painel, documentos |
| Estado vazio com mensagem e ação | `EstadoVazio` em documentos |
| Erro com próximo passo, perto do campo | envio, conferência, agente ("Tentar de novo") |
| Toque mínimo de 44 px, foco visível | `Botao`, `.escolha`, seletor de tema |
| Números formatados e alinhados | `.valor`, `.num`, `tabular-nums` |
| Sem rolagem horizontal no celular | `minmax(0, 1fr)` no grid; menu vira faixa + gaveta |

Contraste conferido: todos os pares de texto principais ficam acima de 4,5:1
nos dois temas.

Componentes novos: `components/interacao.tsx` (`CabecalhoPagina`, `Etapas`,
`ProgressoIndeterminado`, `useSegundos`, `EstadoVazio`) e
`components/Avisos.tsx` (`AvisosProvider`, `useAvisos`).

## Responsivo

| Faixa | Largura | Navegação | Margem lateral |
| --- | --- | --- | --- |
| Celular | < 640 px | barra no topo + menu que abre por cima | 16 px |
| Tablet | 640-1023 px | barra no topo + menu que abre por cima | 24 px |
| Desktop | >= 1024 px | menu lateral fixo | 36 px |

O menu (`components/Layout.tsx`) abre pelo botão da barra do topo, fecha com
Esc (o foco volta ao botão), com toque no fundo escurecido ou ao escolher uma
tela, e trava a rolagem da página enquanto está aberto. Tabelas rolam dentro do
próprio painel (`.tabela-rolavel`); a grade usa `minmax(0, 1fr)` para nada
alargar a página. No gráfico de corrida, os rótulos ficam no dia 1º de cada mês
e, abaixo de 520 px, aparecem a cada três meses.

## Estado

- Fase 1 (feita): tokens, tema claro/escuro, botão, menu lateral, login,
  painel com a régua.
- Fase 2 (feita): envio de nota com etapas, progresso e conferência guiada;
  documentos com esqueleto, estado vazio e tabela legível; agente com
  indicador de espera e nova tentativa; avisos; menu compacto no celular;
  modal de reset acessível.
- Fora do escopo por enquanto: tela de detalhe do documento e gráficos do
  painel (herdam só as cores novas).
