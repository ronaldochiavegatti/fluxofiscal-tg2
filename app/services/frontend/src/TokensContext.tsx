import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { consumeTokens, getTokenBalance } from "./api";
import type { TokenBalance, TokenReason } from "./types";

type TokensCtx = {
  balance: number | null;
  ilimitado: boolean;
  costs: Partial<Record<TokenReason, number>>;
  loading: boolean;
  refresh: () => Promise<void>;
  consume: (reason: TokenReason) => Promise<{ insufficient: boolean }>;
};

const TokensContext = createContext<TokensCtx | null>(null);

export function useTokens() {
  const ctx = useContext(TokensContext);
  if (!ctx) throw new Error("TokensContext not found");
  return ctx;
}

export function TokensProvider({ email, children }: { email: string; children: ReactNode }) {
  const [data, setData] = useState<TokenBalance | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await getTokenBalance(email);
      setData(resp);
    } finally {
      setLoading(false);
    }
  }, [email]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const consume = useCallback(
    async (reason: TokenReason) => {
      const resp = await consumeTokens(email, reason);
      setData((prev) => (prev ? { ...prev, balance: resp.balance } : prev));
      return { insufficient: resp.insufficient };
    },
    [email],
  );

  return (
    <TokensContext.Provider
      value={{
        balance: data?.balance ?? null,
        ilimitado: data?.ilimitado ?? false,
        costs: data?.costs ?? {},
        loading,
        refresh,
        consume,
      }}
    >
      {children}
    </TokensContext.Provider>
  );
}
