import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatCard } from "./StatCard";
import { formatBRL } from "../format";

describe("StatCard", () => {
  it("mostra título e valor", () => {
    render(<StatCard title="Faturamento anual (vendas)" value="R$ 47.304,50" />);

    expect(screen.getByText("Faturamento anual (vendas)")).toBeInTheDocument();
    expect(screen.getByText("R$ 47.304,50")).toBeInTheDocument();
  });

  it("mostra o texto de apoio quando informado", () => {
    render(<StatCard title="Despesas" value="R$ 0,00" helper="Não conta para o limite" />);

    expect(screen.getByText("Não conta para o limite")).toBeInTheDocument();
  });

  it("omite o texto de apoio quando ausente", () => {
    const { container } = render(<StatCard title="Vendas" value="R$ 1,00" />);

    // Título e valor apenas: nenhum terceiro bloco de texto.
    expect(container.querySelectorAll("div.card > div")).toHaveLength(2);
  });

  it("renderiza o valor já formatado pelo formatBRL", () => {
    // Garante que o contrato entre a formatação e o componente se mantém: se
    // formatBRL mudar o separador ou o símbolo, este teste acusa.
    //
    // A asserção usa container.textContent em vez de getByText porque o Intl
    // separa "R$" do número com espaço não separável (U+00A0), e o normalizador
    // padrão da Testing Library o converte em espaço comum antes de comparar —
    // o que faz a busca por uma string que ainda contém U+00A0 nunca casar.
    const { container } = render(
      <StatCard title="Saldo líquido" value={formatBRL(35124)} />,
    );

    expect(container.textContent).toContain(formatBRL(35124));
  });
});
