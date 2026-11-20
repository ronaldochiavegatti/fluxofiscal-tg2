import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PainelRitmo } from "./PainelRitmo";
import type { Ritmo } from "../types";

const BASE: Ritmo = {
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

describe("PainelRitmo", () => {
  it("mostra o índice de ritmo e a tendência — cenário 'Índice de ritmo com tendência'", () => {
    render(<PainelRitmo ritmo={BASE} />);

    expect(screen.getByText("1,27")).toBeInTheDocument();
    expect(screen.getByText(/acelerando/)).toBeInTheDocument();
    expect(screen.getByText("R$ 281,57")).toBeInTheDocument();
    expect(screen.getByText("R$ 221,92")).toBeInTheDocument();
  });

  it("mostra a projeção anual e os dias de folga com a data prevista", () => {
    render(<PainelRitmo ritmo={BASE} />);

    expect(screen.getByText("R$ 102.773,57")).toBeInTheDocument();
    expect(screen.getByText(/120 \(até 15\/10\/2026\)/)).toBeInTheDocument();
  });

  it.each([
    ["acelerando" as const, /acelerando/],
    ["estavel" as const, /estável/],
    ["desacelerando" as const, /desacelerando/],
  ])("tendência %s aparece com o rótulo correspondente", (tendencia, esperado) => {
    render(<PainelRitmo ritmo={{ ...BASE, tendencia }} />);

    expect(screen.getByText(esperado)).toBeInTheDocument();
  });

  it("sem projeção disponível, explica o motivo em vez de mostrar número", () => {
    render(
      <PainelRitmo
        ritmo={{
          ...BASE,
          projecao_disponivel: false,
          motivo_indisponivel: "dados insuficientes para projeção",
          indice_ritmo: null,
          projecao_anual: null,
          dias_ate_estouro: null,
          data_prevista_estouro: null,
        }}
      />
    );

    expect(screen.getByText("dados insuficientes para projeção")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("sinaliza quando a projeção foi influenciada por lançamento atípico", () => {
    render(<PainelRitmo ritmo={{ ...BASE, influenciada_por_lancamento_atipico: true }} />);

    expect(screen.getByText(/lançamento fora do padrão/)).toBeInTheDocument();
  });
});
