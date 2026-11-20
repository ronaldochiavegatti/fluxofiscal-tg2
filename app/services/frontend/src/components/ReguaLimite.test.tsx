import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ReguaLimite } from "./ReguaLimite";
import type { Ritmo, Summary } from "../types";

const NBSP = " ";

function summary(parcial: Partial<Summary> = {}): Summary {
  return {
    email: "demo@mei.com",
    year: 2026,
    total_revenue: 40500,
    total_despesas: 1000,
    saldo_liquido: 39500,
    annual_limit: 81000,
    remaining: 40500,
    exceeded: false,
    percent_used: 50,
    alert_level: "ok",
    ...parcial,
  };
}

function ritmo(parcial: Partial<Ritmo> = {}): Ritmo {
  return {
    email: "demo@mei.com",
    year: 2026,
    limite_aplicavel: 81000,
    meses_de_atividade: null,
    proporcional: false,
    total_vendas: 40500,
    restante: 40500,
    percent_used: 50,
    nivel: "ok",
    dias_decorridos: 146,
    total_dias_ano: 365,
    taxa_diaria: 277,
    taxa_diaria_referencia: 222,
    taxa_diaria_recente: 277,
    taxa_diaria_90d: 277,
    indice_ritmo: 1.25,
    aceleracao: null,
    tendencia: "estavel",
    projecao_disponivel: true,
    motivo_indisponivel: null,
    projecao_anual: 76000,
    dias_ate_estouro: null,
    data_prevista_estouro: null,
    faturamento_seguro_mes: 3000,
    influenciada_por_lancamento_atipico: false,
    ...parcial,
  };
}

describe("ReguaLimite", () => {
  it("responde em frase quanto foi faturado e qual é o limite", () => {
    render(<ReguaLimite summary={summary()} />);
    const frase = screen.getByRole("heading", { level: 1 });
    expect(frase.textContent).toContain(`R$${NBSP}40.500`);
    expect(frase.textContent).toContain(`R$${NBSP}81.000`);
  });

  it("expõe o progresso como medidor acessível", () => {
    render(<ReguaLimite summary={summary()} />);
    const medidor = screen.getByRole("meter");
    expect(medidor.getAttribute("aria-valuenow")).toBe("40500");
    expect(medidor.getAttribute("aria-valuetext")).toBe(`R$${NBSP}40.500 de R$${NBSP}81.000`);
  });

  it("sem ritmo, diz quanto ainda cabe e não mostra o marcador de hoje", () => {
    render(<ReguaLimite summary={summary()} />);
    expect(screen.getByText(/Ainda cabem/)).toBeTruthy();
    expect(screen.queryByText(/linha reta/)).toBeNull();
  });

  it("com ritmo, mostra a projeção e a referência de hoje", () => {
    render(<ReguaLimite summary={summary()} ritmo={ritmo()} />);
    expect(screen.getByText(/fecha 2026 em R\$\s76\.000, dentro do limite/)).toBeTruthy();
    // 81.000 × 146/365 = 32.400
    expect(screen.getByText(/estaria em R\$\s32\.400/)).toBeTruthy();
    expect(screen.getByText("Dentro do limite")).toBeTruthy();
  });

  it("avisa a data prevista quando o ritmo leva a estourar", () => {
    render(
      <ReguaLimite
        summary={summary()}
        ritmo={ritmo({ nivel: "risco", data_prevista_estouro: "2026-11-20" })}
      />
    );
    expect(screen.getByText(/chega ao limite em 20\/11\/2026/)).toBeTruthy();
    expect(screen.getByText("Risco de passar do limite")).toBeTruthy();
  });

  it("estouro previsto só em outro ano: fala da projeção do ano, não da data distante", () => {
    render(<ReguaLimite summary={summary()} ritmo={ritmo({ data_prevista_estouro: "2031-11-04" })} />);
    expect(screen.queryByText(/2031/)).toBeNull();
    expect(screen.getByText(/dentro do limite\./)).toBeTruthy();
  });

  it("limite ultrapassado: diz quanto passou, trava a régua cheia e indica o próximo passo", () => {
    render(
      <ReguaLimite
        summary={summary({ total_revenue: 90000, remaining: -9000, exceeded: true, alert_level: "exceeded" })}
      />
    );
    expect(screen.getByText(/passou R\$\s9\.000 do limite/)).toBeTruthy();
    expect(screen.getByText(/contador/)).toBeTruthy();
    expect(screen.getByText("Limite ultrapassado")).toBeTruthy();
    expect(screen.getByRole("meter").getAttribute("aria-valuenow")).toBe("81000");
  });

  it("alerta do resumo vira faixa de atenção quando não há ritmo", () => {
    render(<ReguaLimite summary={summary({ alert_level: "warning" })} />);
    expect(screen.getByText("Atenção ao limite")).toBeTruthy();
  });
});
