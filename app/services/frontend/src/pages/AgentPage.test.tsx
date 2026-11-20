import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AgentPage, CHAVE_HISTORICO_CHAT } from "./AgentPage";

const chatAgent = vi.fn();
vi.mock("../api", () => ({ chatAgent: (...args: unknown[]) => chatAgent(...args) }));
vi.mock("../TokensContext", () => ({
  useTokens: () => ({ balance: 1000, ilimitado: true, costs: { chat_message: 5 }, consume: vi.fn() }),
}));

const USER = { name: "Demo User", email: "demo@mei.com" };

describe("AgentPage", () => {
  beforeEach(() => {
    localStorage.clear();
    chatAgent.mockResolvedValue({
      reply: "**Não.** Só vendas contam:\n\n* compras ficam fora",
      sources: ["Apenas vendas contam para o limite anual do MEI"],
    });
  });
  afterEach(() => vi.clearAllMocks());

  it("pergunta sugerida envia direto e a resposta aparece formatada, com as fontes", async () => {
    render(<AgentPage user={USER} />);

    fireEvent.click(screen.getByRole("button", { name: "Compras entram no limite do MEI?" }));

    expect(chatAgent).toHaveBeenCalledWith("demo@mei.com", "Compras entram no limite do MEI?");
    expect((await screen.findByText("Não.")).tagName).toBe("STRONG");
    expect(screen.getByText(/Apenas vendas contam/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Compras entram no limite do MEI?" })).not.toBeInTheDocument();
  });

  it("Enter envia e Shift+Enter não", async () => {
    render(<AgentPage user={USER} />);
    const campo = screen.getByRole("textbox", { name: /sua mensagem/i });

    fireEvent.change(campo, { target: { value: "Qual meu limite?" } });
    fireEvent.keyDown(campo, { key: "Enter", shiftKey: true });
    expect(chatAgent).not.toHaveBeenCalled();

    fireEvent.keyDown(campo, { key: "Enter" });
    expect(chatAgent).toHaveBeenCalledWith("demo@mei.com", "Qual meu limite?");
    await screen.findByText("Não.");
  });

  it("guarda o histórico e 'Nova conversa' recomeça", async () => {
    render(<AgentPage user={USER} />);
    fireEvent.click(screen.getByRole("button", { name: "Para que serve o DAS?" }));
    await screen.findByText("Não.");
    expect(localStorage.getItem(CHAVE_HISTORICO_CHAT)).toContain("Para que serve o DAS?");

    fireEvent.click(screen.getByRole("button", { name: "Nova conversa" }));
    await waitFor(() => expect(screen.queryByText("Não.")).not.toBeInTheDocument());
  });

  it("erro da API vira mensagem do agente em vez de quebrar a tela", async () => {
    chatAgent.mockRejectedValueOnce(new Error("timeout"));
    render(<AgentPage user={USER} />);
    fireEvent.click(screen.getByRole("button", { name: "Para que serve o DAS?" }));
    expect(await screen.findByText(/Erro ao chamar a IA: timeout/)).toBeInTheDocument();
  });
});
