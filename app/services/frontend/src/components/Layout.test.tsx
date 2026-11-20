import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Layout } from "./Layout";

// Menu responsivo do visual novo: abaixo de 1024 px vira barra no topo com
// botão que abre e fecha o menu.

vi.mock("../TokensContext", () => ({ useTokens: () => ({ balance: 10, ilimitado: true, loading: false }) }));
vi.mock("../useUserCnpj", () => ({ useUserCnpj: () => ["12.345.678/0001-90", vi.fn()] }));
vi.mock("../aparencia/AparenciaContext", () => ({
  useAparencia: () => ({ visualNovo: true, preferencia: "sistema", setPreferencia: vi.fn(), escuro: false }),
}));

function simularLargura(compacta: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({ matches: compacta, addEventListener: vi.fn(), removeEventListener: vi.fn() }))
  );
}

function montar() {
  return render(
    <MemoryRouter initialEntries={["/dashboard"]}>
      <Layout userEmail="demo@mei.com">
        <p>conteúdo</p>
      </Layout>
    </MemoryRouter>
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.style.overflow = "";
});

describe("Layout — menu responsivo", () => {
  it("no desktop o menu fica fixo, sem botão de abrir", () => {
    simularLargura(false);
    montar();
    expect(screen.queryByRole("button", { name: "Abrir menu" })).toBeNull();
    expect(document.getElementById("menu-principal")!.className).toBe("sidebar");
  });

  it("em tela compacta abre, trava a rolagem e fecha com Esc devolvendo o foco", () => {
    simularLargura(true);
    montar();
    const botao = screen.getByRole("button", { name: "Abrir menu" });
    expect(botao).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(botao);
    expect(screen.getByRole("button", { name: "Fechar menu" })).toHaveAttribute("aria-expanded", "true");
    expect(document.getElementById("menu-principal")!.className).toContain("menu-aberto");
    expect(document.body.style.overflow).toBe("hidden");
    expect(document.activeElement).toBe(screen.getByRole("link", { name: "Painel" }));

    fireEvent.keyDown(document, { key: "Escape" });
    expect(document.getElementById("menu-principal")!.className).not.toContain("menu-aberto");
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Abrir menu" }));
    expect(document.body.style.overflow).toBe("");
  });

  it("escolher uma tela no menu fecha o menu", () => {
    simularLargura(true);
    montar();
    fireEvent.click(screen.getByRole("button", { name: "Abrir menu" }));
    fireEvent.click(screen.getByRole("link", { name: "Documentos" }));
    expect(screen.getByRole("button", { name: "Abrir menu" })).toHaveAttribute("aria-expanded", "false");
  });
});
