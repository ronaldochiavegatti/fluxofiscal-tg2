import type { IConfig } from "@unleash/proxy-client-react";

/**
 * Única fonte da condição "Unleash está configurado" — usada por
 * `FlagsProvider` (decide entre modo live e o padrão "offline" da
 * biblioteca) e por `useFeatureFlag` (decide se confia em `flagsReady`). As
 * duas precisam concordar: se decidissem por condições diferentes, o hook
 * poderia confiar num `flagsReady` que na verdade veio do modo inerte.
 */
export function unleashFrontendConfig(): IConfig | undefined {
  const url = import.meta.env.VITE_UNLEASH_FRONTEND_URL;
  const clientKey = import.meta.env.VITE_UNLEASH_FRONTEND_TOKEN;

  if (!url || !clientKey) return undefined;

  return {
    url,
    clientKey,
    appName: import.meta.env.VITE_UNLEASH_APP_NAME ?? "fluxofiscal",
    refreshInterval: 30,
  };
}
