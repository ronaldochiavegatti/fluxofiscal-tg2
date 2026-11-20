import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AparenciaProvider, URL_FONTE_VISUAL_NOVO } from "./AparenciaContext";
import { SeletorTema } from "./SeletorTema";
import { FlagsProvider } from "../flags/FlagsProvider";

// Sem Unleash configurado, a flag `visual-novo` cai no padrão — que o build
// local controla com VITE_VISUAL_NOVO.

function montar() {
  return render(
    <FlagsProvider>
      <AparenciaProvider>
        <SeletorTema />
      </AparenciaProvider>
    </FlagsProvider>
  );
}

beforeEach(() => {
  vi.stubEnv("VITE_UNLEASH_FRONTEND_URL", "");
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllEnvs();
  delete document.documentElement.dataset.visual;
  delete document.documentElement.dataset.tema;
  document.getElementById("fonte-visual-novo")?.remove();
});

describe("AparenciaProvider", () => {
  it("antes do Unleash responder, usa o último valor visto neste navegador (sem piscar o visual antigo)", () => {
    vi.stubEnv("VITE_VISUAL_NOVO", "");
    localStorage.setItem("visual-novo-ultimo", "true");
    montar();
    expect(document.documentElement.dataset.visual).toBe("novo");
  });

  it("guarda o valor em uso para a próxima carga", () => {
    vi.stubEnv("VITE_VISUAL_NOVO", "true");
    montar();
    expect(localStorage.getItem("visual-novo-ultimo")).toBe("true");
  });

  it("flag desligada: não marca o <html> e não mostra o seletor de tema", () => {
    vi.stubEnv("VITE_VISUAL_NOVO", "");
    montar();
    expect(document.documentElement.dataset.visual).toBeUndefined();
    expect(screen.queryByRole("radiogroup")).toBeNull();
    // Nenhuma requisição de fonte a mais para quem está no visual atual.
    expect(document.getElementById("fonte-visual-novo")).toBeNull();
  });

  it("flag ligada: carrega a fonte do visual novo uma única vez", () => {
    vi.stubEnv("VITE_VISUAL_NOVO", "true");
    montar();
    montar();
    const links = document.querySelectorAll("#fonte-visual-novo");
    expect(links).toHaveLength(1);
    expect((links[0] as HTMLLinkElement).href).toBe(URL_FONTE_VISUAL_NOVO);
  });

  it("flag ligada: marca o visual novo e segue o tema do sistema", () => {
    vi.stubEnv("VITE_VISUAL_NOVO", "true");
    montar();
    expect(document.documentElement.dataset.visual).toBe("novo");
    // jsdom não implementa matchMedia: sistema conta como claro.
    expect(document.documentElement.dataset.tema).toBe("claro");
    expect(screen.getByRole("radio", { name: "Sistema" }).getAttribute("aria-checked")).toBe("true");
  });

  it("escolher um tema aplica na hora e fica salvo", () => {
    vi.stubEnv("VITE_VISUAL_NOVO", "true");
    montar();
    fireEvent.click(screen.getByRole("radio", { name: "Escuro" }));
    expect(document.documentElement.dataset.tema).toBe("escuro");
    expect(localStorage.getItem("tema")).toBe('"escuro"');

    fireEvent.click(screen.getByRole("radio", { name: "Claro" }));
    expect(document.documentElement.dataset.tema).toBe("claro");
  });
});
