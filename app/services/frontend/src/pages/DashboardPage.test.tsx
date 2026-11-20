import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DashboardPage } from "./DashboardPage";
import type { Summary } from "../types";

const api = vi.hoisted(() => ({
  getSummary: vi.fn(),
  getTransactions: vi.fn(),
  chatAgent: vi.fn(),
}));
vi.mock("../api", () => ({
  ...api,
  getRitmo: vi.fn(),
  getSerieAcumulada: vi.fn(),
  getMensal: vi.fn(),
  getConcentracao: vi.fn(),
  getReportUrl: () => "/relatorio.pdf",
  resetAllData: vi.fn(),
}));
// dashboard-v2 desligado: o teste cobre o que é da página, não os gráficos
// (cada um tem a própria suíte).
vi.mock("../flags/useFeatureFlag", () => ({ useFeatureFlag: () => false }));
vi.mock("../App", () => ({ useDocuments: () => ({ docs: [], clearDocs: vi.fn() }) }));
vi.mock("../TokensContext", () => ({
  useTokens: () => ({ balance: 1000, ilimitado: true, costs: { document_confirm: 15, chat_message: 5 } }),
}));

const USER = { name: "Demo User", email: "demo@mei.com" };

const resumo = (vendas: number, despesas = 0): Summary => ({
  email: USER.email,
  year: 2026,
  total_revenue: vendas,
  total_despesas: despesas,
  saldo_liquido: vendas - despesas,
  annual_limit: 81000,
  remaining: 81000 - vendas,
  exceeded: vendas > 81000,
  percent_used: (vendas / 81000) * 100,
  alert_level: "ok",
});

function renderizar() {
  return render(
    <MemoryRouter>
      <DashboardPage user={USER} />
    </MemoryRouter>,
  );
}

describe("DashboardPage", () => {
  beforeEach(() => {
    api.getTransactions.mockResolvedValue([]);
  });
  afterEach(() => vi.clearAllMocks());

  it("sem lançamentos, mostra o aviso de início sem esconder os indicadores de progresso", async () => {
    api.getSummary.mockResolvedValue(resumo(0));
    renderizar();

    expect(await screen.findByText(/Nenhum lançamento em \d{4} ainda/)).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Progresso do faturamento no ano" })).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Vendas do mês contra a meta mensal" })).toBeInTheDocument();
    expect(screen.getByText("Restam R$ 81.000,00")).toBeInTheDocument();
  });

  it("com vendas, mostra o progresso do ano e não o aviso de início", async () => {
    api.getSummary.mockResolvedValue(resumo(40500, 1200));
    api.getTransactions.mockResolvedValue([
      { id: 1, email: USER.email, amount: 3375, tx_date: "2026-10-05", source: "upload", tx_type: "venda" },
      { id: 2, email: USER.email, amount: 1200, tx_date: "2026-10-09", source: "upload", tx_type: "compra" },
    ]);
    renderizar();

    expect(await screen.findByText("Restam R$ 40.500,00")).toBeInTheDocument();
    expect(screen.queryByText(/Nenhum lançamento em \d{4} ainda/)).not.toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Progresso do faturamento no ano" })).toHaveAttribute(
      "aria-valuenow",
      "50",
    );
    // 3.375 de uma meta mensal de 6.750 = 50%.
    expect(screen.getByRole("progressbar", { name: "Vendas do mês contra a meta mensal" })).toHaveAttribute(
      "aria-valuenow",
      "50",
    );

    fireEvent.click(screen.getByRole("button", { name: "Compras" }));
    expect(screen.queryByText("R$ 3.375,00", { selector: "td" })).not.toBeInTheDocument();
    expect(screen.getByText("R$ 1.200,00", { selector: "td" })).toBeInTheDocument();
  });

  it("'Atualizar' e a troca de mês buscam os dados de novo", async () => {
    api.getSummary.mockResolvedValue(resumo(0));
    renderizar();
    await screen.findByText(/Atualizado às/);
    const chamadas = api.getSummary.mock.calls.length;

    fireEvent.click(screen.getByRole("button", { name: /atualizar/i }));
    await waitFor(() => expect(api.getSummary.mock.calls.length).toBeGreaterThan(chamadas));

    fireEvent.click(screen.getByRole("button", { name: "Mês anterior" }));
    await waitFor(() =>
      expect(api.getTransactions).toHaveBeenLastCalledWith(
        expect.objectContaining({ month: expect.any(Number) }),
      ),
    );
  });

  it("o resumo do agente só é pedido quando o usuário clica, e vem formatado", async () => {
    api.getSummary.mockResolvedValue(resumo(0));
    api.chatAgent.mockResolvedValue({ reply: "Você faturou **R$ 0,00**.", sources: [] });
    renderizar();
    await screen.findByText(/Nenhum lançamento em \d{4} ainda/);
    expect(api.chatAgent).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /gerar resumo com ia/i }));
    expect(await screen.findByText("R$ 0,00", { selector: ".chat-bubble strong" })).toBeInTheDocument();
  });
});
