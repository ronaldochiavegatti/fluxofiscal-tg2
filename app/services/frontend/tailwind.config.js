/** @type {import('tailwindcss').Config} */
// Sistema visual do frontend (ADR-0010). Este arquivo é o ÚNICO lugar onde cor
// literal (hexadecimal ou rgba) pode aparecer — todo o resto do `src/` referencia
// os tokens abaixo. O teste `src/theme.guard.test.ts` reprova qualquer `#rrggbb`
// que escape para um componente ou para o `index.css`.
//
// Os tokens apontam para variáveis CSS, não para o hex direto. Assim o mesmo
// nome de classe (`bg-fundo`, `text-acento`) serve a três paletas:
//
//   :root                                   visual atual (azul-noite + índigo)
//   :root[data-visual="novo"]               visual novo, tema claro ("papel")
//   :root[data-visual="novo"][data-tema="escuro"]   visual novo, tema escuro
//
// `data-visual` é ligado pela flag `visual-novo` (src/aparencia/); com ela
// desligada nada muda na tela. Ver docs/redesign-visual.md.
//
// Migração incremental: `preflight` desligado, então `@tailwind base` quase não
// emite nada e o `index.css` (todo em `@apply` sobre estes tokens) continua
// valendo.
const plugin = require("tailwindcss/plugin");

/** "#1f3fb0" -> "31 63 176" (canais para `rgb(var(--x) / <alpha-value>)`). */
function canais(hex) {
  const h = hex.replace("#", "");
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)).join(" ");
}

const PALETAS = {
  // Visual atual — valores idênticos aos de antes da flag.
  atual: {
    canal: {
      fundo: "#0a0e1a", "fundo-elevado": "#141a2e", "fundo-card": "#111729", "fundo-poco": "#070a14",
      tinta: "#e7eaf3", "tinta-forte": "#ffffff", "tinta-leve": "#c5cbdc", "tinta-nav": "#a9b1c7", "tinta-suave": "#8a93ab",
      acento: "#818cf8", "acento-claro": "#a5b4fc", "acento-brilho": "#c4b5fd", "acento-ciano": "#22d3ee",
      "limite-ok": "#4ade80", "limite-ok-forte": "#22c55e",
      "limite-atencao": "#fbbf24", "limite-atencao-forte": "#f97316",
      "limite-risco": "#fb923c", "limite-risco-forte": "#ea580c",
      "limite-estourado": "#fca5a5", "limite-estourado-forte": "#f87171",
      veu: "#ffffff", "sobre-acento": "#ffffff",
    },
    bruto: {
      "--c-borda": "rgba(255,255,255,0.08)",
      "--c-borda-sutil": "rgba(255,255,255,0.05)",
      "--c-borda-forte": "rgba(255,255,255,0.14)",
      "--c-limite-ok-suave": "rgba(34,197,94,0.15)",
      "--c-limite-atencao-suave": "rgba(251,191,36,0.12)",
      "--c-limite-atencao-borda": "rgba(251,191,36,0.4)",
      "--c-limite-estourado-suave": "rgba(248,113,113,0.1)",
      "--c-limite-estourado-borda": "rgba(248,113,113,0.4)",
      "--img-app":
        "radial-gradient(900px 600px at 0% 0%, rgba(99,102,241,0.16), transparent 60%), radial-gradient(800px 500px at 100% 100%, rgba(34,211,238,0.08), transparent 60%)",
      "--img-sidebar": "linear-gradient(180deg, rgba(20,26,46,0.85) 0%, rgba(10,14,26,0.85) 100%)",
      "--img-cta": "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)",
      "--img-marca": "linear-gradient(135deg, #6366f1 0%, #8b5cf6 55%, #22d3ee 100%)",
      "--img-perigo": "linear-gradient(120deg, #f87171, #dc2626)",
      "--img-progresso": "linear-gradient(90deg, #6366f1, #22d3ee)",
      "--img-chat-me": "linear-gradient(135deg, rgba(99,102,241,0.22), rgba(139,92,246,0.18))",
      "--img-login-brilho":
        "radial-gradient(700px 500px at 15% 10%, rgba(99,102,241,0.25), transparent 60%), radial-gradient(600px 400px at 90% 90%, rgba(34,211,238,0.12), transparent 60%)",
      "--sombra-card": "inset 0 1px 0 rgba(255,255,255,0.04), 0 16px 40px -18px rgba(0,0,0,0.7)",
      "--sombra-cta": "0 10px 24px -8px rgba(99,102,241,0.55)",
      "--sombra-foco": "0 0 0 3px rgba(129,140,248,0.35)",
      "--raio-card": "18px",
      "--raio-campo": "12px",
      "--fonte-sans": '"Inter", "Segoe UI", system-ui, sans-serif',
      "--fonte-display": '"Plus Jakarta Sans", "Inter", sans-serif',
    },
  },

  // Visual novo, tema claro: papel de formulário e tinta de caneta azul. O
  // azul (`acento`) é reservado a ação — link, botão, foco.
  novoClaro: {
    canal: {
      fundo: "#f5f6f2", "fundo-elevado": "#ffffff", "fundo-card": "#ffffff", "fundo-poco": "#ecede7",
      tinta: "#1a1d23", "tinta-forte": "#12151b", "tinta-leve": "#3a3f48", "tinta-nav": "#4a505b", "tinta-suave": "#5b606b",
      acento: "#1f3fb0", "acento-claro": "#1f3fb0", "acento-brilho": "#3552c9", "acento-ciano": "#0e7490",
      "limite-ok": "#1e7a4c", "limite-ok-forte": "#17633d",
      "limite-atencao": "#9a6412", "limite-atencao-forte": "#b7791f",
      "limite-risco": "#c2410c", "limite-risco-forte": "#9a3412",
      "limite-estourado": "#b42318", "limite-estourado-forte": "#912018",
      veu: "#1a1d23", "sobre-acento": "#ffffff",
    },
    bruto: {
      "--c-borda": "#e2e3dd",
      "--c-borda-sutil": "#ecede7",
      "--c-borda-forte": "#cdcfc6",
      "--c-limite-ok-suave": "rgba(30,122,76,0.10)",
      "--c-limite-atencao-suave": "rgba(183,121,31,0.12)",
      "--c-limite-atencao-borda": "rgba(183,121,31,0.45)",
      "--c-limite-estourado-suave": "rgba(180,35,24,0.08)",
      "--c-limite-estourado-borda": "rgba(180,35,24,0.40)",
      "--sombra-foco": "0 0 0 3px rgba(31,63,176,0.28)",
      "--sombra-flutuante": "0 12px 32px -12px rgba(26,29,35,0.25)",
    },
  },

  novoEscuro: {
    canal: {
      fundo: "#15181d", "fundo-elevado": "#1d2128", "fundo-card": "#1d2128", "fundo-poco": "#101216",
      tinta: "#e8e9e4", "tinta-forte": "#f7f7f3", "tinta-leve": "#c9cbc4", "tinta-nav": "#b4b7b0", "tinta-suave": "#9ea3ad",
      acento: "#8fa6ff", "acento-claro": "#a9baff", "acento-brilho": "#b9c6ff", "acento-ciano": "#5ec4d6",
      "limite-ok": "#4cc38a", "limite-ok-forte": "#3ba673",
      "limite-atencao": "#e3b04b", "limite-atencao-forte": "#d29a2a",
      "limite-risco": "#f08a4b", "limite-risco-forte": "#d9702f",
      "limite-estourado": "#f2877e", "limite-estourado-forte": "#e5645a",
      veu: "#e8e9e4", "sobre-acento": "#15181d",
    },
    bruto: {
      "--c-borda": "#2c313a",
      "--c-borda-sutil": "#242830",
      "--c-borda-forte": "#3a404a",
      "--c-limite-ok-suave": "rgba(76,195,138,0.14)",
      "--c-limite-atencao-suave": "rgba(227,176,75,0.14)",
      "--c-limite-atencao-borda": "rgba(227,176,75,0.45)",
      "--c-limite-estourado-suave": "rgba(242,135,126,0.12)",
      "--c-limite-estourado-borda": "rgba(242,135,126,0.45)",
      "--sombra-foco": "0 0 0 3px rgba(143,166,255,0.35)",
      "--sombra-flutuante": "0 12px 32px -12px rgba(0,0,0,0.6)",
    },
  },
};

// Partes do visual novo que não mudam entre claro e escuro: sem gradiente,
// sem sombra decorativa, raio menor, uma família tipográfica só.
const NOVO_COMUM = {
  "--img-app": "none",
  "--img-sidebar": "none",
  "--img-login-brilho": "none",
  "--img-cta": "linear-gradient(rgb(var(--c-acento)), rgb(var(--c-acento)))",
  "--img-marca": "linear-gradient(rgb(var(--c-acento)), rgb(var(--c-acento)))",
  "--img-perigo": "linear-gradient(rgb(var(--c-limite-estourado)), rgb(var(--c-limite-estourado)))",
  "--img-progresso": "linear-gradient(rgb(var(--c-acento)), rgb(var(--c-acento)))",
  "--img-chat-me": "linear-gradient(rgb(var(--c-acento) / 0.08), rgb(var(--c-acento) / 0.08))",
  "--sombra-card": "none",
  "--sombra-cta": "none",
  "--raio-card": "10px",
  "--raio-campo": "6px",
  "--fonte-sans": '"Instrument Sans", "Segoe UI", system-ui, sans-serif',
  "--fonte-display": '"Instrument Sans", "Segoe UI", system-ui, sans-serif',
};

function variaveis({ canal, bruto }) {
  const saida = { ...bruto };
  for (const [nome, hex] of Object.entries(canal)) saida[`--c-${nome}`] = canais(hex);
  return saida;
}

const comCanal = (nome) => `rgb(var(--c-${nome}) / <alpha-value>)`;
const cor = (nome) => `var(--c-${nome})`;

module.exports = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  corePlugins: {
    preflight: false,
  },
  theme: {
    extend: {
      colors: {
        fundo: {
          DEFAULT: comCanal("fundo"),
          elevado: comCanal("fundo-elevado"),
          card: comCanal("fundo-card"),
          poco: comCanal("fundo-poco"),
        },
        tinta: {
          DEFAULT: comCanal("tinta"),
          forte: comCanal("tinta-forte"),
          leve: comCanal("tinta-leve"),
          nav: comCanal("tinta-nav"),
          suave: comCanal("tinta-suave"),
        },
        borda: {
          DEFAULT: cor("borda"),
          sutil: cor("borda-sutil"),
          forte: cor("borda-forte"),
        },
        acento: {
          DEFAULT: comCanal("acento"),
          claro: comCanal("acento-claro"),
          brilho: comCanal("acento-brilho"),
          ciano: comCanal("acento-ciano"),
        },
        // Véu: a cor usada em camadas translúcidas (`bg-veu/[0.04]`). Branco no
        // tema escuro, tinta no claro — o que `bg-white/[...]` não conseguia.
        veu: comCanal("veu"),
        // Texto sobre um fundo de acento sólido (botão primário, avatar).
        "sobre-acento": comCanal("sobre-acento"),
        // Paleta de estados do limite anual — docs/dashboard-v2.md (níveis
        // ok / atencao / risco / estourado). Cor nunca é o único sinal: todo
        // estado também carrega rótulo e ícone.
        "limite-ok": { DEFAULT: comCanal("limite-ok"), forte: comCanal("limite-ok-forte"), suave: cor("limite-ok-suave") },
        "limite-atencao": {
          DEFAULT: comCanal("limite-atencao"),
          forte: comCanal("limite-atencao-forte"),
          suave: cor("limite-atencao-suave"),
          borda: cor("limite-atencao-borda"),
        },
        "limite-risco": { DEFAULT: comCanal("limite-risco"), forte: comCanal("limite-risco-forte") },
        "limite-estourado": {
          DEFAULT: comCanal("limite-estourado"),
          forte: comCanal("limite-estourado-forte"),
          suave: cor("limite-estourado-suave"),
          borda: cor("limite-estourado-borda"),
        },
      },
      backgroundImage: {
        app: "var(--img-app)",
        sidebar: "var(--img-sidebar)",
        cta: "var(--img-cta)",
        marca: "var(--img-marca)",
        perigo: "var(--img-perigo)",
        progresso: "var(--img-progresso)",
        "chat-me": "var(--img-chat-me)",
        "login-brilho": "var(--img-login-brilho)",
      },
      fontFamily: {
        sans: "var(--fonte-sans)",
        display: "var(--fonte-display)",
      },
      borderRadius: {
        card: "var(--raio-card)",
        campo: "var(--raio-campo)",
      },
      boxShadow: {
        card: "var(--sombra-card)",
        cta: "var(--sombra-cta)",
        foco: "var(--sombra-foco)",
        flutuante: "var(--sombra-flutuante, var(--sombra-card))",
      },
    },
  },
  plugins: [
    plugin(({ addBase }) => {
      addBase({
        ":root": variaveis(PALETAS.atual),
        ':root[data-visual="novo"]': { ...NOVO_COMUM, ...variaveis(PALETAS.novoClaro), colorScheme: "light" },
        ':root[data-visual="novo"][data-tema="escuro"]': { ...variaveis(PALETAS.novoEscuro), colorScheme: "dark" },
      });
    }),
  ],
};
