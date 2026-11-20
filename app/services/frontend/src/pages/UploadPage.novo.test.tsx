import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { UploadPage } from "./UploadPage";

// Fluxo de envio no visual novo (flag `visual-novo`): etapas, espera com
// progresso, conferência que diz o que foi lido e o que falta, e confirmação.

const uploadDocument = vi.fn();
const getDocument = vi.fn();
const confirmDocument = vi.fn();
const avisar = vi.fn();
const avaliarArquivo = vi.fn();

vi.mock("../api", () => ({
  uploadDocument: (...a: unknown[]) => uploadDocument(...a),
  getDocument: (...a: unknown[]) => getDocument(...a),
  reprocessDocument: vi.fn(),
  confirmDocument: (...a: unknown[]) => confirmDocument(...a),
}));
vi.mock("../App", () => ({ useDocuments: () => ({ addDoc: vi.fn() }) }));
vi.mock("../TokensContext", () => ({
  useTokens: () => ({ balance: 100, ilimitado: true, costs: { document_confirm: 15 }, consume: vi.fn() }),
}));
vi.mock("../useUserCnpj", () => ({ useUserCnpj: () => ["12.345.678/0001-95"] }));
vi.mock("../aparencia/AparenciaContext", () => ({ useAparencia: () => ({ visualNovo: true }) }));
vi.mock("../components/Avisos", () => ({ useAvisos: () => avisar }));
vi.mock("../qualidadeFoto", async (original) => ({
  ...(await original<typeof import("../qualidadeFoto")>()),
  avaliarArquivo: (...a: unknown[]) => avaliarArquivo(...a),
}));

const USER = { name: "Márcia", email: "marcia@mei.com.br" };

function enviarArquivo() {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  const file = new File([new Uint8Array([1, 2, 3])], "nota.png", { type: "image/png" });
  fireEvent.change(input, { target: { files: [file] } });
  expect(screen.getByRole("button", { name: "Enviar e ler a nota" })).toBeEnabled();
  // O jsdom não considera preenchido um <input type="file" required> alterado
  // por evento; envia direto o formulário, como os testes do visual atual.
  fireEvent.submit(input.closest("form")!);
}

function montar() {
  return render(
    <MemoryRouter>
      <UploadPage user={USER} />
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  avaliarArquivo.mockResolvedValue(null);
});

describe("UploadPage — visual novo", () => {
  it("começa na etapa 1 e só libera o envio com arquivo escolhido", () => {
    montar();
    expect(screen.getByRole("navigation", { name: "Etapa 1 de 4" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Enviar e ler a nota" })).toBeDisabled();
  });

  it("durante a leitura mostra a etapa 2 com progresso; depois abre a conferência", async () => {
    uploadDocument.mockResolvedValue({
      original_filename: "nota.png",
      size_bytes: 3,
      estado: "recebido",
      documento_id: "doc-1",
    });
    getDocument.mockResolvedValueOnce({ documento_id: "doc-1", estado: "processando" }).mockResolvedValue({
      documento_id: "doc-1",
      estado: "extraido",
      ocr_text: "VALOR R$ 1.234,56",
      extraction_method: "gemini",
      structured_data: { value: 1234.56, date: "2026-06-17", confidence: 0.9, tx_type_sugerido: "venda", tx_type_auto_detectado: true },
    });

    montar();
    enviarArquivo();

    expect(await screen.findByRole("navigation", { name: "Etapa 2 de 4" })).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: /Lendo|Enviando|Arquivo recebido/ })).toBeInTheDocument();

    await waitFor(() => expect(screen.getByRole("navigation", { name: "Etapa 3 de 4" })).toBeInTheDocument(), {
      timeout: 4000,
    });
    // O que veio da nota e o que falta preencher ficam explícitos no rótulo.
    expect(screen.getByLabelText(/Valor \(R\$\)/).closest("div")!.textContent).toContain("lido da nota");
    expect(screen.getByLabelText(/Descrição/).closest("div")!.textContent).toContain("preencha");
    // O valor digitado aparece por extenso logo abaixo do campo.
    expect(document.getElementById("valor-por-extenso")!.textContent).toMatch(/R\$\s1\.234,56/);
    expect(screen.getByRole("button", { name: /Venda/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("salvar confirma com aviso e oferece os próximos passos", async () => {
    uploadDocument.mockResolvedValue({
      original_filename: "nota.png",
      size_bytes: 3,
      ocr_text: "",
      extraction_method: "regex",
      structured_data: { value: 500, date: "2026-03-02", tx_type_sugerido: "compra", tx_type_auto_detectado: true },
    });
    confirmDocument.mockResolvedValue({ limits_transaction: null });

    montar();
    enviarArquivo();
    fireEvent.click(await screen.findByRole("button", { name: "Salvar nota" }));

    expect(await screen.findByRole("heading", { name: "Compra salva" })).toBeInTheDocument();
    expect(avisar).toHaveBeenCalledWith("sucesso", expect.stringContaining("compra de R$"));
    expect(screen.getByRole("link", { name: "Ver no painel" })).toHaveAttribute("href", "/dashboard");
    expect(screen.getByRole("navigation", { name: "Etapa 4 de 4" })).toBeInTheDocument();
  });

  it("falha no envio diz o que aconteceu e o botão vira tentar de novo", async () => {
    uploadDocument.mockRejectedValue(new Error("Servidor indisponível"));
    montar();
    enviarArquivo();
    expect(await screen.findByRole("alert")).toHaveTextContent("O envio falhou: Servidor indisponível");
    expect(screen.getByRole("button", { name: "Tentar de novo" })).toBeEnabled();
  });

  describe("nota repetida (#93)", () => {
    const REPETIDA = {
      original_filename: "nota.png",
      size_bytes: 3,
      ocr_text: "",
      extraction_method: "regex",
      documento_id: "doc-2",
      structured_data: { value: 1250, date: "2026-05-10", tx_type_sugerido: "venda", tx_type_auto_detectado: true },
      repeticoes: [
        {
          documento_id: "doc-1",
          nome_original: "nota-maio.pdf",
          mesmo_arquivo: false,
          valor: 1250,
          data: "2026-05-10",
          tx_type: "venda",
          enviado_em: "2026-05-11T09:00:00Z",
        },
      ],
    };

    it("pergunta antes de abrir a conferência e mostra a nota já salva", async () => {
      uploadDocument.mockResolvedValue(REPETIDA);
      montar();
      enviarArquivo();

      const aviso = await screen.findByRole("alertdialog", { name: "Esta nota parece já ter sido salva" });
      expect(aviso).toHaveTextContent("nota-maio.pdf");
      expect(aviso).toHaveTextContent(/venda de R\$\s1\.250,00 em 10\/05\/2026/);
      expect(aviso).toHaveTextContent("enviada em 11/05/2026");
      expect(screen.queryByRole("button", { name: "Salvar nota" })).not.toBeInTheDocument();
    });

    it("continuar abre a conferência normalmente", async () => {
      uploadDocument.mockResolvedValue(REPETIDA);
      montar();
      enviarArquivo();

      fireEvent.click(await screen.findByRole("button", { name: "Continuar mesmo assim" }));

      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Salvar nota" })).toBeInTheDocument();
    });

    it("cancelar volta para a escolha do arquivo sem salvar nada", async () => {
      uploadDocument.mockResolvedValue(REPETIDA);
      montar();
      enviarArquivo();

      fireEvent.click(await screen.findByRole("button", { name: "Cancelar envio" }));

      expect(screen.getByRole("navigation", { name: "Etapa 1 de 4" })).toBeInTheDocument();
      expect(confirmDocument).not.toHaveBeenCalled();
    });

    it("o mesmo arquivo de novo diz isso no título", async () => {
      uploadDocument.mockResolvedValue({
        ...REPETIDA,
        repeticoes: [{ ...REPETIDA.repeticoes[0], mesmo_arquivo: true }],
      });
      montar();
      enviarArquivo();

      expect(await screen.findByRole("alertdialog", { name: "Este arquivo já foi salvo" })).toBeInTheDocument();
    });

    it("sem repetição, vai direto para a conferência", async () => {
      uploadDocument.mockResolvedValue({ ...REPETIDA, repeticoes: [] });
      montar();
      enviarArquivo();

      expect(await screen.findByRole("button", { name: "Salvar nota" })).toBeInTheDocument();
      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    });
  });

  describe("foto sem qualidade para leitura (issue 100)", () => {
    const TREMIDA = {
      legivel: false,
      motivo: "tremida",
      nitidez: 20,
      razaoNitidez: 1.1,
      brilho: 200,
      contraste: 40,
      largura: 3000,
      altura: 4000,
    };
    const LIDA = {
      original_filename: "nota.png",
      size_bytes: 3,
      ocr_text: "",
      extraction_method: "gemini",
      structured_data: { value: 80, date: "2026-11-10", tx_type_sugerido: "compra", tx_type_auto_detectado: true },
    };

    it("foto tremida não é enviada: diz o motivo e como resolver", async () => {
      avaliarArquivo.mockResolvedValue(TREMIDA);
      montar();
      enviarArquivo();

      const aviso = await screen.findByRole("alertdialog", { name: "Essa foto não vai dar para ler" });
      expect(aviso).toHaveTextContent("A foto está tremida ou fora de foco.");
      expect(aviso).toHaveTextContent(/Como resolver:.*Apoie os cotovelos/);
      expect(aviso).toHaveTextContent("nada foi gasto");
      expect(uploadDocument).not.toHaveBeenCalled();
    });

    it("enviar mesmo assim pula a checagem e força a leitura no servidor", async () => {
      avaliarArquivo.mockResolvedValue(TREMIDA);
      uploadDocument.mockResolvedValue(LIDA);
      montar();
      enviarArquivo();

      fireEvent.click(await screen.findByRole("button", { name: "Enviar mesmo assim" }));

      expect(await screen.findByRole("button", { name: "Salvar nota" })).toBeInTheDocument();
      expect(uploadDocument).toHaveBeenCalledWith(expect.any(File), USER.email, "12.345.678/0001-95", {
        forcarLeitura: true,
      });
      expect(avaliarArquivo).toHaveBeenCalledTimes(1);
    });

    it("tirar outra foto volta para a escolha do arquivo", async () => {
      avaliarArquivo.mockResolvedValue(TREMIDA);
      montar();
      enviarArquivo();

      fireEvent.click(await screen.findByRole("button", { name: "Tirar outra foto" }));

      expect(screen.getByRole("navigation", { name: "Etapa 1 de 4" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Enviar e ler a nota" })).toBeDisabled();
    });

    it("recusa do servidor mostra o mesmo aviso", async () => {
      const recusa = Object.assign(new Error("A foto está escura demais para ler."), {
        name: "FotoIlegivel",
        motivo: "escura",
        dica: "Procure um lugar iluminado.",
      });
      uploadDocument.mockRejectedValue(recusa);
      montar();
      enviarArquivo();

      const aviso = await screen.findByRole("alertdialog", { name: "Essa foto não vai dar para ler" });
      expect(aviso).toHaveTextContent("A foto está escura demais para ler.");
      expect(aviso).toHaveTextContent("Procure um lugar iluminado.");
    });

    it("foto boa segue direto para a leitura", async () => {
      avaliarArquivo.mockResolvedValue({ ...TREMIDA, legivel: true, motivo: null });
      uploadDocument.mockResolvedValue(LIDA);
      montar();
      enviarArquivo();

      expect(await screen.findByRole("button", { name: "Salvar nota" })).toBeInTheDocument();
      expect(uploadDocument).toHaveBeenCalledWith(expect.any(File), USER.email, "12.345.678/0001-95", {
        forcarLeitura: false,
      });
    });
  });
});
