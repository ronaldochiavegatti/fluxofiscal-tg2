/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: "0.0.0.0",
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/main.tsx",
        "src/vite-env.d.ts",
        "src/test/**",
        "**/*.test.{ts,tsx}",
      ],
      // US-05: a meta global de 70% ainda não foi atingida (as páginas, que
      // concentram o código, serão reescritas na Onda 4). Enquanto isso,
      // travamos por arquivo o que já está coberto, para nenhuma regressão
      // passar despercebida. Ver issue US-05.
      thresholds: {
        "src/format.ts": { statements: 95, branches: 90, functions: 100, lines: 95 },
        "src/api.ts": { statements: 85, branches: 75, functions: 90, lines: 85 },
        "src/hooks/useLocalStorage.ts": { statements: 90, branches: 80, functions: 90, lines: 90 },
      },
    },
  },
});
