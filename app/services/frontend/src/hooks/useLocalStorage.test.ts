import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useLocalStorage } from "./useLocalStorage";

describe("useLocalStorage", () => {
  it("usa o valor padrão quando não há nada guardado", () => {
    const { result } = renderHook(() => useLocalStorage("chave", "padrão"));

    expect(result.current[0]).toBe("padrão");
  });

  it("lê o valor já guardado", () => {
    localStorage.setItem("chave", JSON.stringify("guardado"));

    const { result } = renderHook(() => useLocalStorage("chave", "padrão"));

    expect(result.current[0]).toBe("guardado");
  });

  it("persiste ao alterar", () => {
    const { result } = renderHook(() => useLocalStorage("chave", "inicial"));

    act(() => {
      result.current[1]("novo");
    });

    expect(result.current[0]).toBe("novo");
    expect(JSON.parse(localStorage.getItem("chave") ?? "null")).toBe("novo");
  });

  it("cai no padrão quando o conteúdo guardado é inválido", () => {
    // Acontece de verdade: uma versão anterior do app pode ter gravado outro
    // formato, ou o usuário pode ter editado o localStorage à mão.
    localStorage.setItem("chave", "{isso não é json}");

    const { result } = renderHook(() => useLocalStorage("chave", "padrão"));

    expect(result.current[0]).toBe("padrão");
  });

  it("funciona com objetos, não só strings", () => {
    const { result } = renderHook(() =>
      useLocalStorage("doc", { id: 1, nome: "nota" }),
    );

    act(() => {
      result.current[1]({ id: 2, nome: "recibo" });
    });

    expect(result.current[0]).toEqual({ id: 2, nome: "recibo" });
  });

  it("chaves diferentes não se misturam", () => {
    const a = renderHook(() => useLocalStorage("a", "valor-a"));
    const b = renderHook(() => useLocalStorage("b", "valor-b"));

    act(() => {
      a.result.current[1]("alterado");
    });

    expect(a.result.current[0]).toBe("alterado");
    expect(b.result.current[0]).toBe("valor-b");
  });
});
