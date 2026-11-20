import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CorridaContraLimite } from "./CorridaContraLimite";
import type { PontoSerieAcumulada, Ritmo } from "../types";

const RITMO_BASE: Ritmo = {
  email: "marcia@mei.com.br",
  year: 2026,
  limite_aplicavel: 81000,
  meses_de_atividade: null,
  proporcional: false,
  total_vendas: 47304,
  restante: 33696,
  percent_used: 58.4,
  nivel: "risco",
  dias_decorridos: 168,
  total_dias_ano: 365,
  taxa_diaria: 281.57,
  taxa_diaria_referencia: 221.92,
  taxa_diaria_recente: 321.33,
  taxa_diaria_90d: 300.1,
  indice_ritmo: 1.27,
  aceleracao: 1.14,
  tendencia: "acelerando",
  projecao_disponivel: true,
  motivo_indisponivel: null,
  projecao_anual: 102773.57,
  dias_ate_estouro: 120,
  data_prevista_estouro: "2026-10-15",
  faturamento_seguro_mes: 4813.71,
  influenciada_por_lancamento_atipico: false,
};

function serieAte(dia: number, valorPorDia: number): PontoSerieAcumulada[] {
  const pontos: PontoSerieAcumulada[] = [];
  for (let d = 1; d <= dia; d++) {
    const data = new Date(Date.UTC(2026, 0, d));
    const iso = `2026-${String(data.getUTCMonth() + 1).padStart(2, "0")}-${String(
      data.getUTCDate()
    ).padStart(2, "0")}`;
    pontos.push({ data: iso, acumulado: Math.round(valorPorDia * d * 100) / 100 });
  }
  return pontos;
}

describe("CorridaContraLimite", () => {
  it("renderiza o gráfico e a anotação de cruzamento — cenário 'O cruzamento é anotado'", () => {
    const serie = serieAte(168, 281.57);
    const { container } = render(<CorridaContraLimite ritmo={RITMO_BASE} serie={serie} />);

    expect(container.querySelector("svg")).toBeInTheDocument();
    expect(screen.getByText(/Estouro em 15\/10\/2026/)).toBeInTheDocument();
  });

  it("cenário 'Existe alternativa textual': tabela mensal com os mesmos valores", () => {
    const serie = serieAte(168, 281.57);
    render(<CorridaContraLimite ritmo={RITMO_BASE} serie={serie} />);

    expect(screen.getByText("Ver como tabela (alternativa ao gráfico)")).toBeInTheDocument();
    // Meses já decorridos (jan–jun) mostram acumulado real; dez ainda não chegou.
    const linhas = screen.getAllByRole("row");
    expect(linhas.length).toBeGreaterThan(1); // cabeçalho + 12 meses
  });

  it("cenário 'Dado insuficiente não projeta': sem cone, mostra o motivo", () => {
    const ritmoIndisponivel: Ritmo = {
      ...RITMO_BASE,
      projecao_disponivel: false,
      motivo_indisponivel: "dados insuficientes para projeção",
      data_prevista_estouro: null,
      dias_ate_estouro: null,
    };
    const serie = serieAte(18, 50); // 18 dias de histórico, como no cenário

    render(<CorridaContraLimite ritmo={ritmoIndisponivel} serie={serie} />);

    expect(screen.getByText("dados insuficientes para projeção")).toBeInTheDocument();
    expect(screen.queryByText(/Estouro em/)).not.toBeInTheDocument();
  });

  it("não anota cruzamento quando o estouro previsto cai fora do ano corrente", () => {
    const semEstouroNoAno: Ritmo = { ...RITMO_BASE, data_prevista_estouro: "2027-02-01" };
    const serie = serieAte(168, 100);

    render(<CorridaContraLimite ritmo={semEstouroNoAno} serie={serie} />);

    expect(screen.queryByText(/Estouro em/)).not.toBeInTheDocument();
  });

  it("sem transações ainda, mostra a tabela com traço em vez de quebrar", () => {
    render(
      <CorridaContraLimite
        ritmo={{ ...RITMO_BASE, projecao_disponivel: false, motivo_indisponivel: "dados insuficientes para projeção" }}
        serie={[]}
      />
    );

    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });
});
