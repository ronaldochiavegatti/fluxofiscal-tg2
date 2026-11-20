import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DocumentsPage } from "./DocumentsPage";

const listDocuments = vi.fn();
const useFeatureFlag = vi.fn();
const useDocuments = vi.fn();

vi.mock("../api", () => ({ listDocuments: (...a: unknown[]) => listDocuments(...a) }));
vi.mock("../flags/useFeatureFlag", () => ({
  useFeatureFlag: (...a: unknown[]) => useFeatureFlag(...a),
}));
vi.mock("../App", () => ({ useDocuments: () => useDocuments() }));

function renderPage() {
  return render(
    <MemoryRouter>
      <DocumentsPage />
    </MemoryRouter>,
  );
}

const DOC_LOCAL = {
  id: "loc-1",
  filename: "recibo-local.png",
  structured: { value: 100, date: "2026-03-01", confidence: 0.9 },
  limitsTransaction: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.setItem("demo-user", JSON.stringify({ email: "marcia@mei.com.br" }));
  useDocuments.mockReturnValue({ docs: [DOC_LOCAL], addDoc: vi.fn(), updateDoc: vi.fn(), clearDocs: vi.fn() });
});

afterEach(() => localStorage.clear());

describe("DocumentsPage", () => {
  it("com a flag desligada, mostra o histórico do localStorage", () => {
    useFeatureFlag.mockReturnValue(false);

    renderPage();

    expect(screen.getByText("recibo-local.png")).toBeInTheDocument();
    expect(screen.getByText(/localStorage/)).toBeInTheDocument();
    expect(listDocuments).not.toHaveBeenCalled();
  });

  it("com a flag ligada, lista os documentos do servidor com o estado", async () => {
    useFeatureFlag.mockReturnValue(true);
    listDocuments.mockResolvedValue([
      {
        id: "srv-1",
        nome_original: "nota-servidor.pdf",
        tamanho_bytes: 1000,
        tipo_mime: "application/pdf",
        estado: "extraido",
        extracao: { metodo: "regex", campos: { value: 250, date: "2026-05-10" }, confianca: 0.8 },
        criado_em: "2026-05-10T12:00:00Z",
      },
    ]);

    renderPage();

    await waitFor(() => expect(screen.getByText("nota-servidor.pdf")).toBeInTheDocument());
    expect(listDocuments).toHaveBeenCalledWith("marcia@mei.com.br");
    expect(screen.getByText("Extraído")).toBeInTheDocument();
    expect(screen.getByText(/qualquer dispositivo/)).toBeInTheDocument();
    // o documento só do localStorage não aparece quando o servidor respondeu
    expect(screen.queryByText("recibo-local.png")).not.toBeInTheDocument();
  });

  it("documento confirmado mostra o valor confirmado, não o extraído", async () => {
    useFeatureFlag.mockReturnValue(true);
    listDocuments.mockResolvedValue([
      {
        id: "srv-2",
        nome_original: "nota-corrigida.pdf",
        tamanho_bytes: 1000,
        tipo_mime: "application/pdf",
        estado: "confirmado",
        extracao: { metodo: "regex", campos: { value: 1200, date: "2026-05-10" }, confianca: 0.8 },
        confirmacao: {
          campos: { value: 1250, date: "2026-05-10", tx_type: "venda" },
          transacao_limits_id: 7,
        },
        criado_em: "2026-05-10T12:00:00Z",
      },
    ]);

    renderPage();

    await waitFor(() => expect(screen.getByText("nota-corrigida.pdf")).toBeInTheDocument());
    expect(screen.getByText("Confirmado")).toBeInTheDocument();
    expect(screen.getAllByText(/1\.250,00/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/1\.200,00/)).not.toBeInTheDocument();
  });

  it("nota salva depois do aviso de repetição aparece sinalizada (#93)", async () => {
    useFeatureFlag.mockReturnValue(true);
    const base = {
      nome_original: "nota-maio.pdf",
      tamanho_bytes: 1000,
      tipo_mime: "application/pdf",
      estado: "confirmado",
      extracao: { metodo: "regex", campos: { value: 500, date: "2026-05-10" }, confianca: 0.8 },
      confirmacao: { campos: { value: 500, date: "2026-05-10", tx_type: "venda" }, transacao_limits_id: 1 },
      criado_em: "2026-05-10T12:00:00Z",
    };
    listDocuments.mockResolvedValue([
      { ...base, id: "srv-2", repeticao_de: ["srv-1"] },
      { ...base, id: "srv-1", repeticao_de: [] },
    ]);

    renderPage();

    await waitFor(() => expect(screen.getAllByText("nota-maio.pdf").length).toBeGreaterThan(0));
    // Só a segunda tem o selo; a original continua sem.
    expect(screen.getAllByText("Repetida")).toHaveLength(1);
  });

  it("no localStorage, a nota marcada como repetida também aparece sinalizada", () => {
    useFeatureFlag.mockReturnValue(false);
    useDocuments.mockReturnValue({
      docs: [DOC_LOCAL, { ...DOC_LOCAL, id: "loc-2", repetida: true }],
      addDoc: vi.fn(),
      updateDoc: vi.fn(),
      clearDocs: vi.fn(),
    });

    renderPage();

    expect(screen.getAllByText("Repetida")).toHaveLength(1);
  });

  it("com a flag ligada mas o servidor falhando, cai para o localStorage", async () => {
    useFeatureFlag.mockReturnValue(true);
    listDocuments.mockRejectedValue(new Error("500"));

    renderPage();

    await waitFor(() =>
      expect(screen.getByText(/Não foi possível carregar o histórico/)).toBeInTheDocument(),
    );
    expect(screen.getByText("recibo-local.png")).toBeInTheDocument();
  });
});
