import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AgentPage } from "./AgentPage";

// Conversa no visual novo (flag `visual-novo`): espera com indicador e tempo,
// e falha que oferece tentar de novo sem redigitar.

const chatAgent = vi.fn();
vi.mock("../api", () => ({ chatAgent: (...args: unknown[]) => chatAgent(...args) }));
vi.mock("../TokensContext", () => ({
  useTokens: () => ({ balance: 1000, ilimitado: true, costs: { chat_message: 5 }, consume: vi.fn() }),
}));
vi.mock("../aparencia/AparenciaContext", () => ({ useAparencia: () => ({ visualNovo: true }) }));

const USER = { name: "Demo User", email: "demo@mei.com" };

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
});

describe("AgentPage — visual novo", () => {
  it("enquanto espera, mostra o agente pensando com o tempo decorrido", async () => {
    let responder: (v: unknown) => void = () => undefined;
    chatAgent.mockReturnValue(new Promise((r) => (responder = r)));
    render(<AgentPage user={USER} />);

    fireEvent.click(screen.getByRole("button", { name: "Para que serve o DAS?" }));

    expect(screen.getByRole("status")).toHaveTextContent(/Pensando · 0 s/);
    expect(screen.getByRole("button", { name: "Enviar" })).toHaveAttribute("aria-busy", "true");

    responder({ reply: "É a guia mensal do MEI.", sources: [] });
    expect(await screen.findByText("É a guia mensal do MEI.")).toBeInTheDocument();
  });

  it("falha explica, avisa que não cobrou e permite tentar de novo a mesma pergunta", async () => {
    chatAgent.mockRejectedValueOnce(new Error("tempo esgotado")).mockResolvedValue({ reply: "Agora foi.", sources: [] });
    render(<AgentPage user={USER} />);

    fireEvent.click(screen.getByRole("button", { name: "Para que serve o DAS?" }));
    expect(await screen.findByText(/Não consegui responder agora \(tempo esgotado\)/)).toBeInTheDocument();
    expect(screen.getByText(/não foi cobrada/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
    expect(chatAgent).toHaveBeenLastCalledWith("demo@mei.com", "Para que serve o DAS?");
    expect(await screen.findByText("Agora foi.")).toBeInTheDocument();
  });
});
