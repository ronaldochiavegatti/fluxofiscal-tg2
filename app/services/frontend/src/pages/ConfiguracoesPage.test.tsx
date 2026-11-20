import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConfiguracoesPage } from "./ConfiguracoesPage";
import type { ConfiguracaoFiscal, ParametrosFiscais } from "../types";

// Tela de configurações (#91): converte unidades, envia só o que mudou e
// mostra o erro do domínio embaixo do campo certo.

const api = vi.hoisted(() => ({
  getConfiguracao: vi.fn(),
  salvarConfiguracao: vi.fn(),
  restaurarConfiguracao: vi.fn(),
}));
vi.mock("../api", async () => {
  const real = await vi.importActual<typeof import("../api")>("../api");
  return { ...api, ErroConfiguracao: real.ErroConfiguracao };
});
const avisar = vi.fn();
vi.mock("../components/Avisos", () => ({ useAvisos: () => avisar }));

const USER = { name: "Demo", email: "demo@mei.com" };

const PADRAO: ParametrosFiscais = {
  limite_anual: 81000,
  limite_proporcional: true,
  margem_desenquadramento: 1.2,
  limiar_alerta: 0.8,
  meta_mensal: null,
  limiar_concentracao_cliente: 0.7,
  dias_minimos_para_projetar: 30,
  transacoes_minimas_para_projetar: 3,
  dias_abertura_recente: 60,
  limiar_lancamento_atipico: 0.6,
  limiar_atencao_ritmo_realizado: 0.5,
};

function config(parcial: Partial<ParametrosFiscais> = {}, extra: Partial<ConfiguracaoFiscal> = {}): ConfiguracaoFiscal {
  return {
    email: USER.email,
    data_abertura: null,
    parametros: { ...PADRAO, ...parcial },
    padrao: PADRAO,
    personalizados: Object.keys(parcial) as ConfiguracaoFiscal["personalizados"],
    ativa: true,
    ...extra,
  };
}

const campo = (rotulo: RegExp) => screen.getByLabelText(rotulo) as HTMLInputElement;

beforeEach(() => {
  vi.clearAllMocks();
  api.getConfiguracao.mockResolvedValue(config());
});

describe("ConfiguracoesPage", () => {
  it("mostra esqueleto enquanto carrega e depois os valores na unidade da tela", async () => {
    render(<ConfiguracoesPage user={USER} />);
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull();

    expect((await screen.findByLabelText(/Limite anual de faturamento/) as HTMLInputElement).value).toBe("81000");
    expect(campo(/Avisar a partir de/).value).toBe("80");
    expect(campo(/Tolerância antes do desenquadramento/).value).toBe("20");
    expect(campo(/Meta de vendas por mês/).value).toBe("");
    expect(screen.getByText("Tudo salvo.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Salvar configurações" })).toBeDisabled();
  });

  it("salva só o que mudou, já convertido para a API, e confirma", async () => {
    api.salvarConfiguracao.mockResolvedValue(config({ limiar_alerta: 0.7, limite_anual: 130000 }));
    render(<ConfiguracoesPage user={USER} />);
    await screen.findByLabelText(/Avisar a partir de/);

    fireEvent.change(campo(/Avisar a partir de/), { target: { value: "70" } });
    fireEvent.change(campo(/Limite anual de faturamento/), { target: { value: "130000" } });
    expect(screen.getByText("Há mudanças não salvas.")).toBeInTheDocument();
    expect(screen.getAllByText("personalizado")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "Salvar configurações" }));

    await waitFor(() =>
      expect(api.salvarConfiguracao).toHaveBeenCalledWith(USER.email, {
        parametros: { limiar_alerta: 0.7, limite_anual: 130000 },
      })
    );
    await waitFor(() => expect(avisar).toHaveBeenCalledWith("sucesso", expect.stringContaining("salvas")));
    expect(screen.getByText("Tudo salvo.")).toBeInTheDocument();
  });

  it("meta mensal em branco vai como null (volta ao automático) e a data de abertura também é enviada", async () => {
    api.getConfiguracao.mockResolvedValue(config({ meta_mensal: 5000 }));
    api.salvarConfiguracao.mockResolvedValue(config());
    render(<ConfiguracoesPage user={USER} />);
    await screen.findByLabelText(/Meta de vendas por mês/);

    fireEvent.change(campo(/Meta de vendas por mês/), { target: { value: "" } });
    fireEvent.change(campo(/Data de abertura do MEI/), { target: { value: "2026-07-01" } });
    fireEvent.click(screen.getByRole("switch"));
    fireEvent.click(screen.getByRole("button", { name: "Salvar configurações" }));

    await waitFor(() =>
      expect(api.salvarConfiguracao).toHaveBeenCalledWith(USER.email, {
        parametros: { meta_mensal: null, limite_proporcional: false },
        data_abertura: "2026-07-01",
      })
    );
  });

  it("erro do domínio aparece embaixo do campo citado na mensagem", async () => {
    const { ErroConfiguracao } = await import("../api");
    api.salvarConfiguracao.mockRejectedValue(
      new ErroConfiguracao("limiar_alerta deve estar entre 0 (exclusive) e 1, recebido 1.5")
    );
    render(<ConfiguracoesPage user={USER} />);
    await screen.findByLabelText(/Avisar a partir de/);

    fireEvent.change(campo(/Avisar a partir de/), { target: { value: "150" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar configurações" }));

    const erro = await screen.findByRole("alert");
    expect(erro).toHaveTextContent("limiar_alerta deve estar entre");
    expect(erro.id).toBe("erro-limiar_alerta");
    expect(campo(/Avisar a partir de/)).toHaveAttribute("aria-invalid", "true");
    // Digitar de novo no campo limpa o erro.
    fireEvent.change(campo(/Avisar a partir de/), { target: { value: "75" } });
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("campo obrigatório vazio não vai ao servidor", async () => {
    render(<ConfiguracoesPage user={USER} />);
    await screen.findByLabelText(/Limite anual de faturamento/);
    fireEvent.change(campo(/Limite anual de faturamento/), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar configurações" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Preencha este campo");
    expect(api.salvarConfiguracao).not.toHaveBeenCalled();
  });

  it("voltar ao padrão restaura o valor do campo", async () => {
    api.getConfiguracao.mockResolvedValue(config({ limite_anual: 130000 }));
    render(<ConfiguracoesPage user={USER} />);
    await screen.findByLabelText(/Limite anual de faturamento/);
    fireEvent.click(screen.getByRole("button", { name: "Voltar ao padrão" }));
    expect(campo(/Limite anual de faturamento/).value).toBe("81000");
  });

  it("restaurar tudo pede confirmação", async () => {
    api.getConfiguracao.mockResolvedValue(config({ limite_anual: 130000 }));
    api.restaurarConfiguracao.mockResolvedValue(config());
    render(<ConfiguracoesPage user={USER} />);
    await screen.findByLabelText(/Limite anual de faturamento/);

    fireEvent.click(screen.getByRole("button", { name: "Restaurar padrões" }));
    expect(api.restaurarConfiguracao).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Sim, voltar tudo ao padrão" }));

    await waitFor(() => expect(api.restaurarConfiguracao).toHaveBeenCalledWith(USER.email));
    await waitFor(() => expect(campo(/Limite anual de faturamento/).value).toBe("81000"));
  });

  it("avisa quando o servidor ainda não aplica a configuração", async () => {
    api.getConfiguracao.mockResolvedValue(config({}, { ativa: false }));
    render(<ConfiguracoesPage user={USER} />);
    expect(await screen.findByText(/servidor ainda está usando os valores padrão/)).toBeInTheDocument();
  });

  it("falha ao carregar oferece tentar de novo", async () => {
    api.getConfiguracao.mockRejectedValueOnce(new Error("sem rede")).mockResolvedValue(config());
    render(<ConfiguracoesPage user={USER} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("sem rede");
    fireEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
    expect(await screen.findByLabelText(/Limite anual de faturamento/)).toBeInTheDocument();
  });
});
