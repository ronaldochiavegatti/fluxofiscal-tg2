import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Markdown } from "./Markdown";

describe("Markdown", () => {
  it("formata negrito, lista e título em vez de mostrar os símbolos", () => {
    const { container } = render(
      <Markdown texto={"### Sua situação\n\n* **Faturamento:** R$ 1.000,00\n* Limite: R$ 81.000,00"} />,
    );

    expect(screen.getByText("Sua situação").tagName).toBe("H5");
    expect(screen.getByText("Faturamento:").tagName).toBe("STRONG");
    expect(container.querySelectorAll("li")).toHaveLength(2);
    expect(container.textContent).not.toContain("**");
    expect(container.textContent).not.toContain("###");
  });

  it("renderiza tabela no formato GFM", () => {
    render(<Markdown texto={"| Mês | Vendas |\n|---|---|\n| ago | R$ 10,00 |"} />);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("R$ 10,00")).toBeInTheDocument();
  });

  it("HTML vindo do modelo não vira marcação", () => {
    const { container } = render(<Markdown texto={'<img src="x" onerror="alert(1)"> oi'} />);
    expect(container.querySelector("img")).toBeNull();
  });
});
