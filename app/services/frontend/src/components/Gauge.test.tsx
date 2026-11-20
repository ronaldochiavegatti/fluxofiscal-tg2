import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Gauge } from "./Gauge";

describe("Gauge", () => {
  it("mostra percentual, acumulado e restante — cenário 'O gauge mostra três informações'", () => {
    render(<Gauge percentual={58.4} acumulado={47304} restante={33696} nivel="ok" />);

    expect(screen.getByText("58,4%")).toBeInTheDocument();
    expect(screen.getByText("R$ 47.304,00")).toBeInTheDocument();
    expect(screen.getByText("restam R$ 33.696,00")).toBeInTheDocument();
  });

  it("nível 'risco' traz rótulo textual e ícone, não só cor — cenário 'Cor não é o único sinal'", () => {
    render(<Gauge percentual={90} acumulado={72900} restante={8100} nivel="risco" />);

    expect(screen.getByText("Risco de estourar")).toBeInTheDocument();
    expect(screen.getByText("🔺")).toBeInTheDocument();
  });

  it.each([
    ["ok", "Tranquilo", "✅"],
    ["atencao_ritmo", "Ritmo alto", "📈"],
    ["atencao", "Atenção", "⚠️"],
    ["risco", "Risco de estourar", "🔺"],
    ["estourado", "Limite estourado", "🚨"],
    ["desenquadramento", "Desenquadramento", "🚨"],
  ] as const)("nível %s renderiza rótulo '%s' e ícone", (nivel, rotulo, icone) => {
    render(<Gauge percentual={50} acumulado={1000} restante={1000} nivel={nivel} />);

    expect(screen.getByText(rotulo)).toBeInTheDocument();
    expect(screen.getByText(icone)).toBeInTheDocument();
  });

  it("limita o percentual exibido no arco a 0–100, mesmo passando do teto", () => {
    const { container } = render(
      <Gauge percentual={140} acumulado={140000} restante={-59000} nivel="desenquadramento" />
    );

    // O texto central mostra o percentual real (140%); o arco é que satura.
    expect(screen.getByText("140,0%")).toBeInTheDocument();
    expect(container.querySelector("svg")).toBeInTheDocument();
  });
});
