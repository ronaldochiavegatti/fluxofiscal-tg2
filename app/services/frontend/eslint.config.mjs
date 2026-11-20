import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "coverage", "node_modules"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,

      // Desligada de propósito. A regra existe para preservar a granularidade
      // do Fast Refresh em desenvolvimento, e reclama de arquivos que exportam
      // um componente junto de outra coisa. Os dois casos aqui são um contexto
      // exportado ao lado do seu hook `useX` — padrão idiomático do React, e
      // separá-los em arquivos distintos só para agradar a ferramenta pioraria
      // a leitura sem ganho de correção.
      "react-refresh/only-export-components": "off",

      // Variável não usada é erro, exceto quando prefixada com _, que é a
      // convenção para "recebi mas não preciso".
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],

      // `any` derrota o propósito de usar TypeScript num sistema que lida com
      // dado fiscal. Vira erro quando os tipos da API estiverem completos
      // (US-04); por ora avisa.
      "@typescript-eslint/no-explicit-any": "warn",

      // Regra de domínio, não de estilo: valor monetário passa por formatBRL.
      // `toLocaleString` espalhado foi o que produziu a inconsistência em que
      // o limite anual renderizava sem centavos.
      "no-restricted-syntax": [
        "warn",
        {
          selector:
            "CallExpression[callee.property.name='toLocaleString'][arguments.0.value='pt-BR']",
          message:
            "Use formatBRL ou formatNumeroBr de src/format.ts em vez de toLocaleString direto.",
        },
      ],
    },
  },
  {
    // format.ts é o lugar onde a formatação deve morar. Proibir toLocaleString
    // ali seria proibir a própria implementação.
    files: ["src/format.ts"],
    rules: { "no-restricted-syntax": "off" },
  },
  {
    // Testes podem usar utilitários que não fazem sentido em código de produção.
    files: ["**/*.test.{ts,tsx}", "src/test/**"],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
      "no-restricted-syntax": "off",
    },
  },
);
