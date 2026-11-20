import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Critério de aceite da US-24 (ADR-0010): "zero hexadecimal literal fora do
 * tailwind.config.js". Toda cor mora nos tokens do tema; um componente ou o
 * index.css que traga `#rrggbb` de volta reprova aqui.
 *
 * Lê os arquivos com `fs` (roda em Node, no Vitest) em vez de `import.meta.glob`
 * — o glob eager marcaria cada fonte como "carregada" e inflaria a cobertura.
 */

// Vitest roda com o diretório do serviço como cwd.
const SRC = join(process.cwd(), "src");
const HEX = /#[0-9a-fA-F]{3,8}\b/;
const ESTE_ARQUIVO = "theme.guard.test.ts";

function arquivosDeFonte(dir: string): string[] {
  const encontrados: string[] = [];
  for (const nome of readdirSync(dir)) {
    const caminho = join(dir, nome);
    if (statSync(caminho).isDirectory()) {
      encontrados.push(...arquivosDeFonte(caminho));
    } else if (/\.(ts|tsx|css)$/.test(nome) && nome !== ESTE_ARQUIVO) {
      encontrados.push(caminho);
    }
  }
  return encontrados;
}

describe("sistema visual", () => {
  it("não tem cor hexadecimal literal fora do tailwind.config.js", () => {
    const infratores: string[] = [];
    for (const arquivo of arquivosDeFonte(SRC)) {
      readFileSync(arquivo, "utf8")
        .split("\n")
        .forEach((linha, i) => {
          if (HEX.test(linha)) infratores.push(`${relative(SRC, arquivo)}:${i + 1}  ${linha.trim()}`);
        });
    }
    expect(infratores, `cor hexadecimal literal encontrada:\n${infratores.join("\n")}`).toEqual([]);
  });
});
