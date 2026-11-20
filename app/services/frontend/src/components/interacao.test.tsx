import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CabecalhoPagina, EstadoVazio, Etapas, ProgressoIndeterminado, formatarDuracao, useSegundos } from "./interacao";
import { AvisosProvider, useAvisos } from "./Avisos";
import { AparenciaProvider } from "../aparencia/AparenciaContext";
import { FlagsProvider } from "../flags/FlagsProvider";

describe("Etapas", () => {
  it("anuncia a posição e marca a etapa atual e as concluídas", () => {
    render(<Etapas etapas={["Escolher", "Ler", "Conferir", "Salvo"]} atual={2} />);
    expect(screen.getByRole("navigation", { name: "Etapa 3 de 4" })).toBeTruthy();
    const itens = screen.getAllByRole("listitem");
    expect(itens[2].getAttribute("aria-current")).toBe("step");
    expect(itens[0].textContent).toContain("(concluída)");
    expect(itens[3].textContent).not.toContain("(concluída)");
  });
});

describe("formatarDuracao", () => {
  it("mostra segundos e, a partir de um minuto, minutos com segundos em dois dígitos", () => {
    expect(formatarDuracao(7)).toBe("7 s");
    expect(formatarDuracao(65)).toBe("1 min 05 s");
  });
});

describe("useSegundos", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("conta enquanto ativo e zera ao desativar", () => {
    const { result, rerender } = renderHook(({ ativo }) => useSegundos(ativo), { initialProps: { ativo: true } });
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(result.current).toBe(3);
    rerender({ ativo: false });
    expect(result.current).toBe(0);
  });
});

describe("peças de apoio", () => {
  it("cabeçalho usa h1 e mostra ações", () => {
    render(<CabecalhoPagina titulo="Documentos" descricao="Notas enviadas" acoes={<button>Enviar</button>} />);
    expect(screen.getByRole("heading", { level: 1, name: "Documentos" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Enviar" })).toBeTruthy();
  });

  it("estado vazio diz o que fazer em seguida", () => {
    render(<EstadoVazio titulo="Nada aqui" texto="Envie a primeira nota." acao={<a href="/upload">Enviar</a>} />);
    expect(screen.getByText("Nada aqui")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Enviar" })).toBeTruthy();
  });

  it("progresso indeterminado é um progressbar ocupado, sem valor inventado", () => {
    render(<ProgressoIndeterminado rotulo="Lendo a nota" />);
    const barra = screen.getByRole("progressbar", { name: "Lendo a nota" });
    expect(barra.getAttribute("aria-valuenow")).toBeNull();
  });
});

function Disparador() {
  const avisar = useAvisos();
  return <button onClick={() => avisar("sucesso", "Nota salva.")}>Salvar</button>;
}

function montarAvisos() {
  return render(
    <FlagsProvider>
      <AparenciaProvider>
        <AvisosProvider>
          <Disparador />
        </AvisosProvider>
      </AparenciaProvider>
    </FlagsProvider>
  );
}

describe("Avisos", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_UNLEASH_FRONTEND_URL", "");
  });
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.useRealTimers();
  });

  it("no visual novo, mostra o aviso e some sozinho", () => {
    vi.stubEnv("VITE_VISUAL_NOVO", "true");
    vi.useFakeTimers();
    montarAvisos();
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(screen.getByRole("status").textContent).toContain("Nota salva.");
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(screen.queryByText("Nota salva.")).toBeNull();
  });

  it("pode ser fechado antes do tempo", () => {
    vi.stubEnv("VITE_VISUAL_NOVO", "true");
    montarAvisos();
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    fireEvent.click(screen.getByRole("button", { name: "Fechar aviso" }));
    expect(screen.queryByText("Nota salva.")).toBeNull();
  });

  it("no visual atual não mostra nada", () => {
    vi.stubEnv("VITE_VISUAL_NOVO", "");
    montarAvisos();
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(screen.queryByText("Nota salva.")).toBeNull();
  });
});
