// Vite lê este arquivo automaticamente. Tailwind processa as diretivas
// `@tailwind` de `src/index.css`; o autoprefixer cuida dos prefixos de
// fornecedor a partir do `browserslist` padrão.
module.exports = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
