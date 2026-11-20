import {
  AtualizacaoConfiguracao,
  ConcentracaoCliente,
  ConfiguracaoFiscal,
  ConfirmDocumentPayload,
  ConfirmDocumentResponse,
  CorrecaoDocumentoPayload,
  DocumentoDetalhe,
  DocumentoPersistido,
  MesResumo,
  PontoSerieAcumulada,
  RegistroAuditoria,
  Ritmo,
  Summary,
  TokenBalance,
  TokenConsumeResult,
  TokenReason,
  Transaction,
  UpdateTransactionPayload,
  UploadResponse,
} from "./types";

// Resolve a base URL que funcione no navegador (localhost) e no build dockerizado.
const API_BASE = (() => {
  const envBase = import.meta.env.VITE_API_BASE_URL as string | undefined;
  if (envBase) return envBase;
  if (typeof window !== "undefined") {
    const { hostname } = window.location;
    if (hostname === "localhost") return "http://localhost:8000";
    if (hostname === "127.0.0.1") return "http://127.0.0.1:8000";
  }
  // fallback neutro (assume mesma origem; útil se servir frontend via gateway)
  return "";
})();

async function fetchJson<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers || {}),
    },
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Erro ${res.status} ao chamar ${path}`);
  }

  return res.json();
}

export async function getSummary(email: string): Promise<Summary> {
  return fetchJson<Summary>(`/limits/summary/${encodeURIComponent(email)}`);
}

export async function getRitmo(email: string, year?: number): Promise<Ritmo> {
  const qs = year ? `?year=${year}` : "";
  return fetchJson<Ritmo>(`/limits/ritmo/${encodeURIComponent(email)}${qs}`);
}

export async function getSerieAcumulada(
  email: string,
  year?: number
): Promise<PontoSerieAcumulada[]> {
  const qs = year ? `?year=${year}` : "";
  return fetchJson<PontoSerieAcumulada[]>(`/limits/ritmo/${encodeURIComponent(email)}/serie${qs}`);
}

export async function getMensal(email: string, year?: number): Promise<MesResumo[]> {
  const qs = year ? `?year=${year}` : "";
  return fetchJson<MesResumo[]>(`/limits/mensal/${encodeURIComponent(email)}${qs}`);
}

export async function getConcentracao(
  email: string,
  year?: number
): Promise<ConcentracaoCliente[]> {
  const qs = year ? `?year=${year}` : "";
  return fetchJson<ConcentracaoCliente[]>(`/limits/concentracao/${encodeURIComponent(email)}${qs}`);
}

export async function getTransactions(params: {
  email: string;
  year?: number;
  month?: number;
}): Promise<Transaction[]> {
  const qs = new URLSearchParams({ email: params.email });
  if (params.year) qs.append("year", params.year.toString());
  if (params.month) qs.append("month", params.month.toString());
  return fetchJson<Transaction[]>(`/limits/transactions?${qs.toString()}`);
}

/**
 * issue 100: o servidor recusou a foto por qualidade antes de ler. Carrega o
 * motivo e a dica para a tela mostrar, e não um texto de erro genérico.
 */
export class FotoIlegivel extends Error {
  constructor(
    public motivo: string,
    public dica: string,
    mensagem: string,
  ) {
    super(mensagem);
    this.name = "FotoIlegivel";
  }
}

export async function uploadDocument(
  file: File,
  email: string,
  userCnpj?: string,
  opcoes: { forcarLeitura?: boolean } = {},
): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("email", email);
  if (userCnpj) formData.append("user_cnpj", userCnpj);
  if (opcoes.forcarLeitura) formData.append("forcar_leitura", "true");

  const res = await fetch(`${API_BASE}/documents/upload`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const text = await res.text();
    if (res.status === 422) {
      try {
        const detalhe = JSON.parse(text).detail;
        if (detalhe?.codigo === "foto_ilegivel") {
          throw new FotoIlegivel(detalhe.motivo, detalhe.dica, detalhe.mensagem);
        }
      } catch (erro) {
        if (erro instanceof FotoIlegivel) throw erro;
      }
    }
    throw new Error(text || "Falha no upload");
  }

  return res.json();
}

export async function confirmDocument(
  payload: ConfirmDocumentPayload,
): Promise<ConfirmDocumentResponse> {
  return fetchJson<ConfirmDocumentResponse>(`/documents/confirm`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// US-20: histórico de documentos persistido no servidor (flag
// `documentos-persistidos`). Só é chamado quando a flag está ligada.
export async function listDocuments(email: string): Promise<DocumentoPersistido[]> {
  return fetchJson<DocumentoPersistido[]>(
    `/documents/documentos?email=${encodeURIComponent(email)}`,
  );
}

// US-18: acompanhamento do processamento assíncrono. A tela de upload chama em
// loop até o estado sair de "recebido"/"processando".
export async function getDocument(id: string): Promise<DocumentoDetalhe> {
  return fetchJson<DocumentoDetalhe>(`/documents/documentos/${encodeURIComponent(id)}`);
}

export async function reprocessDocument(id: string): Promise<{ estado: string }> {
  return fetchJson<{ estado: string }>(
    `/documents/documentos/${encodeURIComponent(id)}/reprocessar`,
    { method: "POST" },
  );
}

// US-22: trilha de auditoria de um documento — do valor extraído à correção
// humana. Disponível quando `documentos-persistidos` está ligada.
/** #95: corrige uma nota já salva — atualiza o Limits e o histórico no servidor. */
export async function corrigirDocumento(id: string, payload: CorrecaoDocumentoPayload): Promise<DocumentoDetalhe> {
  return fetchJson<DocumentoDetalhe>(`/documents/documentos/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

/** #96: apaga a nota — lançamento no Limits, registro e arquivo. */
export async function apagarDocumento(
  id: string,
): Promise<{ documento_id: string; transacao_removida: boolean; arquivo_removido: boolean }> {
  return fetchJson(`/documents/documentos/${encodeURIComponent(id)}`, { method: "DELETE" });
}

/** #96: apaga um lançamento (modo sem histórico no servidor). */
export async function deleteTransaction(id: number): Promise<{ id: number; removida: boolean }> {
  return fetchJson(`/limits/transactions/${id}`, { method: "DELETE" });
}

export async function getDocumentAudit(id: string): Promise<{
  documento_id: string;
  registros: RegistroAuditoria[];
}> {
  return fetchJson(`/documents/documentos/${encodeURIComponent(id)}/auditoria`);
}

export async function updateTransaction(
  id: number,
  payload: UpdateTransactionPayload,
): Promise<Transaction> {
  return fetchJson<Transaction>(`/limits/transactions/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function getTokenBalance(email: string): Promise<TokenBalance> {
  return fetchJson<TokenBalance>(`/billing/tokens/${encodeURIComponent(email)}`);
}

export async function consumeTokens(
  email: string,
  reason: TokenReason,
): Promise<TokenConsumeResult> {
  return fetchJson<TokenConsumeResult>(`/billing/tokens/consume`, {
    method: "POST",
    body: JSON.stringify({ email, reason }),
  });
}

export function getReportUrl(email: string, year: number): string {
  return `${API_BASE}/limits/report/${encodeURIComponent(email)}?year=${year}`;
}

export type ResetResult = {
  service: string;
  ok: boolean;
  detail?: string;
};

export async function resetAllData(email: string): Promise<ResetResult[]> {
  const calls: { service: string; path: string }[] = [
    { service: "limits", path: `/limits/reset/${encodeURIComponent(email)}` },
    { service: "billing", path: `/billing/reset/${encodeURIComponent(email)}` },
    { service: "agent", path: `/agent/reset/${encodeURIComponent(email)}` },
    // O e-mail faz o documents apagar também o histórico persistido no Mongo.
    { service: "documents", path: `/documents/reset?email=${encodeURIComponent(email)}` },
  ];

  const settled = await Promise.allSettled(
    calls.map(({ path }) =>
      fetch(`${API_BASE}${path}`, { method: "DELETE" }).then(async (res) => {
        if (!res.ok) throw new Error(await res.text());
        return res.json();
      }),
    ),
  );

  return settled.map((result, i) => ({
    service: calls[i].service,
    ok: result.status === "fulfilled",
    detail: result.status === "rejected" ? String(result.reason) : undefined,
  }));
}

export async function chatAgent(
  email: string,
  message: string,
): Promise<{ reply: string; sources: string[] }> {
  const res = await fetch(`${API_BASE}/agent/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, message }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Falha ao falar com agente");
  }

  const data = await res.json();
  return { reply: data.reply ?? "", sources: data.sources ?? [] };
}

/** Erro de validação da configuração: a mensagem do domínio, em texto. */
export class ErroConfiguracao extends Error {}

async function chamarConfiguracao(email: string, metodo: "GET" | "PUT" | "DELETE", corpo?: AtualizacaoConfiguracao) {
  const res = await fetch(`${API_BASE}/limits/configuracao/${encodeURIComponent(email)}`, {
    method: metodo,
    headers: { "Content-Type": "application/json" },
    body: corpo ? JSON.stringify(corpo) : undefined,
  });
  if (!res.ok) {
    const texto = await res.text();
    let detalhe = texto;
    try {
      const json = JSON.parse(texto) as { detail?: unknown };
      detalhe = typeof json.detail === "string" ? json.detail : "Valor fora da faixa permitida.";
    } catch {
      // Corpo não-JSON (gateway fora do ar): usa o texto como veio.
    }
    throw new ErroConfiguracao(detalhe || `Erro ${res.status} ao salvar a configuração`);
  }
  return (await res.json()) as ConfiguracaoFiscal;
}

export function getConfiguracao(email: string) {
  return chamarConfiguracao(email, "GET");
}

export function salvarConfiguracao(email: string, corpo: AtualizacaoConfiguracao) {
  return chamarConfiguracao(email, "PUT", corpo);
}

export function restaurarConfiguracao(email: string) {
  return chamarConfiguracao(email, "DELETE");
}
