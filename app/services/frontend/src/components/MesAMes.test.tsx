import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MesAMes } from "./MesAMes";
import type { MesResumo } from "../types";

function mesResumo(mes: number, ajustes: Partial<MesResumo> = {}): MesResumo {
  return { mes, vendas: 0, despesas: 0, meta: 6750, acima_da_meta: false, ...ajustes };
}

const DOZE_MESES: MesResumo[] = Array.from({ length: 12 }, (_, i) => mesResumo(i + 1));

function tabela() {
  return screen.getByRole("table", { name: /vendas e despesas por mês/i });
}

describe("MesAMes", () => {
  it("mostra a meta mensal no texto de apoio", () => {
    render(<MesAMes mensal={DOZE_MESES} />);

    expect(screen.getByText(/meta mensal de R\$ 6\.750,00/)).toBeInTheDocument();
  });

  it("cenário 'Barras com linha de meta': tabela equivalente traz vendas e despesas por mês", () => {
    const mensal = DOZE_MESES.map((ponto) =>
      ponto.mes === 8 ? mesResumo(8, { vendas: 9640, despesas: 2100, acima_da_meta: true }) : ponto
    );
    render(<MesAMes mensal={mensal} />);

    const linhaAgosto = within(tabela()).getByText("ago").closest("tr");
    expect(linhaAgosto).not.toBeNull();
    expect(linhaAgosto).toHaveTextContent("R$ 9.640,00");
    expect(linhaAgosto).toHaveTextContent("R$ 2.100,00");
  });

  it("mês acima da meta é destacado na tabela, não só na cor da barra", () => {
    const mensal = DOZE_MESES.map((ponto) =>
      ponto.mes === 8 ? mesResumo(8, { vendas: 9640, acima_da_meta: true }) : ponto
    );
    render(<MesAMes mensal={mensal} />);

    const linhaAgosto = within(tabela()).getByText("ago").closest("tr");
    const linhaSetembro = within(tabela()).getByText("set").closest("tr");
    expect(linhaAgosto).toHaveTextContent("Sim");
    expect(linhaSetembro).toHaveTextContent("Não");
  });

  it("renderiza os doze meses, mesmo sem lançamento", () => {
    render(<MesAMes mensal={DOZE_MESES} />);

    const linhas = within(tabela()).getAllByRole("row");
    // 1 de cabeçalho + 12 meses
    expect(linhas).toHaveLength(13);
  });

  it("sem dados ainda (array vazio) não quebra", () => {
    const { container } = render(<MesAMes mensal={[]} />);

    expect(container.querySelector("svg")).toBeInTheDocument();
  });
});
