import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DocumentDetailPage } from "./DocumentDetailPage";
import type { DocumentEntry } from "../types";

// Detalhe do documento no visual novo (flag `visual-novo`).

const updateTransaction = vi.fn();
const getDocument = vi.fn();
const confirmDocument = vi.fn();
const corrigirDocumento = vi.fn();
const apagarDocumento = vi.fn();
const deleteTransaction = vi.fn();
const removeDoc = vi.fn();
const updateDoc = vi.fn();
const avisar = vi.fn();
let docs: DocumentEntry[] = [];

vi.mock("../api", () => ({
  updateTransaction: (...a: unknown[]) => updateTransaction(...a),
  getDocument: (...a: unknown[]) => getDocument(...a),
  confirmDocument: (...a: unknown[]) => confirmDocument(...a),
  corrigirDocumento: (...a: unknown[]) => corrigirDocumento(...a),
  apagarDocumento: (...a: unknown[]) => apagarDocumento(...a),
  deleteTransaction: (...a: unknown[]) => deleteTransaction(...a),
  getDocumentAudit: () => Promise.resolve({ registros: [] }),
}));
vi.mock("../App", () => ({ useDocuments: () => ({ docs, updateDoc, removeDoc }) }));
vi.mock("../aparencia/AparenciaContext", () => ({ useAparencia: () => ({ visualNovo: true }) }));
vi.mock("../components/Avisos", () => ({ useAvisos: () => avisar }));

const DOC = {
  id: "d1",
  filename: "nota-bolo.pdf",
  uploadedAt: "2026-03-02T14:30:00",
  sizeBytes: 10,
  ocrText: "BOLO R$ 350,00",
  structured: { value: 350, date: "2026-03-02", cnpj_emitente: "12.345.678/0001-90", confidence: 0.92 },
  limitsTransaction: { id: "t1", amount: 350, tx_date: "2026-03-02", tx_type: "venda", source: "upload" },
  status: "confirmed",
} as unknown as DocumentEntry;

function montar(id = "d1") {
  return render(
    <MemoryRouter initialEntries={[`/documents/${id}`]}>
      <Routes>
        <Route path="/documents/:id" element={<DocumentDetailPage />} />
        <Route path="/documents" element={<p>Lista de documentos</p>} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  docs = [DOC];
  localStorage.setItem("demo-user", JSON.stringify({ name: "Márcia", email: "marcia@mei.com.br" }));
  getDocument.mockRejectedValue(new Error("404"));
});

describe("DocumentDetailPage — visual novo", () => {
  it("mostra o valor em destaque e diz se conta para o limite", () => {
    montar();
    expect(screen.getByRole("heading", { level: 1, name: "nota-bolo.pdf" })).toBeInTheDocument();
    // Valor em destaque (o texto lido da nota também tem "R$ 350,00").
    expect(screen.getByText(/^R\$\s350,00$/)).toHaveClass("valor");
    expect(screen.getByText(/Já conta no seu limite anual/)).toBeInTheDocument();
    expect(screen.getByText("92%")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Documentos" })).toHaveAttribute("href", "/documents");
  });

  it("corrigir e salvar atualiza o lançamento e confirma com aviso", async () => {
    updateTransaction.mockResolvedValue({ ...DOC.limitsTransaction, amount: 400, tx_type: "compra" });
    montar();

    fireEvent.click(screen.getByRole("button", { name: "Corrigir dados" }));
    fireEvent.change(screen.getByLabelText("Valor (R$)"), { target: { value: "400" } });
    fireEvent.click(screen.getByRole("button", { name: /Compra/ }));
    expect(document.getElementById("editar-valor-extenso")!.textContent).toMatch(/R\$\s400,00/);
    fireEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));

    expect(await screen.findByRole("button", { name: "Corrigir dados" })).toBeInTheDocument();
    expect(updateTransaction).toHaveBeenCalledWith("t1", { amount: 400, tx_date: "2026-03-02", tx_type: "compra" });
    expect(avisar).toHaveBeenCalledWith("sucesso", expect.stringContaining("Alterações salvas"));
  });

  it("erro ao salvar mantém a edição e explica o que fazer", async () => {
    updateTransaction.mockRejectedValue(new Error("serviço fora do ar"));
    montar();
    fireEvent.click(screen.getByRole("button", { name: "Corrigir dados" }));
    fireEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível salvar: serviço fora do ar");
    expect(screen.getByLabelText("Valor (R$)")).toBeInTheDocument();
  });

  it("nota que não está no navegador nem no servidor vira estado vazio com caminho de volta", async () => {
    docs = [];
    montar("inexistente");
    expect(await screen.findByText("Nota não encontrada")).toBeInTheDocument();
    expect(getDocument).toHaveBeenCalledWith("inexistente");
    expect(screen.getByRole("link", { name: "Ver todos os documentos" })).toHaveAttribute("href", "/documents");
  });

  describe("nota do histórico no servidor (#95)", () => {
    const SALVA = {
      documento_id: "srv-1",
      estado: "confirmado",
      original_filename: "nota-maio.pdf",
      ocr_text: "NOTA R$ 1.200,00",
      extraction_method: "regex",
      structured_data: { value: 1200, date: "2026-05-10", confidence: 0.8 },
      confirmacao: {
        campos: { value: 1250, date: "2026-05-10", cnpj_emitente: "12.345.678/0001-90", tx_type: "venda" },
        transacao_limits_id: 7,
      },
      criado_em: "2026-05-10T12:00:00",
    };
    const SO_LIDA = { ...SALVA, documento_id: "srv-2", estado: "extraido", confirmacao: null };

    beforeEach(() => {
      docs = [];
    });

    it("abre a nota salva com o valor confirmado e o lançamento", async () => {
      getDocument.mockResolvedValue(SALVA);
      montar("srv-1");

      expect(await screen.findByRole("heading", { level: 1, name: "nota-maio.pdf" })).toBeInTheDocument();
      expect(screen.getByText(/^R\$\s1\.250,00$/)).toHaveClass("valor");
      expect(screen.getByText(/Lançada como venda em 10\/05\/2026/)).toBeInTheDocument();
      expect(screen.getByText("12.345.678/0001-90")).toBeInTheDocument();
      expect(screen.getByText("80%")).toBeInTheDocument();
    });

    it("corrigir salva no servidor e mostra o valor novo", async () => {
      getDocument.mockResolvedValue(SALVA);
      corrigirDocumento.mockResolvedValue({
        ...SALVA,
        confirmacao: { ...SALVA.confirmacao, campos: { ...SALVA.confirmacao.campos, value: 1300, tx_type: "compra" } },
      });
      montar("srv-1");

      fireEvent.click(await screen.findByRole("button", { name: "Corrigir dados" }));
      expect(screen.getByLabelText("Valor (R$)")).toHaveValue(1250);
      fireEvent.change(screen.getByLabelText("Valor (R$)"), { target: { value: "1300" } });
      fireEvent.click(screen.getByRole("button", { name: /Compra/ }));
      fireEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));

      // Espera a edição fechar: a prévia do valor no formulário também diz R$ 1.300,00.
      expect(await screen.findByRole("button", { name: "Corrigir dados" })).toBeInTheDocument();
      expect(screen.getByText(/^R\$\s1\.300,00$/)).toHaveClass("valor");
      expect(screen.getByText(/Lançada como despesa/)).toBeInTheDocument();
      expect(corrigirDocumento).toHaveBeenCalledWith("srv-1", {
        amount: 1300,
        tx_date: "2026-05-10",
        tx_type: "compra",
        cnpj_emitente: "12.345.678/0001-90",
        cnpj_destinatario: null,
        description: null,
      });
      expect(updateTransaction).not.toHaveBeenCalled();
      expect(avisar).toHaveBeenCalledWith("sucesso", expect.stringContaining("Alterações salvas"));
    });

    it("nota só lida é conferida e salva dali, lançando no limite", async () => {
      getDocument.mockResolvedValueOnce(SO_LIDA).mockResolvedValue({ ...SALVA, documento_id: "srv-2" });
      confirmDocument.mockResolvedValue({ limits_transaction: null, structured_data: {} });
      montar("srv-2");

      expect(await screen.findByText("Ainda não foi lançada no seu limite.")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Conferir e salvar" }));
      fireEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));

      await waitFor(() => expect(screen.getByText(/Lançada como venda/)).toBeInTheDocument());
      expect(confirmDocument).toHaveBeenCalledWith(
        expect.objectContaining({
          email: "marcia@mei.com.br",
          amount: 1200,
          tx_type: "venda",
          documento_id: "srv-2",
          source_filename: "nota-maio.pdf",
        }),
      );
      expect(corrigirDocumento).not.toHaveBeenCalled();
    });

    it("erro do servidor ao corrigir mantém a edição", async () => {
      getDocument.mockResolvedValue(SALVA);
      corrigirDocumento.mockRejectedValue(new Error("limits fora do ar"));
      montar("srv-1");

      fireEvent.click(await screen.findByRole("button", { name: "Corrigir dados" }));
      fireEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));

      expect(await screen.findByRole("alert")).toHaveTextContent("limits fora do ar");
      expect(screen.getByLabelText("Valor (R$)")).toBeInTheDocument();
    });
  });

  describe("apagar a nota (#96)", () => {
    const SALVA = {
      documento_id: "srv-1",
      estado: "confirmado",
      original_filename: "nota-maio.pdf",
      ocr_text: "",
      structured_data: { value: 1250, date: "2026-05-10", confidence: 0.8 },
      confirmacao: { campos: { value: 1250, date: "2026-05-10", tx_type: "venda" }, transacao_limits_id: 7 },
      criado_em: "2026-05-10T12:00:00",
    };

    it("pergunta antes, explica o que sai junto, e cancelar não apaga", () => {
      montar();

      fireEvent.click(screen.getByRole("button", { name: "Apagar" }));

      const dialogo = screen.getByRole("alertdialog", { name: "Apagar nota-bolo.pdf?" });
      expect(dialogo).toHaveTextContent(/lançamento de R\$\s350,00 sai do seu faturamento/);
      expect(dialogo).toHaveTextContent("Não dá para desfazer");
      fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
      expect(deleteTransaction).not.toHaveBeenCalled();
      expect(removeDoc).not.toHaveBeenCalled();
    });

    it("nota do navegador: apaga o lançamento e a nota, e volta para a lista", async () => {
      deleteTransaction.mockResolvedValue({ id: "t1", removida: true });
      montar();

      fireEvent.click(screen.getByRole("button", { name: "Apagar" }));
      fireEvent.click(screen.getByRole("button", { name: "Apagar nota" }));

      expect(await screen.findByText("Lista de documentos")).toBeInTheDocument();
      expect(deleteTransaction).toHaveBeenCalledWith("t1");
      expect(removeDoc).toHaveBeenCalledWith("d1");
      expect(avisar).toHaveBeenCalledWith("sucesso", "Nota apagada. O valor dela saiu do painel.");
    });

    it("nota do servidor: apaga pelo Documents", async () => {
      docs = [];
      getDocument.mockResolvedValue(SALVA);
      apagarDocumento.mockResolvedValue({ documento_id: "srv-1", transacao_removida: true, arquivo_removido: true });
      montar("srv-1");

      fireEvent.click(await screen.findByRole("button", { name: "Apagar" }));
      fireEvent.click(screen.getByRole("button", { name: "Apagar nota" }));

      expect(await screen.findByText("Lista de documentos")).toBeInTheDocument();
      expect(apagarDocumento).toHaveBeenCalledWith("srv-1");
      expect(deleteTransaction).not.toHaveBeenCalled();
    });

    it("nota só lida avisa que o painel não muda", async () => {
      docs = [];
      getDocument.mockResolvedValue({ ...SALVA, estado: "extraido", confirmacao: null });
      apagarDocumento.mockResolvedValue({ documento_id: "srv-1", transacao_removida: false, arquivo_removido: true });
      montar("srv-1");

      fireEvent.click(await screen.findByRole("button", { name: "Apagar" }));
      expect(screen.getByRole("alertdialog")).toHaveTextContent("o painel não muda");
      fireEvent.click(screen.getByRole("button", { name: "Apagar nota" }));

      await waitFor(() => expect(avisar).toHaveBeenCalledWith("sucesso", "Nota apagada."));
    });

    it("erro ao apagar mantém a nota e explica", async () => {
      docs = [];
      getDocument.mockResolvedValue(SALVA);
      apagarDocumento.mockRejectedValue(new Error("limits fora do ar"));
      montar("srv-1");

      fireEvent.click(await screen.findByRole("button", { name: "Apagar" }));
      fireEvent.click(screen.getByRole("button", { name: "Apagar nota" }));

      expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível apagar: limits fora do ar");
      expect(screen.getByRole("button", { name: "Apagar nota" })).toBeEnabled();
      expect(screen.queryByText("Lista de documentos")).not.toBeInTheDocument();
    });
  });
});
