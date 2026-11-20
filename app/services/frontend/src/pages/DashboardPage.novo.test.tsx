import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DashboardPage } from "./DashboardPage";
import type { Ritmo, Summary } from "../types";

// Painel no visual novo (flag `visual-novo`): a régua substitui a fileira de
// cards e o gauge; o resto da página continua.

const api = vi.hoisted(() => ({
  getSummary: vi.fn(),
  getTransactions: vi.fn(),
  getRitmo: vi.fn(),
  getSerieAcumulada: vi.fn(),
}));
vi.mock("../api", () => ({
  ...api,
  chatAgent: vi.fn(),
  getMensal: vi.fn(() => Promise.resolve([])),
  getConcentracao: vi.fn(() => Promise.resolve([])),
  getReportUrl: () => "/relatorio.pdf",
  resetAllData: vi.fn(),
}));
// dashboard-v2 desligado: só a régua (visual novo) pede o ritmo.
vi.mock("../flags/useFeatureFlag", () => ({ useFeatureFlag: () => false }));
vi.mock("../aparencia/AparenciaContext", () => ({ useAparencia: () => ({ visualNovo: true }) }));
vi.mock("../App", () => ({ useDocuments: () => ({ docs: [], clearDocs: vi.fn() }) }));
vi.mock("../TokensContext", () => ({
  useTokens: () => ({ balance: 1000, ilimitado: true, costs: { document_confirm: 15, chat_message: 5 } }),
}));

const USER = { name: "Demo User", email: "demo@mei.com" };

const RESUMO: Summary = {
  email: USER.email,
  year: 2026,
  total_revenue: 40500,
  total_despesas: 1200,
  saldo_liquido: 39300,
  annual_limit: 81000,
  remaining: 40500,
  exceeded: false,
  percent_used: 50,
  alert_level: "ok",
};

const RITMO = {
  year: 2026,
  limite_aplicavel: 81000,
  nivel: "ok",
  dias_decorridos: 146,
  total_dias_ano: 365,
  projecao_disponivel: true,
  projecao_anual: 76000,
  data_prevista_estouro: null,
} as unknown as Ritmo;

function renderizar() {
  return render(
    <MemoryRouter>
      <DashboardPage user={USER} />
    </MemoryRouter>
  );
}

beforeEach(() => {
  api.getTransactions.mockResolvedValue([]);
  api.getSerieAcumulada.mockResolvedValue([]);
});
afterEach(() => vi.clearAllMocks());

describe("DashboardPage — visual novo", () => {
  it("abre com a frase e a régua do limite, sem a fileira de cards antiga", async () => {
    api.getSummary.mockResolvedValue(RESUMO);
    api.getRitmo.mockResolvedValue(RITMO);
    renderizar();

    const frase = await screen.findByRole("heading", { level: 1 });
    expect(frase.textContent).toMatch(/Você faturou R\$\s40\.500 dos R\$\s81\.000/);
    expect(screen.getByRole("meter")).toBeInTheDocument();
    expect(await screen.findByText(/fecha 2026 em R\$\s76\.000/)).toBeInTheDocument();
    // Um único título principal na página.
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.queryByText("Faturamento anual (vendas)")).not.toBeInTheDocument();
    expect(screen.getByText("Despesas no ano")).toBeInTheDocument();
  });

  it("enquanto o resumo não chega, mostra o esqueleto e avisa que está carregando", () => {
    api.getSummary.mockReturnValue(new Promise(() => undefined));
    api.getRitmo.mockReturnValue(new Promise(() => undefined));
    renderizar();
    expect(screen.getByText("Carregando seus números…")).toBeInTheDocument();
    expect(document.querySelectorAll(".esqueleto").length).toBeGreaterThan(0);
  });

  it("o reset de dados abre um diálogo que fecha com Esc", async () => {
    api.getSummary.mockResolvedValue(RESUMO);
    api.getRitmo.mockResolvedValue(RITMO);
    renderizar();
    await screen.findByRole("meter");

    fireEvent.click(screen.getByRole("button", { name: "Resetar dados de teste" }));
    const dialogo = screen.getByRole("dialog", { name: "Resetar todos os dados de teste?" });
    expect(screen.getByRole("button", { name: "Apagar tudo" })).toBeDisabled();

    fireEvent.keyDown(dialogo, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
