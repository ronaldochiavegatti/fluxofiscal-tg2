import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { UploadPage } from "./UploadPage";

const uploadDocument = vi.fn();
const getDocument = vi.fn();
const reprocessDocument = vi.fn();
const confirmDocument = vi.fn();

vi.mock("../api", () => ({
  uploadDocument: (...a: unknown[]) => uploadDocument(...a),
  getDocument: (...a: unknown[]) => getDocument(...a),
  reprocessDocument: (...a: unknown[]) => reprocessDocument(...a),
  confirmDocument: (...a: unknown[]) => confirmDocument(...a),
}));
let docsLocais: unknown[] = [];
const addDoc = vi.fn();
vi.mock("../App", () => ({ useDocuments: () => ({ docs: docsLocais, addDoc: (...a: unknown[]) => addDoc(...a) }) }));
vi.mock("../TokensContext", () => ({
  useTokens: () => ({ balance: 100, costs: { document_confirm: 15 }, consume: vi.fn() }),
}));
vi.mock("../useUserCnpj", () => ({ useUserCnpj: () => ["12.345.678/0001-95"] }));

const USER = { name: "Márcia", email: "marcia@mei.com.br" };

function enviarArquivo() {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  const file = new File([new Uint8Array([1, 2, 3])], "nota.png", { type: "image/png" });
  fireEvent.change(input, { target: { files: [file] } });
  fireEvent.submit(input.closest("form")!);
}

beforeEach(() => {
  vi.clearAllMocks();
  docsLocais = [];
});
afterEach(() => vi.useRealTimers());

describe("UploadPage — upload assíncrono (US-18)", () => {
  it("mostra o progresso ao receber 202 e abre a revisão quando extrai", async () => {
    uploadDocument.mockResolvedValue({
      original_filename: "nota.png",
      size_bytes: 3,
      estado: "recebido",
      documento_id: "doc-1",
      acompanhamento_url: "/documents/documentos/doc-1",
    });
    getDocument
      .mockResolvedValueOnce({ documento_id: "doc-1", estado: "processando" })
      .mockResolvedValue({
        documento_id: "doc-1",
        estado: "extraido",
        ocr_text: "VALOR R$ 1.234,56",
        extraction_method: "regex",
        structured_data: { value: 1234.56, date: "2026-06-17", confidence: 0.9 },
      });

    render(<UploadPage user={USER} />);
    enviarArquivo();

    expect(await screen.findByText(/Recebemos sua nota/)).toBeInTheDocument();
    await waitFor(
      () => expect(screen.getByText(/Confira os dados antes de salvar/)).toBeInTheDocument(),
      { timeout: 4000 },
    );
    expect(screen.getByDisplayValue("1234.56")).toBeInTheDocument();
  });

  it("mostra a falha com botão de tentar de novo", async () => {
    uploadDocument.mockResolvedValue({
      original_filename: "nota.png",
      size_bytes: 3,
      estado: "recebido",
      documento_id: "doc-2",
    });
    getDocument.mockResolvedValue({
      documento_id: "doc-2",
      estado: "erro",
      erro: { motivo: "Gemini indisponível", permanente: false },
    });
    reprocessDocument.mockResolvedValue({ estado: "processando" });

    render(<UploadPage user={USER} />);
    enviarArquivo();

    await waitFor(() => expect(screen.getByText(/Gemini indisponível/)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /tentar de novo/i }));
    await waitFor(() => expect(reprocessDocument).toHaveBeenCalledWith("doc-2"));
  });

  it("sem 202, segue o fluxo síncrono e abre a revisão direto", async () => {
    uploadDocument.mockResolvedValue({
      original_filename: "nota.png",
      size_bytes: 3,
      ocr_text: "R$ 1.000,00",
      extraction_method: "gemini",
      structured_data: { value: 1000, confidence: 0.95 },
    });

    render(<UploadPage user={USER} />);
    enviarArquivo();

    await waitFor(() =>
      expect(screen.getByText(/Confira os dados antes de salvar/)).toBeInTheDocument(),
    );
    expect(getDocument).not.toHaveBeenCalled();
  });
});

describe("UploadPage — nota repetida sem persistência no servidor (#93)", () => {
  const LIDA = {
    original_filename: "foto-nota.png",
    size_bytes: 3,
    ocr_text: "",
    extraction_method: "regex",
    structured_data: { value: 300, date: "2026-04-02", cnpj_emitente: "12345678000195" },
  };
  const SALVA = {
    id: "loc-1",
    filename: "nota-abril.pdf",
    uploadedAt: "2026-04-03T10:00:00Z",
    ocrText: "",
    structured: { value: 300, date: "2026-04-02", cnpj_emitente: "12.345.678/0001-95" },
    status: "confirmed",
  };

  it("compara com as notas confirmadas neste navegador", async () => {
    docsLocais = [SALVA];
    uploadDocument.mockResolvedValue(LIDA);

    render(<UploadPage user={USER} />);
    enviarArquivo();

    const aviso = await screen.findByRole("alertdialog", { name: "Esta nota parece já ter sido salva" });
    expect(aviso).toHaveTextContent("nota-abril.pdf");
    fireEvent.click(screen.getByRole("button", { name: "Continuar mesmo assim" }));
    expect(screen.getByText(/Confira os dados antes de salvar/)).toBeInTheDocument();
  });

  it("salvar depois de continuar marca a nota como repetida no histórico", async () => {
    docsLocais = [SALVA];
    uploadDocument.mockResolvedValue({ ...LIDA, structured_data: { ...LIDA.structured_data, tx_type_sugerido: "venda" } });
    confirmDocument.mockResolvedValue({ limits_transaction: null });

    render(<UploadPage user={USER} />);
    enviarArquivo();
    fireEvent.click(await screen.findByRole("button", { name: "Continuar mesmo assim" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirmar e salvar" }));

    await waitFor(() => expect(addDoc).toHaveBeenCalledWith(expect.objectContaining({ repetida: true })));
  });

  it("nota sem repetição é salva sem a marca", async () => {
    uploadDocument.mockResolvedValue({ ...LIDA, structured_data: { ...LIDA.structured_data, tx_type_sugerido: "venda" } });
    confirmDocument.mockResolvedValue({ limits_transaction: null });

    render(<UploadPage user={USER} />);
    enviarArquivo();
    fireEvent.click(await screen.findByRole("button", { name: "Confirmar e salvar" }));

    await waitFor(() => expect(addDoc).toHaveBeenCalledWith(expect.objectContaining({ repetida: false })));
  });

  it("nota descartada ou de outro emitente não conta como repetida", async () => {
    docsLocais = [
      { ...SALVA, id: "loc-2", status: "discarded" },
      { ...SALVA, id: "loc-3", structured: { ...SALVA.structured, cnpj_emitente: "99.999.999/0001-99" } },
    ];
    uploadDocument.mockResolvedValue(LIDA);

    render(<UploadPage user={USER} />);
    enviarArquivo();

    expect(await screen.findByText(/Confira os dados antes de salvar/)).toBeInTheDocument();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("a resposta do servidor tem prioridade sobre o navegador", async () => {
    docsLocais = [SALVA];
    uploadDocument.mockResolvedValue({ ...LIDA, documento_id: "doc-9", repeticoes: [] });

    render(<UploadPage user={USER} />);
    enviarArquivo();

    expect(await screen.findByText(/Confira os dados antes de salvar/)).toBeInTheDocument();
  });
});
