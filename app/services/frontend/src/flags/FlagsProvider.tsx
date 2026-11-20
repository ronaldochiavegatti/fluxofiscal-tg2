import type { PropsWithChildren } from "react";
import { FlagProvider } from "@unleash/proxy-client-react";
import { unleashFrontendConfig } from "./config";

/**
 * Feature flags via Unleash (US-15, ADR-0008).
 *
 * O SDK do navegador fala com o Frontend API do Unleash através do gateway
 * (`/unleash-frontend/`), nunca direto — evita expor um token com mais
 * escopo do que o necessário para um cliente que roda no dispositivo do
 * usuário.
 *
 * Sem URL e token configurados, `unleashFrontendConfig()` devolve
 * `undefined` e o `FlagProvider` cai no próprio padrão "offline" da
 * biblioteca (sem rede, sem refresh, sem métricas) — nunca uma tela em
 * branco por causa disto.
 */
export function FlagsProvider({ children }: PropsWithChildren) {
  return <FlagProvider config={unleashFrontendConfig()}>{children}</FlagProvider>;
}
