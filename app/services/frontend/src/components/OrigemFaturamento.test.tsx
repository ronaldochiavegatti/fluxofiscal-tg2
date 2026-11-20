import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { OrigemFaturamento } from "./OrigemFaturamento";
import type { ConcentracaoCliente } from "../types";

function item(ajustes: Partial<ConcentracaoCliente>): ConcentracaoCliente {
  return {
    cnpj: "12.345.678/0001-90",
    nome: null,
    valor: 1000,
    percentual: 10,
    alerta: false,
    ...ajustes,
  };
}

describe("OrigemFaturamento", () => {
  it("sem cliente identificado, mostra mensagem em vez de lista vazia", () => {
    render(<OrigemFaturamento concentracao={[]} />);

    expect(screen.getByText(/nenhuma venda com cliente identificado/i)).toBeInTheDocument();
  });

  it("cenário 'Concentração é sinalizada': CNPJ de 38% aparece no topo com o percentual", () => {
    render(
      <OrigemFaturamento
        concentracao={[
          item({ cnpj: "outro/cliente", percentual: 62 }),
          item({ cnpj: "12.345.678/0001-90", percentual: 38 }),
        ]}
      />
    );

    expect(screen.getByText("38,0%")).toBeInTheDocument();
    expect(screen.getByText("12.345.678/0001-90")).toBeInTheDocument();
  });

  it("aviso de concentração aparece quando um item ultrapassa 70%", () => {
    render(
      <OrigemFaturamento
        concentracao={[
          item({ cnpj: "12.345.678/0001-90", percentual: 75, alerta: true }),
          item({ cnpj: "outro/cliente", percentual: 25 }),
        ]}
      />
    );

    expect(screen.getByText(/vem de um só cliente/i)).toBeInTheDocument();
  });

  it("sem nenhum item acima de 70%, não mostra o aviso", () => {
    render(
      <OrigemFaturamento
        concentracao={[
          item({ cnpj: "a", percentual: 38 }),
          item({ cnpj: "b", percentual: 62 }),
        ]}
      />
    );

    expect(screen.queryByText(/vem de um só cliente/i)).not.toBeInTheDocument();
  });

  it("usa o nome quando disponível, em vez do CNPJ", () => {
    render(<OrigemFaturamento concentracao={[item({ nome: "Construtora Silva" })]} />);

    expect(screen.getByText("Construtora Silva")).toBeInTheDocument();
  });
});

describe("OrigemFaturamento — interação", () => {
  it("passar o mouse num cliente da lista mostra o percentual dele no centro do donut", () => {
    render(
      <OrigemFaturamento
        concentracao={[
          { cnpj: "11.111.111/0001-11", nome: null, valor: 600, percentual: 60, alerta: false },
          { cnpj: "22.222.222/0001-22", nome: null, valor: 400, percentual: 40, alerta: false },
        ]}
      />,
    );
    expect(screen.getByText("clientes")).toBeInTheDocument();

    const item = screen.getByText("22.222.222/0001-22").closest("li") as HTMLElement;
    fireEvent.mouseEnter(item);
    expect(screen.getAllByText("40,0%")).toHaveLength(2);
    expect(screen.getAllByText("22.222.222/0001-22")).toHaveLength(2);

    fireEvent.mouseLeave(item);
    expect(screen.getByText("clientes")).toBeInTheDocument();
  });
});
