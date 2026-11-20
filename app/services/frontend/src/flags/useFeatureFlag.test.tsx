import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FlagsProvider } from "./FlagsProvider";
import { useFeatureFlag } from "./useFeatureFlag";

// Cobre o contrato de segurança da US-15 (ADR-0008): sem Unleash configurado,
// ou com o Unleash fora do ar, toda flag cai no padrão declarado pelo
// chamador — nunca uma tela em branco por causa da flag.

function Sonda({ nome, padrao }: { nome: string; padrao: boolean }) {
  const ativo = useFeatureFlag(nome, padrao);
  return <span data-testid="resultado">{String(ativo)}</span>;
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("useFeatureFlag", () => {
  it("sem Unleash configurado, cai no padrão declarado pelo chamador", () => {
    vi.stubEnv("VITE_UNLEASH_FRONTEND_URL", "");

    render(
      <FlagsProvider>
        <Sonda nome="dashboard-v2" padrao={true} />
      </FlagsProvider>
    );

    expect(screen.getByTestId("resultado").textContent).toBe("true");
  });

  it("com URL configurada mas sem token, cai no padrão (não deixa o SDK levantar)", () => {
    vi.stubEnv("VITE_UNLEASH_FRONTEND_URL", "http://localhost/unleash-frontend");
    vi.stubEnv("VITE_UNLEASH_FRONTEND_TOKEN", "");

    render(
      <FlagsProvider>
        <Sonda nome="dashboard-v2" padrao={true} />
      </FlagsProvider>
    );

    expect(screen.getByTestId("resultado").textContent).toBe("true");
  });

  it("com o Unleash inalcançável, cai no padrão em vez de travar a tela", async () => {
    vi.stubEnv("VITE_UNLEASH_FRONTEND_URL", "http://127.0.0.1:1/api/frontend");
    vi.stubEnv("VITE_UNLEASH_FRONTEND_TOKEN", "token-de-teste");
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("rede indisponível")))
    );

    render(
      <FlagsProvider>
        <Sonda nome="dashboard-v2" padrao={false} />
      </FlagsProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("resultado").textContent).toBe("false");
    });
  });

  it("com o Unleash respondendo, usa o valor avaliado — não mais o padrão", async () => {
    vi.stubEnv("VITE_UNLEASH_FRONTEND_URL", "http://localhost/unleash-frontend");
    vi.stubEnv("VITE_UNLEASH_FRONTEND_TOKEN", "token-de-teste");
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({
              toggles: [
                {
                  name: "dashboard-v2",
                  enabled: true,
                  variant: { name: "disabled", enabled: false },
                  impressionData: false,
                },
              ],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          )
        )
      )
    );

    render(
      <FlagsProvider>
        <Sonda nome="dashboard-v2" padrao={false} />
      </FlagsProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("resultado").textContent).toBe("true");
    });
  });
});
