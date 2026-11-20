import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BarraProgresso } from "./BarraProgresso";

describe("BarraProgresso", () => {
  it("expõe o valor como progressbar e mostra os marcos rotulados", () => {
    render(<BarraProgresso percentual={42.4} rotulo="Limite anual" marcos={[{ em: 80, rotulo: "80%" }]} />);
    const barra = screen.getByRole("progressbar", { name: "Limite anual" });
    expect(barra).toHaveAttribute("aria-valuenow", "42");
    expect(screen.getByText("80%")).toBeInTheDocument();
  });

  it("acima de 100% trava no fim e muda para a cor de estouro", () => {
    render(<BarraProgresso percentual={130} rotulo="Limite" />);
    const barra = screen.getByRole("progressbar");
    expect(barra).toHaveAttribute("aria-valuenow", "100");
    expect(barra.firstElementChild).toHaveClass("!bg-limite-estourado");
  });

  it("entre 80% e 100% usa a cor de atenção; abaixo, a padrão", () => {
    const { rerender } = render(<BarraProgresso percentual={85} rotulo="L" fina />);
    expect(screen.getByRole("progressbar").firstElementChild).toHaveClass("!bg-limite-atencao");
    rerender(<BarraProgresso percentual={10} rotulo="L" />);
    expect(screen.getByRole("progressbar").firstElementChild).not.toHaveClass("!bg-limite-atencao");
  });
});
