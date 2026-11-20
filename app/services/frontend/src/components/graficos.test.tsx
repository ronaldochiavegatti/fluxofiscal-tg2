import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LegendaInterativa, TooltipCartao, useSeriesOcultas, type Serie } from "./graficos";

const SERIES: Serie[] = [
  { chave: "vendas", nome: "Vendas", cor: "var(--cor-vendas)" },
  { chave: "meta", nome: "Meta", cor: "var(--cor-meta)", tracejada: true },
];

function Legenda() {
  const [ocultas, alternar] = useSeriesOcultas();
  return <LegendaInterativa series={SERIES} ocultas={ocultas} onAlternar={alternar} />;
}

describe("LegendaInterativa", () => {
  it("clicar alterna a série entre visível e oculta", () => {
    render(<Legenda />);
    const vendas = screen.getByRole("button", { name: /vendas/i });
    expect(vendas).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(vendas);
    expect(vendas).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: /meta/i })).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(vendas);
    expect(vendas).toHaveAttribute("aria-pressed", "true");
  });
});

describe("TooltipCartao", () => {
  it("inativo não renderiza nada", () => {
    const { container } = render(<TooltipCartao active={false} payload={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("mostra título formatado, valores em reais, faixa e rodapé", () => {
    render(
      <TooltipCartao
        active
        label="2026-08-10"
        titulo={(l) => `dia ${l}`}
        payload={[
          { dataKey: "vendas", name: "Vendas", value: 1500, color: "red" },
          { dataKey: "faixa", name: "Cone", value: [100, 200], color: "blue" },
          { dataKey: "vazio", name: "Vazio", value: undefined },
        ]}
        rodape={(itens) => <span>{itens.length} séries</span>}
      />,
    );
    expect(screen.getByText("dia 2026-08-10")).toBeInTheDocument();
    expect(screen.getByText("R$ 1.500,00")).toBeInTheDocument();
    expect(screen.getByText("R$ 100,00 – R$ 200,00")).toBeInTheDocument();
    expect(screen.queryByText("Vazio")).not.toBeInTheDocument();
    expect(screen.getByText("2 séries")).toBeInTheDocument();
  });
});
