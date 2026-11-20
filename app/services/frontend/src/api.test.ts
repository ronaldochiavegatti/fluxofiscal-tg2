import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ErroConfiguracao,
  FotoIlegivel,
  apagarDocumento,
  deleteTransaction,
  chatAgent,
  confirmDocument,
  consumeTokens,
  corrigirDocumento,
  getConcentracao,
  getConfiguracao,
  getDocument,
  getDocumentAudit,
  getMensal,
  getReportUrl,
  getRitmo,
  getSerieAcumulada,
  getSummary,
  getTokenBalance,
  getTransactions,
  listDocuments,
  reprocessDocument,
  resetAllData,
  restaurarConfiguracao,
  salvarConfiguracao,
  updateTransaction,
  uploadDocument,
} from "./api";

// `api.ts` é onde mora o contrato com o backend: qual URL, qual método, qual
// corpo, e o que acontece quando a resposta não é 2xx. É o que estes testes
// fixam — sem tocar rede.

type FakeRes = { ok?: boolean; status?: number; json?: unknown; text?: string };

let chamadas: { url: string; init?: RequestInit }[];

function responder(fila: FakeRes[]) {
  const restante = [...fila];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      chamadas.push({ url, init });
      const r = restante.shift() ?? {};
      return Promise.resolve({
        ok: r.ok ?? true,
        status: r.status ?? 200,
        json: () => Promise.resolve(r.json ?? {}),
        text: () => Promise.resolve(r.text ?? ""),
      });
    }),
  );
}

beforeEach(() => {
  chamadas = [];
});
afterEach(() => vi.unstubAllGlobals());

describe("montagem das requisições", () => {
  it("getSummary escapa o e-mail na URL", async () => {
    responder([{ json: { total_revenue: 10 } }]);
    await getSummary("maria+teste@mei.com.br");
    expect(chamadas[0].url).toContain("/limits/summary/maria%2Bteste%40mei.com.br");
  });

  it("getTransactions só inclui year/month quando informados", async () => {
    responder([{ json: [] }, { json: [] }]);
    await getTransactions({ email: "m@x.com" });
    expect(chamadas[0].url).toMatch(/\/limits\/transactions\?email=m%40x.com$/);

    await getTransactions({ email: "m@x.com", year: 2026, month: 3 });
    expect(chamadas[1].url).toContain("year=2026");
    expect(chamadas[1].url).toContain("month=3");
  });

  it("getRitmo monta a rota e só inclui year quando informado (US-25)", async () => {
    responder([{ json: {} }, { json: {} }]);
    await getRitmo("m@x.com");
    expect(chamadas[0].url).toMatch(/\/limits\/ritmo\/m%40x\.com$/);

    await getRitmo("m@x.com", 2026);
    expect(chamadas[1].url).toMatch(/\/limits\/ritmo\/m%40x\.com\?year=2026$/);
  });

  it("getSerieAcumulada monta a rota /serie e só inclui year quando informado (US-26)", async () => {
    responder([{ json: [] }, { json: [] }]);
    await getSerieAcumulada("m@x.com");
    expect(chamadas[0].url).toMatch(/\/limits\/ritmo\/m%40x\.com\/serie$/);

    await getSerieAcumulada("m@x.com", 2026);
    expect(chamadas[1].url).toMatch(/\/limits\/ritmo\/m%40x\.com\/serie\?year=2026$/);
  });

  it("uploadDocument envia multipart com file, email e user_cnpj", async () => {
    responder([{ json: { original_filename: "n.png" } }]);
    const file = new File([new Uint8Array([1])], "n.png", { type: "image/png" });
    await uploadDocument(file, "m@x.com", "12.345.678/0001-95");

    const body = chamadas[0].init?.body as FormData;
    expect(chamadas[0].url).toMatch(/\/documents\/upload$/);
    expect(chamadas[0].init?.method).toBe("POST");
    expect(body.get("email")).toBe("m@x.com");
    expect(body.get("user_cnpj")).toBe("12.345.678/0001-95");
    expect((body.get("file") as File).name).toBe("n.png");
  });

  it("uploadDocument omite user_cnpj quando não informado", async () => {
    responder([{ json: {} }]);
    await uploadDocument(new File([], "n.png"), "m@x.com");
    expect((chamadas[0].init?.body as FormData).has("user_cnpj")).toBe(false);
  });

  it("confirmDocument manda JSON no corpo", async () => {
    responder([{ json: { limits_transaction: null } }]);
    await confirmDocument({ email: "m@x.com", amount: 100, tx_date: "2026-03-01", tx_type: "venda" });
    expect(chamadas[0].init?.method).toBe("POST");
    expect(JSON.parse(chamadas[0].init?.body as string).amount).toBe(100);
  });

  it("getDocument e reprocessDocument montam a rota do documento (US-18)", async () => {
    responder([{ json: { estado: "extraido" } }, { json: { estado: "processando" } }]);
    await getDocument("doc 1");
    await reprocessDocument("doc 1");
    expect(chamadas[0].url).toContain("/documents/documentos/doc%201");
    expect(chamadas[1].url).toMatch(/\/documents\/documentos\/doc%201\/reprocessar$/);
    expect(chamadas[1].init?.method).toBe("POST");
  });

  it("corrigirDocumento usa PATCH na rota do documento (#95)", async () => {
    responder([{ json: { documento_id: "doc 1" } }]);
    await corrigirDocumento("doc 1", { amount: 10, tx_date: "2026-03-01", tx_type: "venda" });
    expect(chamadas[0].url).toMatch(/\/documents\/documentos\/doc%201$/);
    expect(chamadas[0].init?.method).toBe("PATCH");
    expect(JSON.parse(chamadas[0].init?.body as string).amount).toBe(10);
  });

  it("apagarDocumento e deleteTransaction usam DELETE (#96)", async () => {
    responder([{ json: {} }, { json: {} }]);
    await apagarDocumento("doc 1");
    await deleteTransaction(7);
    expect(chamadas[0].url).toMatch(/\/documents\/documentos\/doc%201$/);
    expect(chamadas[0].init?.method).toBe("DELETE");
    expect(chamadas[1].url).toMatch(/\/limits\/transactions\/7$/);
    expect(chamadas[1].init?.method).toBe("DELETE");
  });

  it("getDocumentAudit busca a trilha do documento (US-22)", async () => {
    responder([{ json: { documento_id: "doc-1", registros: [] } }]);
    await getDocumentAudit("doc-1");
    expect(chamadas[0].url).toMatch(/\/documents\/documentos\/doc-1\/auditoria$/);
  });

  it("updateTransaction usa PATCH", async () => {
    responder([{ json: {} }]);
    await updateTransaction(7, { amount: 50 });
    expect(chamadas[0].url).toMatch(/\/limits\/transactions\/7$/);
    expect(chamadas[0].init?.method).toBe("PATCH");
  });

  it("listDocuments passa o e-mail em query", async () => {
    responder([{ json: [] }]);
    await listDocuments("m@x.com");
    expect(chamadas[0].url).toContain("/documents/documentos?email=m%40x.com");
  });

  it("getTokenBalance e consumeTokens batem no billing", async () => {
    responder([{ json: { balance: 10 } }, { json: { charged: 15 } }]);
    await getTokenBalance("m@x.com");
    await consumeTokens("m@x.com", "document_confirm");
    expect(chamadas[0].url).toContain("/billing/tokens/m%40x.com");
    expect(chamadas[1].url).toMatch(/\/billing\/tokens\/consume$/);
    expect(JSON.parse(chamadas[1].init?.body as string).reason).toBe("document_confirm");
  });

  it("getMensal busca a série mensal do Limits (US-27)", async () => {
    responder([{ json: [] }]);
    await getMensal("m@x.com", 2026);
    expect(chamadas[0].url).toMatch(/\/limits\/mensal\/m%40x.com\?year=2026$/);
  });

  it("getConcentracao busca a concentração de cliente do Limits (US-27)", async () => {
    responder([{ json: [] }]);
    await getConcentracao("m@x.com", 2026);
    expect(chamadas[0].url).toMatch(/\/limits\/concentracao\/m%40x.com\?year=2026$/);
  });

  it("getReportUrl é pura e monta a query do ano", () => {
    expect(getReportUrl("m@x.com", 2026)).toContain("/limits/report/m%40x.com?year=2026");
  });

  it("chatAgent devolve reply e sources com defaults", async () => {
    responder([{ json: { reply: "olá" } }]);
    expect(await chatAgent("m@x.com", "oi")).toEqual({ reply: "olá", sources: [] });
  });
});

describe("tratamento de erro", () => {
  it("fetchJson lança com o texto do corpo quando a resposta não é ok", async () => {
    responder([{ ok: false, status: 422, text: "email inválido" }]);
    await expect(getSummary("x")).rejects.toThrow("email inválido");
  });

  it("uploadDocument lança em falha", async () => {
    responder([{ ok: false, status: 500, text: "" }]);
    await expect(uploadDocument(new File([], "n.png"), "m@x.com")).rejects.toThrow(/Falha no upload/);
  });

  it("uploadDocument transforma a recusa por qualidade em FotoIlegivel (issue 100)", async () => {
    const detalhe = { codigo: "foto_ilegivel", motivo: "tremida", mensagem: "A foto está tremida.", dica: "Apoie." };
    responder([{ ok: false, status: 422, text: JSON.stringify({ detail: detalhe }) }]);
    const erro = await uploadDocument(new File([], "n.jpg"), "m@x.com").catch((e) => e);
    expect(erro).toBeInstanceOf(FotoIlegivel);
    expect(erro.name).toBe("FotoIlegivel");
    expect(erro.message).toBe("A foto está tremida.");
    expect(erro.motivo).toBe("tremida");
    expect(erro.dica).toBe("Apoie.");
  });

  it("uploadDocument com 422 de outro tipo continua erro comum", async () => {
    responder([{ ok: false, status: 422, text: "email inválido" }]);
    const erro = await uploadDocument(new File([], "n.jpg"), "m@x.com").catch((e) => e);
    expect(erro).not.toBeInstanceOf(FotoIlegivel);
    expect(erro.message).toBe("email inválido");
  });

  it("uploadDocument só manda forcar_leitura quando pedido", async () => {
    responder([{ json: {} }, { json: {} }]);
    await uploadDocument(new File([], "n.jpg"), "m@x.com");
    await uploadDocument(new File([], "n.jpg"), "m@x.com", undefined, { forcarLeitura: true });
    expect((chamadas[0].init?.body as FormData).has("forcar_leitura")).toBe(false);
    expect((chamadas[1].init?.body as FormData).get("forcar_leitura")).toBe("true");
  });

  it("chatAgent lança em falha", async () => {
    responder([{ ok: false, status: 502, text: "" }]);
    await expect(chatAgent("m@x.com", "oi")).rejects.toThrow(/Falha ao falar com agente/);
  });

  it("resetAllData resolve por serviço, marcando os que falharam", async () => {
    responder([
      { json: { ok: true } },
      { ok: false, status: 500, text: "boom" },
      { json: { ok: true } },
      { json: { ok: true } },
    ]);
    const r = await resetAllData("m@x.com");
    expect(r.map((x) => x.service)).toEqual(["limits", "billing", "agent", "documents"]);
    expect(r[0].ok).toBe(true);
    expect(r[1].ok).toBe(false);
    expect(r[1].detail).toContain("boom");
  });

  it("resetAllData manda o e-mail ao documents para apagar o histórico persistido", async () => {
    responder([{ json: {} }, { json: {} }, { json: {} }, { json: {} }]);
    await resetAllData("m+1@x.com");
    const reset = chamadas.find((c) => c.url.includes("/documents/reset"));
    expect(reset?.url).toContain("/documents/reset?email=m%2B1%40x.com");
    expect(reset?.init?.method).toBe("DELETE");
  });
});

describe("configuração das regras e metas (#91)", () => {
  it("lê, grava (PUT com corpo JSON) e restaura (DELETE) pela rota do limits", async () => {
    responder([{ json: { email: "m@x.com" } }, { json: {} }, { json: {} }]);
    await getConfiguracao("m+1@x.com");
    expect(chamadas[0].url).toContain("/limits/configuracao/m%2B1%40x.com");
    expect(chamadas[0].init?.method).toBe("GET");

    await salvarConfiguracao("m@x.com", { parametros: { limiar_alerta: 0.7 } });
    expect(chamadas[1].init?.method).toBe("PUT");
    expect(JSON.parse(String(chamadas[1].init?.body))).toEqual({ parametros: { limiar_alerta: 0.7 } });

    await restaurarConfiguracao("m@x.com");
    expect(chamadas[2].init?.method).toBe("DELETE");
    expect(chamadas[2].init?.body).toBeUndefined();
  });

  it("erro 422 vira ErroConfiguracao com a mensagem do domínio", async () => {
    responder([{ ok: false, status: 422, text: JSON.stringify({ detail: "limiar_alerta deve estar entre 0 e 1" }) }]);
    const erro = await salvarConfiguracao("m@x.com", { parametros: { limiar_alerta: 2 } }).catch((e) => e);
    expect(erro).toBeInstanceOf(ErroConfiguracao);
    expect(erro.message).toBe("limiar_alerta deve estar entre 0 e 1");
  });

  it("detalhe que não é texto (validação do FastAPI) vira mensagem genérica", async () => {
    responder([{ ok: false, status: 422, text: JSON.stringify({ detail: [{ loc: ["body"] }] }) }]);
    const erro = await salvarConfiguracao("m@x.com", {}).catch((e) => e);
    expect(erro.message).toBe("Valor fora da faixa permitida.");
  });

  it("corpo que não é JSON (gateway fora do ar) mantém o texto", async () => {
    responder([{ ok: false, status: 502, text: "Bad Gateway" }]);
    const erro = await getConfiguracao("m@x.com").catch((e) => e);
    expect(erro.message).toBe("Bad Gateway");
  });
});
