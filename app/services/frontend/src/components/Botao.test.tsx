import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Botao, classesBotao } from "./Botao";

describe("Botao", () => {
  it("é primário por padrão e não envia formulário sem pedir", () => {
    render(<Botao>Salvar</Botao>);
    const botao = screen.getByRole("button", { name: "Salvar" });
    expect(botao.className).toContain("botao-primario");
    expect(botao.getAttribute("type")).toBe("button");
  });

  it("carregando: bloqueia clique e anuncia ocupado", () => {
    const aoClicar = vi.fn();
    render(
      <Botao carregando onClick={aoClicar}>
        Enviando
      </Botao>
    );
    const botao = screen.getByRole("button", { name: "Enviando" });
    expect(botao.hasAttribute("disabled")).toBe(true);
    expect(botao.getAttribute("aria-busy")).toBe("true");
    fireEvent.click(botao);
    expect(aoClicar).not.toHaveBeenCalled();
  });

  it("aplica variante e tamanho", () => {
    render(
      <Botao variante="perigo" tamanho="sm">
        Apagar
      </Botao>
    );
    expect(screen.getByRole("button").className).toContain("botao-perigo botao-sm");
  });

  it("classesBotao serve para links com a mesma aparência", () => {
    expect(classesBotao()).toBe("botao botao-primario");
    expect(classesBotao("secundario", "sm")).toBe("botao botao-secundario botao-sm");
  });
});
