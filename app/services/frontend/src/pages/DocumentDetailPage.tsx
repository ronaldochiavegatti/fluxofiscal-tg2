import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import { useDocuments } from "../App";
import {
  apagarDocumento,
  confirmDocument,
  corrigirDocumento,
  deleteTransaction,
  getDocument,
  getDocumentAudit,
  updateTransaction,
} from "../api";
import { formatBRL, formatDataHoraBr, formatIsoDateBr, todayIso } from "../format";
import { useLocalStorage } from "../hooks/useLocalStorage";
import type { DemoUser, DocumentEntry, DocumentoDetalhe, RegistroAuditoria, TxType, UploadStructured } from "../types";
import { useAparencia } from "../aparencia/AparenciaContext";
import { useAvisos } from "../components/Avisos";
import { Botao, classesBotao } from "../components/Botao";
import { CabecalhoPagina, EstadoVazio } from "../components/interacao";

function LinkVoltar() {
  return (
    <Link to="/documents" className={`${classesBotao("discreto", "sm")} -ml-3 mb-2`}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="m15 6-6 6 6 6" />
      </svg>
      Documentos
    </Link>
  );
}

function valorDe(campos: Record<string, unknown> | undefined): number | null {
  const v = campos?.["value"];
  return typeof v === "number" ? v : null;
}

// US-22: "de onde veio este número". Busca a trilha do documento no servidor e
// mostra o valor extraído, o método e a correção humana. Se não houver trilha
// (flag desligada, id só do localStorage), o componente não renderiza nada.
function TrilhaAuditoria({ docId }: { docId: string }) {
  const [registros, setRegistros] = useState<RegistroAuditoria[] | null>(null);

  useEffect(() => {
    let vivo = true;
    getDocumentAudit(docId)
      .then((r) => vivo && setRegistros(r.registros))
      .catch(() => vivo && setRegistros([]));
    return () => {
      vivo = false;
    };
  }, [docId]);

  const { visualNovo } = useAparencia();

  if (!registros || registros.length === 0) return null;

  if (visualNovo) {
    return (
      <section className="painel painel-lista mt-6" aria-labelledby="titulo-historico">
        <div className="border-b border-borda px-5 py-4">
          <h2 id="titulo-historico" className="m-0 text-lg font-semibold text-tinta-forte">
            Histórico de alterações
          </h2>
          <p className="mb-0 mt-1 text-sm text-tinta-suave">
            Cada mudança fica registrada e não pode ser apagada, para você saber de onde veio cada número.
          </p>
        </div>
        <div className="tabela-rolavel">
          <table className="table mt-0 min-w-[520px]">
            <thead>
              <tr>
                <th scope="col">Quando</th>
                <th scope="col">O que aconteceu</th>
                <th scope="col" className="num">
                  Valor antes
                </th>
                <th scope="col" className="num">
                  Valor depois
                </th>
              </tr>
            </thead>
            <tbody>
              {registros.map((reg) => {
                const antes = valorDe(reg.antes?.campos as Record<string, unknown> | undefined);
                const depois = valorDe(reg.depois);
                return (
                  <tr key={reg._id}>
                    <td className="tabular-nums">{formatDataHoraBr(reg.em)}</td>
                    <td>
                      {reg.acao === "documento.corrigido"
                        ? "Você corrigiu os dados"
                        : reg.acao === "documento.confirmado"
                          ? "Você confirmou os dados"
                          : "Sistema leu a nota"}
                      {reg.antes?.metodo && (
                        <span className="text-tinta-suave"> ({reg.antes.metodo === "gemini" ? "com IA" : reg.antes.metodo})</span>
                      )}
                    </td>
                    <td className="num">{antes != null ? formatBRL(antes) : "—"}</td>
                    <td className="num font-semibold text-tinta-forte">{depois != null ? formatBRL(depois) : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    );
  }

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <div className="pill">Trilha de auditoria</div>
      <div className="muted" style={{ marginTop: 6 }}>
        Registro imutável de cada mudança neste documento — encadeado por hash.
      </div>
      <div className="tabela-rolavel">
        <table className="table" style={{ marginTop: 12 }}>
          <thead>
            <tr>
              <th>Quando</th>
              <th>O quê</th>
              <th>Antes</th>
              <th>Depois</th>
            </tr>
          </thead>
          <tbody>
            {registros.map((r) => {
              const antes = valorDe(r.antes?.campos as Record<string, unknown> | undefined);
              const depois = valorDe(r.depois);
              return (
                <tr key={r._id}>
                  <td>{formatDataHoraBr(r.em)}</td>
                  <td>
                    {r.acao === "documento.corrigido"
                      ? "Corrigido"
                      : r.acao === "documento.confirmado"
                        ? "Confirmado"
                        : "Extraído"}
                    {r.antes?.metodo && (
                      <span className="muted"> · {r.antes.metodo}</span>
                    )}
                  </td>
                  <td>{antes != null ? formatBRL(antes) : "—"}</td>
                  <td>{depois != null ? formatBRL(depois) : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/**
 * O que a tela mostra, venha a nota do navegador (localStorage) ou do
 * histórico no servidor (flag `documentos-persistidos`, #95).
 */
type Nota = {
  id: string;
  filename: string;
  uploadedAt: string;
  ocrText: string;
  structured: UploadStructured;
  txType: TxType;
  /** Lançamento no limite; nulo enquanto a nota só foi lida. */
  transacao: { tx_date: string; amount: number; source?: string | null } | null;
  /** Já foi salva (tem transação). Nota só lida é conferida e salva aqui mesmo. */
  confirmada: boolean;
};

/**
 * Confirmação antes de apagar (#96). Fica na página, não num `confirm()` do
 * navegador, para dizer o que sai junto: o lançamento no faturamento.
 */
function ConfirmarApagar({
  nota,
  visualNovo,
  apagando,
  erro,
  onApagar,
  onCancelar,
}: {
  nota: Nota;
  visualNovo: boolean;
  apagando: boolean;
  erro: string | null;
  onApagar: () => void;
  onCancelar: () => void;
}) {
  const titulo = useRef<HTMLHeadingElement>(null);
  useEffect(() => titulo.current?.focus(), []);
  const efeito = nota.transacao
    ? `O lançamento de ${formatBRL(nota.transacao.amount)} sai do seu ${
        nota.txType === "compra" ? "registro de despesas" : "faturamento"
      }, e o painel deixa de contá-lo.`
    : "Ela ainda não foi lançada no seu limite, então o painel não muda.";
  return (
    <section
      className={visualNovo ? "painel mt-6 border-limite-estourado-borda" : "card"}
      style={visualNovo ? undefined : { marginTop: 16 }}
      role="alertdialog"
      aria-labelledby="titulo-apagar"
      aria-describedby="texto-apagar"
    >
      <h2 id="titulo-apagar" ref={titulo} tabIndex={-1} className="m-0 text-lg font-semibold text-limite-estourado outline-none">
        Apagar {nota.filename}?
      </h2>
      <p id="texto-apagar" className="mb-0 mt-1 text-tinta-leve">
        {efeito} O arquivo também é apagado. Não dá para desfazer.
      </p>
      <div className="mt-5 flex flex-wrap gap-2.5">
        <Botao variante="perigo" onClick={onApagar} carregando={apagando}>
          {apagando ? "Apagando a nota" : "Apagar nota"}
        </Botao>
        <Botao variante="secundario" onClick={onCancelar} disabled={apagando}>
          Cancelar
        </Botao>
      </div>
      {erro && (
        <p className="mb-0 mt-3 text-limite-estourado" role="alert">
          Não foi possível apagar: {erro}. A nota continua salva; tente de novo.
        </p>
      )}
    </section>
  );
}

function notaLocal(doc: DocumentEntry): Nota {
  return {
    id: doc.id,
    filename: doc.filename,
    uploadedAt: doc.uploadedAt,
    ocrText: doc.ocrText,
    structured: doc.structured,
    txType: doc.limitsTransaction?.tx_type ?? "venda",
    transacao: doc.limitsTransaction ?? null,
    confirmada: true,
  };
}

// O Mongo grava em UTC sem fuso no texto; sem o "Z" o navegador leria como hora local.
const comFuso = (iso: string) => (/(Z|[+-]\d\d:\d\d)$/i.test(iso) ? iso : `${iso}Z`);

function notaDoServidor(d: DocumentoDetalhe): Nota {
  const lido = d.structured_data ?? {};
  const salvo = d.confirmacao?.campos;
  const filename = d.original_filename ?? "Nota";
  return {
    id: d.documento_id,
    filename,
    uploadedAt: d.criado_em ? comFuso(d.criado_em) : "",
    ocrText: d.ocr_text ?? "",
    // Salva: o que o usuário confirmou (com correções). Senão, o que foi lido.
    structured: salvo ? { ...salvo, confidence: lido.confidence } : lido,
    txType: salvo?.tx_type ?? lido.tx_type_sugerido ?? "venda",
    transacao:
      salvo && salvo.date && salvo.value != null
        ? { tx_date: salvo.date, amount: salvo.value, source: `upload:${filename}` }
        : null,
    confirmada: d.estado === "confirmado",
  };
}

export function DocumentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { docs, updateDoc, removeDoc } = useDocuments();
  const navigate = useNavigate();
  const [user] = useLocalStorage<DemoUser | null>("demo-user", null);
  const local = docs.find((d) => d.id === id);

  // #95: com o histórico no servidor, o id da lista é do Mongo e não está no
  // navegador — a nota é buscada no Documents.
  const [remota, setRemota] = useState<Nota | null>(null);
  const [buscaRemota, setBuscaRemota] = useState<"carregando" | "pronta">("carregando");

  useEffect(() => {
    if (local || !id) return;
    let vivo = true;
    getDocument(id)
      .then((d) => vivo && setRemota(notaDoServidor(d)))
      .catch(() => undefined)
      .finally(() => vivo && setBuscaRemota("pronta"));
    return () => {
      vivo = false;
    };
  }, [id, local]);

  const nota = local ? notaLocal(local) : remota;

  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [amount, setAmount] = useState("");
  const [txDate, setTxDate] = useState(todayIso());
  const [cnpjEmitente, setCnpjEmitente] = useState("");
  const [cnpjDestinatario, setCnpjDestinatario] = useState("");
  const [description, setDescription] = useState("");
  const [txType, setTxType] = useState<TxType>("venda");
  const [confirmandoApagar, setConfirmandoApagar] = useState(false);
  const [apagando, setApagando] = useState(false);
  const [erroApagar, setErroApagar] = useState<string | null>(null);
  const { visualNovo } = useAparencia();
  const avisar = useAvisos();

  if (!nota && buscaRemota === "carregando") {
    return visualNovo ? (
      <div>
        <LinkVoltar />
        <div className="painel mt-6 space-y-3" aria-busy="true" aria-label="Carregando a nota">
          {[0, 1, 2].map((n) => (
            <div key={n} className="esqueleto h-11" />
          ))}
        </div>
      </div>
    ) : (
      <div className="card" style={{ marginTop: 16 }}>
        <div className="muted">Carregando a nota…</div>
      </div>
    );
  }

  if (!nota && visualNovo) {
    return (
      <div>
        <LinkVoltar />
        <EstadoVazio
          titulo="Nota não encontrada"
          texto="Ela pode ter sido apagada no reset dos dados de teste ou enviada de outro aparelho sem o histórico no servidor."
          acao={
            <Link to="/documents" className={classesBotao("secundario")}>
              Ver todos os documentos
            </Link>
          }
        />
        {id && <TrilhaAuditoria docId={id} />}
      </div>
    );
  }

  if (!nota) {
    return (
      <div>
        <div className="card" style={{ marginTop: 16 }}>
          <div className="muted">
            Documento não encontrado neste navegador nem no servidor. Se ele foi processado no
            servidor, a trilha de auditoria abaixo mostra o histórico dele.
          </div>
          <Link to="/documents" className="mt-2 inline-block text-acento-claro">
            Voltar
          </Link>
        </div>
        {id && <TrilhaAuditoria docId={id} />}
      </div>
    );
  }

  const currentTxType: TxType = nota.txType;

  const startEditing = () => {
    setAmount(nota.structured.value != null ? String(nota.structured.value) : "");
    setTxDate(nota.structured.date || todayIso());
    setCnpjEmitente(nota.structured.cnpj_emitente || "");
    setCnpjDestinatario(nota.structured.cnpj_destinatario || "");
    setDescription(nota.structured.description || "");
    setTxType(currentTxType);
    setSaveError(null);
    setEditing(true);
  };

  const salvarNoServidor = async () => {
    const campos = {
      amount: Number(amount),
      tx_date: txDate,
      tx_type: txType,
      cnpj_emitente: cnpjEmitente || null,
      cnpj_destinatario: cnpjDestinatario || null,
      description: description || null,
    };
    if (nota.confirmada) {
      setRemota(notaDoServidor(await corrigirDocumento(nota.id, campos)));
      return;
    }
    // Só lida: salvar aqui é a mesma confirmação da tela de envio.
    await confirmDocument({
      ...campos,
      email: user?.email ?? "",
      source_filename: nota.filename,
      ocr_text: nota.ocrText || null,
      documento_id: nota.id,
    });
    setRemota(notaDoServidor(await getDocument(nota.id)));
  };

  const salvarLocal = async (doc: DocumentEntry) => {
    let updatedTx = doc.limitsTransaction ?? null;
    if (doc.limitsTransaction) {
      updatedTx = await updateTransaction(doc.limitsTransaction.id, {
        amount: Number(amount),
        tx_date: txDate,
        tx_type: txType,
      });
    }
    updateDoc(doc.id, {
      structured: {
        ...doc.structured,
        value: Number(amount),
        date: txDate,
        cnpj_emitente: cnpjEmitente || null,
        cnpj_destinatario: cnpjDestinatario || null,
        description: description || null,
      },
      limitsTransaction: updatedTx,
    });
  };

  const handleApagar = async () => {
    setApagando(true);
    setErroApagar(null);
    try {
      if (local) {
        if (local.limitsTransaction) await deleteTransaction(local.limitsTransaction.id);
        removeDoc(local.id);
      } else {
        await apagarDocumento(nota.id);
      }
      avisar(
        "sucesso",
        nota.transacao ? "Nota apagada. O valor dela saiu do painel." : "Nota apagada.",
      );
      navigate("/documents");
    } catch (err) {
      setErroApagar((err as Error).message);
      setApagando(false);
    }
  };

  const pedirApagar = () => {
    setEditing(false);
    setErroApagar(null);
    setConfirmandoApagar(true);
  };

  const confirmacaoApagar = confirmandoApagar && (
    <ConfirmarApagar
      nota={nota}
      visualNovo={visualNovo}
      apagando={apagando}
      erro={erroApagar}
      onApagar={handleApagar}
      onCancelar={() => setConfirmandoApagar(false)}
    />
  );

  const handleSave = async () => {
    if (!amount) return;
    setSaving(true);
    setSaveError(null);
    try {
      if (local) await salvarLocal(local);
      else await salvarNoServidor();
      setEditing(false);
      avisar("sucesso", "Alterações salvas. O painel já mostra os novos valores.");
    } catch (err) {
      setSaveError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  if (visualNovo) {
    const valor = nota.structured.value;
    const campos: { rotulo: string; valor: string; numerico?: boolean }[] = [
      { rotulo: "Data da nota", valor: nota.structured.date ? formatIsoDateBr(nota.structured.date) : "—", numerico: true },
      { rotulo: "CNPJ de quem emitiu", valor: nota.structured.cnpj_emitente || "—", numerico: true },
      { rotulo: "CNPJ de quem recebeu", valor: nota.structured.cnpj_destinatario || "—", numerico: true },
      { rotulo: "Descrição", valor: nota.structured.description || "—" },
      {
        rotulo: "Confiança da leitura",
        valor: nota.structured.confidence ? `${Math.round(nota.structured.confidence * 100)}%` : "—",
        numerico: true,
      },
    ];

    return (
      <div>
        <LinkVoltar />
        <CabecalhoPagina
          titulo={nota.filename}
          descricao={`Enviada em ${formatDataHoraBr(nota.uploadedAt)}`}
          acoes={
            !editing &&
            !confirmandoApagar && (
              <div className="flex flex-wrap gap-2.5">
                <Botao variante="secundario" onClick={startEditing}>
                  {nota.confirmada ? "Corrigir dados" : "Conferir e salvar"}
                </Botao>
                <Botao variante="perigo" onClick={pedirApagar}>
                  Apagar
                </Botao>
              </div>
            )
          }
        />

        {confirmacaoApagar}

        {!editing ? (
          <section className="painel mt-6" aria-label="Dados da nota">
            <p className="m-0 text-tinta-suave">{currentTxType === "compra" ? "Compra" : "Venda"}</p>
            <p className="valor m-0 mt-1 text-[clamp(32px,6vw,44px)] leading-none">{valor ? formatBRL(valor) : "Sem valor"}</p>
            <p className="mb-0 mt-3 max-w-[60ch] text-tinta-leve">
              {nota.transacao
                ? currentTxType === "compra"
                  ? `Lançada como despesa em ${formatIsoDateBr(nota.transacao.tx_date)}. Não conta para o limite do MEI.`
                  : `Lançada como venda em ${formatIsoDateBr(nota.transacao.tx_date)}. Já conta no seu limite anual.`
                : "Ainda não foi lançada no seu limite."}
            </p>

            <dl className="m-0 mt-6 grid gap-x-8 gap-y-5 border-t border-borda pt-6 sm:grid-cols-2 lg:grid-cols-3">
              {campos.map((campo) => (
                <div key={campo.rotulo} className="min-w-0">
                  <dt className="text-sm text-tinta-suave">{campo.rotulo}</dt>
                  <dd className={`m-0 mt-1 text-tinta-forte ${campo.numerico ? "tabular-nums" : ""}`}>{campo.valor}</dd>
                </div>
              ))}
            </dl>
          </section>
        ) : (
          <section className="painel mt-6" aria-labelledby="titulo-correcao">
            <h2 id="titulo-correcao" className="m-0 text-lg font-semibold text-tinta-forte">
              Corrigir dados da nota
            </h2>
            <p className="mb-0 mt-1 text-tinta-suave">
              Valor, data e tipo são atualizados no seu limite; o painel e o agente passam a usar os novos valores.
            </p>

            <fieldset className="m-0 mt-6 border-0 p-0">
              <legend className="mb-2 p-0 font-semibold text-tinta-leve">Esta nota é</legend>
              <div className="flex flex-col gap-2.5 sm:flex-row">
                <button type="button" className="escolha" aria-pressed={txType === "venda"} onClick={() => setTxType("venda")}>
                  <span className="font-semibold text-tinta-forte">Venda</span>
                  <span className="text-sm text-tinta-suave">Conta para o limite do MEI.</span>
                </button>
                <button type="button" className="escolha" aria-pressed={txType === "compra"} onClick={() => setTxType("compra")}>
                  <span className="font-semibold text-tinta-forte">Compra</span>
                  <span className="text-sm text-tinta-suave">Entra como despesa, fora do limite.</span>
                </button>
              </div>
            </fieldset>

            <div className="mt-6 grid gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="editar-valor">Valor (R$)</label>
                <input
                  id="editar-valor"
                  type="number"
                  inputMode="decimal"
                  step="0.01"
                  min="0"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  aria-describedby="editar-valor-extenso"
                  required
                />
                <div id="editar-valor-extenso" className="mt-1 text-sm text-tinta-suave">
                  {amount && Number.isFinite(Number(amount)) ? formatBRL(Number(amount)) : "Informe o valor total da nota"}
                </div>
              </div>
              <div>
                <label htmlFor="editar-data">Data</label>
                <input id="editar-data" type="date" value={txDate} onChange={(e) => setTxDate(e.target.value)} required />
              </div>
              <div>
                <label htmlFor="editar-emitente">CNPJ de quem emitiu</label>
                <input
                  id="editar-emitente"
                  type="text"
                  inputMode="numeric"
                  value={cnpjEmitente}
                  onChange={(e) => setCnpjEmitente(e.target.value)}
                  placeholder="00.000.000/0000-00"
                />
              </div>
              <div>
                <label htmlFor="editar-destinatario">CNPJ de quem recebeu</label>
                <input
                  id="editar-destinatario"
                  type="text"
                  inputMode="numeric"
                  value={cnpjDestinatario}
                  onChange={(e) => setCnpjDestinatario(e.target.value)}
                  placeholder="00.000.000/0000-00"
                />
              </div>
              <div className="sm:col-span-2">
                <label htmlFor="editar-descricao">Descrição</label>
                <input id="editar-descricao" type="text" value={description} onChange={(e) => setDescription(e.target.value)} />
              </div>
            </div>

            <div className="mt-6 flex flex-wrap items-center gap-2.5 border-t border-borda pt-5">
              <Botao onClick={handleSave} carregando={saving} disabled={!amount}>
                {saving ? "Salvando alterações" : "Salvar alterações"}
              </Botao>
              <Botao variante="secundario" onClick={() => setEditing(false)} disabled={saving}>
                Cancelar
              </Botao>
            </div>
            {saveError && (
              <p className="mb-0 mt-3 text-limite-estourado" role="alert">
                Não foi possível salvar: {saveError}. Suas correções continuam aqui; tente de novo.
              </p>
            )}
          </section>
        )}

        <details className="painel mt-6">
          <summary className="cursor-pointer font-semibold text-tinta-leve">Ver o texto lido da nota</summary>
          <pre className="mb-0 mt-4 max-h-80 overflow-auto whitespace-pre-wrap rounded-campo bg-fundo-poco p-4 font-sans text-sm text-tinta-leve">
            {nota.ocrText || "Nenhum texto lido."}
          </pre>
        </details>

        {id && <TrilhaAuditoria docId={id} />}
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="pill">Detalhe do Documento</div>
          <h2 className="title">{nota.filename}</h2>
          <div className="muted">
            Upload em {formatDataHoraBr(nota.uploadedAt)}
          </div>
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          {!editing && !confirmandoApagar && (
            <button
              type="button"
              className="cta bg-gradient-to-r from-limite-atencao to-limite-atencao-forte"
              onClick={startEditing}
            >
              Editar
            </button>
          )}
          {!editing && !confirmandoApagar && (
            <button
              type="button"
              className="cursor-pointer rounded-campo border border-limite-estourado/50 bg-transparent px-4 py-3 text-limite-estourado"
              onClick={pedirApagar}
            >
              Apagar
            </button>
          )}
          <Link to="/documents">
            <button className="cta">Voltar</button>
          </Link>
        </div>
      </div>

      {confirmacaoApagar}

      <div className="card" style={{ marginTop: 16 }}>
        {!editing ? (
          <>
            <div style={{ marginBottom: 12 }}>
              <span
                className={`badge ${
                  currentTxType === "compra"
                    ? "bg-limite-atencao/15 text-limite-atencao"
                    : "bg-limite-ok/15 text-limite-ok"
                }`}
              >
                {currentTxType === "compra" ? "Compra (despesa)" : "Venda (faturamento)"}
              </span>
            </div>
            <div className="card-grid">
              <div>
                <div className="muted">Valor</div>
                <div style={{ fontSize: 20, fontWeight: 700 }}>
                  {nota.structured.value
                    ? formatBRL(nota.structured.value)
                    : "—"}
                </div>
              </div>
              <div>
                <div className="muted">Data</div>
                <div>{nota.structured.date ? formatIsoDateBr(nota.structured.date) : "—"}</div>
              </div>
              <div>
                <div className="muted">CNPJ do emitente</div>
                <div>{nota.structured.cnpj_emitente || "—"}</div>
              </div>
              <div>
                <div className="muted">CNPJ do destinatário</div>
                <div>{nota.structured.cnpj_destinatario || "—"}</div>
              </div>
              <div>
                <div className="muted">Descrição</div>
                <div>{nota.structured.description || "—"}</div>
              </div>
              <div>
                <div className="muted">Confiança da extração</div>
                <div>{nota.structured.confidence ? `${Math.round(nota.structured.confidence * 100)}%` : "—"}</div>
              </div>
            </div>

            {nota.transacao && (
              <div className="section">
                <div className="pill">Transação registrada</div>
                <div style={{ marginTop: 8 }}>
                  Data: {formatIsoDateBr(nota.transacao.tx_date)} · Valor: R${" "}
                  {formatBRL(nota.transacao.amount)} · Tipo:{" "}
                  {currentTxType === "compra" ? "Compra" : "Venda"} · Origem:{" "}
                  {nota.transacao.source || "upload"}
                </div>
              </div>
            )}
          </>
        ) : (
          <>
            <div>
              <label>Tipo de operação</label>
              <div className="mb-1 mt-1.5 flex gap-2.5">
                <button
                  type="button"
                  onClick={() => setTxType("venda")}
                  className={`flex-1 cursor-pointer rounded-campo px-4 py-3 font-bold text-tinta ${
                    txType === "venda"
                      ? "border border-limite-ok/50 bg-limite-ok/15"
                      : "border border-borda-forte bg-veu/[0.03]"
                  }`}
                >
                  Venda (entrada de receita)
                </button>
                <button
                  type="button"
                  onClick={() => setTxType("compra")}
                  className={`flex-1 cursor-pointer rounded-campo px-4 py-3 font-bold text-tinta ${
                    txType === "compra"
                      ? "border border-limite-atencao/50 bg-limite-atencao/15"
                      : "border border-borda-forte bg-veu/[0.03]"
                  }`}
                >
                  Compra (despesa)
                </button>
              </div>
            </div>
            <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", marginTop: 10 }}>
              <div>
                <label>Valor (R$)</label>
                <input type="number" step="0.01" min="0" value={amount} onChange={(e) => setAmount(e.target.value)} required />
              </div>
              <div>
                <label>Data</label>
                <input type="date" value={txDate} onChange={(e) => setTxDate(e.target.value)} required />
              </div>
              <div>
                <label>CNPJ do emitente</label>
                <input type="text" value={cnpjEmitente} onChange={(e) => setCnpjEmitente(e.target.value)} placeholder="00.000.000/0000-00" />
              </div>
              <div>
                <label>CNPJ do destinatário</label>
                <input type="text" value={cnpjDestinatario} onChange={(e) => setCnpjDestinatario(e.target.value)} placeholder="00.000.000/0000-00" />
              </div>
              <div>
                <label>Descrição</label>
                <input type="text" value={description} onChange={(e) => setDescription(e.target.value)} />
              </div>
            </div>
            <div className="muted" style={{ marginTop: 10 }}>
              Ao salvar, o valor, a data e o tipo (venda/compra) são atualizados no serviço de
              Limites: o dashboard e o agente conversacional passam a refletir a alteração
              imediatamente.
            </div>
            <div style={{ marginTop: 14, display: "flex", gap: 10 }}>
              <button className="cta" onClick={handleSave} disabled={saving || !amount}>
                {saving ? "Salvando..." : "Salvar alterações"}
              </button>
              <button
                type="button"
                onClick={() => setEditing(false)}
                disabled={saving}
                className="cursor-pointer rounded-campo border border-borda-forte bg-transparent px-4 py-3 text-tinta"
              >
                Cancelar
              </button>
            </div>
            {saveError && <div className="mt-2.5 text-limite-estourado">{saveError}</div>}
          </>
        )}

        <div className="section">
          <div className="muted">Texto OCR</div>
          <div className="chat-bubble" style={{ marginTop: 6, whiteSpace: "pre-wrap" }}>
            {nota.ocrText || "Nenhum texto lido."}
          </div>
        </div>
      </div>

      {id && <TrilhaAuditoria docId={id} />}
    </div>
  );
}
