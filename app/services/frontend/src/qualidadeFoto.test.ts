import { afterEach, describe, expect, it, vi } from "vitest";
import { avaliarArquivo, avaliarCinza, ehFoto, motivoDaRecusa, rgbaParaCinza } from "./qualidadeFoto";

// Mesmos cenários de `documents/tests/test_qualidade.py` (issue 100). A paridade
// numérica com o Pillow foi conferida sobre os mesmos pixels de uma foto real
// do lote de teste (nitidez, razão, brilho e contraste idênticos).

const L = 300;
const A = 200;

/** "Texto": linhas de traços escuros finos sobre papel claro. */
function texto(): Uint8ClampedArray {
  const px = new Uint8ClampedArray(L * A).fill(240);
  for (let y = 10; y < A - 10; y += 8) {
    for (let x = 10; x < L - 10; x++) {
      if ((x * 7 + y) % 11 < 5) {
        px[y * L + x] = 20;
        px[(y + 1) * L + x] = 20;
      }
    }
  }
  return px;
}

/** Desfoque de caixa repetido, para simular foto tremida. */
function borrar(px: Uint8ClampedArray, vezes: number): Uint8ClampedArray {
  let atual = px;
  for (let n = 0; n < vezes; n++) {
    const saida = new Uint8ClampedArray(atual);
    for (let y = 2; y < A - 2; y++) {
      for (let x = 2; x < L - 2; x++) {
        let s = 0;
        for (let j = -2; j <= 2; j++) for (let i = -2; i <= 2; i++) s += atual[(y + j) * L + (x + i)];
        saida[y * L + x] = s / 25;
      }
    }
    atual = saida;
  }
  return atual;
}

const uniforme = (tom: number) => new Uint8ClampedArray(L * A).fill(tom);

describe("avaliarCinza", () => {
  it("texto nítido é legível", () => {
    const a = avaliarCinza(texto(), L, A, 1200, 800);
    expect(a.legivel).toBe(true);
    expect(a.motivo).toBeNull();
    expect(a.razaoNitidez).toBeGreaterThan(1.1);
  });

  it.each([
    ["tremida", borrar(texto(), 3), 1200, 800],
    ["pequena", texto(), 300, 200],
    ["escura", uniforme(5), 1200, 800],
    ["estourada", uniforme(255), 1200, 800],
    ["sem_contraste", uniforme(128), 1200, 800],
  ] as const)("recusa foto %s", (motivo, px, largura, altura) => {
    const a = avaliarCinza(px, L, A, largura, altura);
    expect(a.legivel).toBe(false);
    expect(a.motivo).toBe(motivo);
  });

  it("o motivo mais fácil de corrigir vem primeiro", () => {
    expect(
      motivoDaRecusa({ nitidez: 1, razaoNitidez: 1, brilho: 5, contraste: 0, largura: 300, altura: 200 }),
    ).toBe("pequena");
  });
});

describe("auxiliares", () => {
  it("rgbaParaCinza usa os pesos do Pillow", () => {
    const rgba = new Uint8ClampedArray([255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255]);
    expect(Array.from(rgbaParaCinza(rgba))).toEqual([76, 150, 29]);
  });

  it("ehFoto reconhece imagem pelo tipo ou pela extensão", () => {
    expect(ehFoto(new File([], "a.jpg"))).toBe(true);
    expect(ehFoto(new File([], "camera", { type: "image/jpeg" }))).toBe(true);
    expect(ehFoto(new File([], "nota.pdf", { type: "application/pdf" }))).toBe(false);
    expect(ehFoto(new File([], "nota.txt"))).toBe(false);
  });
});

describe("avaliarArquivo", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sem createImageBitmap, não decide: o servidor confere", async () => {
    vi.stubGlobal("createImageBitmap", undefined);
    expect(await avaliarArquivo(new File([], "a.jpg"))).toBeNull();
  });

  it("imagem que não abre é recusada como inválida", async () => {
    vi.stubGlobal("createImageBitmap", () => Promise.reject(new Error("decode")));
    const a = await avaliarArquivo(new File([new Uint8Array([1, 2])], "a.jpg"));
    expect(a?.legivel).toBe(false);
    expect(a?.motivo).toBe("invalida");
  });

  it("sem canvas 2D (jsdom), não decide e libera o bitmap", async () => {
    const close = vi.fn();
    vi.stubGlobal("createImageBitmap", () => Promise.resolve({ width: 2000, height: 1500, close }));
    expect(await avaliarArquivo(new File([], "a.jpg"))).toBeNull();
    expect(close).toHaveBeenCalled();
  });
});
