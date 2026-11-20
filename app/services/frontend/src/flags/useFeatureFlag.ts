import { useFlag, useFlagsStatus } from "@unleash/proxy-client-react";
import { unleashFrontendConfig } from "./config";

/**
 * Avalia uma feature flag com fallback seguro (US-15, ADR-0008).
 *
 * `useFlag` sozinho devolve `false` enquanto as flags não carregaram, para
 * qualquer flag não declarada — o que não é o mesmo que "o padrão antigo e
 * conhecido" de toda flag (`ops-desligar-gemini`, por exemplo, tem
 * `padrao_seguro: true`). Este hook cobre os casos em que o Unleash não é a
 * fonte da verdade agora — não configurado, ainda não carregou, ou falhou —
 * e cai no `padrao` que o CHAMADOR declara, nunca em `false` por acidente.
 */
export function useFeatureFlag(nome: string, padrao: boolean): boolean {
  // Chamados incondicionalmente (regra dos hooks) mesmo quando não há
  // Unleash configurado: nesse caso o FlagProvider usa o padrão "offline" da
  // biblioteca (bootstrap vazio), que reporta `flagsReady = true` de
  // imediato — sem a checagem de `unleashFrontendConfig()` abaixo, esse
  // "pronto" seria confundido com "avaliado de verdade".
  const { flagsReady, flagsError } = useFlagsStatus();
  const ativo = useFlag(nome);

  if (!unleashFrontendConfig()) return padrao;
  if (flagsError || !flagsReady) return padrao;
  return ativo;
}
