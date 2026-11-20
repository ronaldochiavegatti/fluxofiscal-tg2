import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SoltarArquivo } from "./SoltarArquivo";

const nota = new File(["x".repeat(2048)], "nota.pdf", { type: "application/pdf" });

describe("SoltarArquivo", () => {
  it("sem arquivo, convida a arrastar ou clicar", () => {
    render(<SoltarArquivo arquivo={null} onEscolher={vi.fn()} />);
    expect(screen.getByText(/arraste a nota fiscal/i)).toBeInTheDocument();
  });

  it("escolher pelo seletor nativo entrega o arquivo", () => {
    const onEscolher = vi.fn();
    const { container } = render(<SoltarArquivo arquivo={null} onEscolher={onEscolher} />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [nota] } });
    expect(onEscolher).toHaveBeenCalledWith(nota);
  });

  it("arrastar destaca a área e soltar entrega o arquivo", () => {
    const onEscolher = vi.fn();
    render(<SoltarArquivo arquivo={null} onEscolher={onEscolher} />);
    const area = screen.getByText(/arraste a nota fiscal/i).closest("label") as HTMLElement;

    fireEvent.dragOver(area);
    expect(screen.getByText("Solte o arquivo aqui")).toBeInTheDocument();
    fireEvent.dragLeave(area);
    expect(screen.queryByText("Solte o arquivo aqui")).not.toBeInTheDocument();

    fireEvent.drop(area, { dataTransfer: { files: [nota] } });
    expect(onEscolher).toHaveBeenCalledWith(nota);
  });

  it("desabilitado ignora o arquivo solto", () => {
    const onEscolher = vi.fn();
    render(<SoltarArquivo arquivo={null} onEscolher={onEscolher} desabilitado />);
    const area = screen.getByText(/arraste a nota fiscal/i).closest("label") as HTMLElement;
    fireEvent.drop(area, { dataTransfer: { files: [nota] } });
    expect(onEscolher).not.toHaveBeenCalled();
  });

  it("com arquivo, mostra nome, tipo e tamanho", () => {
    render(<SoltarArquivo arquivo={nota} onEscolher={vi.fn()} />);
    expect(screen.getByText("nota.pdf")).toBeInTheDocument();
    expect(screen.getByText(/PDF · 2 KB/)).toBeInTheDocument();
  });

  it("o botão de câmera abre a câmera traseira e entrega a foto (issue 100)", () => {
    const onEscolher = vi.fn();
    render(<SoltarArquivo arquivo={null} onEscolher={onEscolher} />);
    const camera = screen.getByLabelText("Tirar foto da nota") as HTMLInputElement;
    expect(camera).toHaveAttribute("capture", "environment");
    expect(camera).toHaveAttribute("accept", "image/*");
    const foto = new File([new Uint8Array([1])], "image.jpg", { type: "image/jpeg" });
    fireEvent.change(camera, { target: { files: [foto] } });
    expect(onEscolher).toHaveBeenCalledWith(foto);
  });
});
