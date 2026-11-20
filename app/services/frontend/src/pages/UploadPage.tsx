import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { confirmDocument, getDocument, reprocessDocument, uploadDocument, type FotoIlegivel } from "../api";
import { AvisoFotoRuim, type FotoRuim } from "../components/AvisoFotoRuim";
import { DICAS, MENSAGENS, avaliarArquivo, ehFoto } from "../qualidadeFoto";
import { useDocuments } from "../App";
import { useTokens } from "../TokensContext";
import { SoltarArquivo } from "../components/SoltarArquivo";
import { useUserCnpj } from "../useUserCnpj";
import { formatBRL, formatIsoDateBr, todayIso } from "../format";
import type { DemoUser, DocumentEntry, Repeticao, TxType, UploadResponse, UploadStructured } from "../types";
import { Link } from "react-router-dom";
import { useAparencia } from "../aparencia/AparenciaContext";
import { useAvisos } from "../components/Avisos";
import { AvisoNotaRepetida } from "../components/AvisoNotaRepetida";
import { Botao, classesBotao } from "../components/Botao";
import {
  CabecalhoPagina,
  Etapas,
  IconeVisto,
  ProgressoIndeterminado,
  formatarDuracao,
  useSegundos,
} from "../components/interacao";

const ETAPAS_ENVIO = ["Escolher o arquivo", "Ler a nota", "Conferir os dados", "Salvo"];

type Props = {
  user: DemoUser;
};

const digitos = (cnpj?: string | null) => (cnpj ?? "").replace(/\D/g, "");

/**
 * Sem `documentos-persistidos` o servidor não guarda histórico e não manda
 * `repeticoes`; a comparação usa as notas confirmadas neste navegador, pelo
 * mesmo critério do Documents (valor, data e CNPJ do emitente, se lido).
 */
function repeticoesLocais(docs: DocumentEntry[], lido?: UploadStructured): Repeticao[] {
  if (lido?.value == null || !lido.date) return [];
  const cnpj = digitos(lido.cnpj_emitente);
  return docs
    .filter((d) => {
      if (d.status !== "confirmed" || d.structured.value !== lido.value || d.structured.date !== lido.date) {
        return false;
      }
      const outro = digitos(d.structured.cnpj_emitente);
      return !cnpj || !outro || cnpj === outro;
    })
    .map((d) => ({
      documento_id: d.id,
      nome_original: d.filename,
      mesmo_arquivo: false,
      valor: d.structured.value ?? null,
      data: d.structured.date ?? null,
      tx_type: null,
      enviado_em: d.uploadedAt,
    }));
}

export function UploadPage({ user }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [result, setResult] = useState<UploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  // #93: enquanto houver repetição não decidida, a conferência não abre.
  const [repeticoes, setRepeticoes] = useState<Repeticao[]>([]);
  const [repeticaoAceita, setRepeticaoAceita] = useState(false);
  // issue 100: foto barrada pela checagem de qualidade, aguardando a decisão.
  const [fotoRuim, setFotoRuim] = useState<FotoRuim | null>(null);

  // US-18: acompanhamento do processamento assíncrono (flag `ocr-assincrono`).
  // Quando o /upload responde 202, `pendingId` guarda o documento e o efeito
  // abaixo faz polling até a extração terminar (ou falhar).
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [pendingEstado, setPendingEstado] = useState<string>("recebido");
  const [pendingErro, setPendingErro] = useState<string | null>(null);
  const [erroDocId, setErroDocId] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const pendingFilename = useRef<string>("");

  // Campos editáveis do rascunho, pré-preenchidos com o que a extração retornou.
  const [amount, setAmount] = useState("");
  const [txDate, setTxDate] = useState(todayIso());
  const [cnpjEmitente, setCnpjEmitente] = useState("");
  const [cnpjDestinatario, setCnpjDestinatario] = useState("");
  const [description, setDescription] = useState("");
  const [txType, setTxType] = useState<TxType | null>(null);
  const [txTypeAutoDetectado, setTxTypeAutoDetectado] = useState(false);

  const { visualNovo } = useAparencia();
  const avisar = useAvisos();
  const processando = loading || pendingId !== null;
  const segundos = useSegundos(processando);
  const { docs = [], addDoc } = useDocuments();
  const { balance, ilimitado, costs, consume } = useTokens();
  const [userCnpj] = useUserCnpj();
  const confirmCost = costs.document_confirm ?? 15;
  const insufficientBalance = !ilimitado && balance !== null && balance < confirmCost;

  const resetReview = () => {
    setResult(null);
    setFile(null);
    setSaved(false);
    setConfirmError(null);
    setPendingId(null);
    setPendingErro(null);
    setRepeticoes([]);
    setRepeticaoAceita(false);
    setFotoRuim(null);
  };

  const continuarRepetida = () => {
    setRepeticoes([]);
    setRepeticaoAceita(true);
  };

  const preencherRevisao = useCallback((structured: UploadStructured | undefined) => {
    setAmount(structured?.value != null ? String(structured.value) : "");
    setTxDate(structured?.date || todayIso());
    setCnpjEmitente(structured?.cnpj_emitente || "");
    setCnpjDestinatario(structured?.cnpj_destinatario || "");
    setDescription(structured?.description || "");
    setTxType(structured?.tx_type_sugerido ?? null);
    setTxTypeAutoDetectado(Boolean(structured?.tx_type_auto_detectado));
  }, []);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    void enviar(false);
  };

  const enviar = async (forcarLeitura: boolean) => {
    if (!file) return;
    setLoading(true);
    setError(null);
    setSaved(false);
    setPendingErro(null);
    setRepeticaoAceita(false);
    setFotoRuim(null);
    try {
      // issue 100: foto ruim não sai do aparelho. O servidor confere de novo.
      if (!forcarLeitura && ehFoto(file)) {
        const avaliacao = await avaliarArquivo(file);
        if (avaliacao && !avaliacao.legivel && avaliacao.motivo) {
          setFotoRuim({ mensagem: MENSAGENS[avaliacao.motivo], dica: DICAS[avaliacao.motivo], arquivo: file });
          return;
        }
      }
      const resp = await uploadDocument(file, user.email, userCnpj, { forcarLeitura });
      // US-18: 202 Accepted — o processamento ainda vai rodar na fila.
      if (resp.estado === "recebido" && resp.documento_id) {
        pendingFilename.current = resp.original_filename;
        setPendingEstado("recebido");
        setPendingId(resp.documento_id);
        return;
      }
      setResult(resp);
      setRepeticoes(resp.repeticoes ?? repeticoesLocais(docs, resp.structured_data));
      preencherRevisao(resp.structured_data);
    } catch (err) {
      if (err instanceof Error && err.name === "FotoIlegivel") {
        setFotoRuim({ mensagem: err.message, dica: (err as FotoIlegivel).dica, arquivo: file });
      } else {
        setError((err as Error).message);
      }
    } finally {
      setLoading(false);
    }
  };

  // Polling do documento em processamento (US-18).
  useEffect(() => {
    if (!pendingId) return;
    let vivo = true;
    const tick = async () => {
      try {
        const doc = await getDocument(pendingId);
        if (!vivo) return;
        setPendingEstado(doc.estado);
        if (doc.estado === "extraido") {
          setPendingId(null);
          setResult({
            original_filename: pendingFilename.current,
            size_bytes: 0,
            ocr_text: doc.ocr_text,
            extraction_method: doc.extraction_method,
            structured_data: doc.structured_data,
            limits_transaction: null,
            documento_id: doc.documento_id,
          });
          setRepeticoes(doc.repeticoes ?? []);
          preencherRevisao(doc.structured_data);
        } else if (doc.estado === "erro") {
          setPendingId(null);
          setErroDocId(doc.documento_id);
          setPendingErro(
            doc.erro?.motivo || "O processamento falhou. Tente enviar de novo.",
          );
        }
      } catch {
        /* rede instável: o próximo tick tenta de novo */
      }
    };
    void tick();
    const t = setInterval(tick, 1500);
    return () => {
      vivo = false;
      clearInterval(t);
    };
  }, [pendingId, preencherRevisao]);

  const handleRetry = async () => {
    if (!erroDocId) {
      resetReview();
      return;
    }
    setRetrying(true);
    setPendingErro(null);
    try {
      await reprocessDocument(erroDocId);
      setResult(null);
      setPendingEstado("processando");
      setPendingId(erroDocId);
      setErroDocId(null);
    } catch (err) {
      setPendingErro((err as Error).message);
    } finally {
      setRetrying(false);
    }
  };

  const handleConfirm = async () => {
    if (!result || !amount || !txType) return;
    setConfirming(true);
    setConfirmError(null);
    try {
      const resp = await confirmDocument({
        email: user.email,
        amount: Number(amount),
        tx_date: txDate,
        tx_type: txType,
        cnpj_emitente: cnpjEmitente || null,
        cnpj_destinatario: cnpjDestinatario || null,
        description: description || null,
        source_filename: result.original_filename,
        ocr_text: result.ocr_text || null,
        documento_id: result.documento_id ?? null,
      });

      addDoc({
        id: `${Date.now()}`,
        filename: result.original_filename,
        uploadedAt: new Date().toISOString(),
        sizeBytes: result.size_bytes,
        storagePath: result.storage_path,
        ocrText: result.ocr_text ?? "",
        structured: {
          value: Number(amount),
          date: txDate,
          cnpj_emitente: cnpjEmitente || null,
          cnpj_destinatario: cnpjDestinatario || null,
          description: description || null,
          confidence: result.structured_data?.confidence,
        },
        limitsTransaction: resp.limits_transaction,
        status: "confirmed",
        repetida: repeticaoAceita,
      });

      await consume("document_confirm");
      setSaved(true);
      avisar(
        "sucesso",
        `Nota salva: ${txType === "compra" ? "compra" : "venda"} de ${formatBRL(Number(amount))} em ${formatIsoDateBr(txDate)}.`
      );
    } catch (err) {
      setConfirmError((err as Error).message);
    } finally {
      setConfirming(false);
    }
  };

  const handleDiscard = () => {
    resetReview();
  };

  const missing = (v: string) => v.trim().length === 0;

  if (visualNovo) {
    const etapaAtual = saved ? 3 : result ? 2 : processando || pendingErro ? 1 : 0;
    const extraido = result?.structured_data;
    const origem = (lido: unknown) =>
      lido != null && lido !== "" ? (
        <span className="campo-origem campo-origem-lido">lido da nota</span>
      ) : (
        <span className="campo-origem campo-origem-falta">preencha</span>
      );
    const valorNumero = Number(amount);
    const statusLeitura = loading
      ? "Enviando o arquivo e lendo a nota"
      : pendingEstado === "processando"
        ? "Lendo o texto e os campos da nota"
        : "Arquivo recebido, aguardando a vez na fila";

    return (
      <div>
        <CabecalhoPagina
          titulo="Enviar nota"
          descricao="O sistema lê valor, data e CNPJ da nota. Nada entra no seu limite antes de você conferir e salvar."
        />

        <div className="mt-6">
          <Etapas etapas={ETAPAS_ENVIO} atual={etapaAtual} />
        </div>

        {processando && (
          <section className="painel mt-6" aria-busy="true" aria-labelledby="titulo-leitura">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 id="titulo-leitura" className="m-0 text-lg font-semibold text-tinta-forte">
                {statusLeitura}
              </h2>
              <span className="text-sm tabular-nums text-tinta-suave" aria-live="off">
                {formatarDuracao(segundos)}
              </span>
            </div>
            <p className="mb-4 mt-1 text-tinta-suave">
              {file?.name ?? pendingFilename.current}
              {pendingId && " · pode sair desta tela, a leitura continua e a conferência abre aqui quando terminar."}
            </p>
            <ProgressoIndeterminado rotulo={statusLeitura} />
            <ul className="m-0 mt-5 list-none space-y-2 p-0 text-[15px]">
              <li className="flex items-center gap-2.5">
                <span className={`etapa-marca h-6 w-6 ${loading ? "" : "border-limite-ok bg-limite-ok text-sobre-acento"}`}>
                  {loading ? "1" : <IconeVisto />}
                </span>
                {loading ? "Enviando o arquivo" : "Arquivo recebido"}
              </li>
              <li className={`flex items-center gap-2.5 ${pendingEstado === "processando" || loading ? "text-tinta-forte" : "text-tinta-suave"}`}>
                <span className="etapa-marca h-6 w-6">2</span>
                Lendo valor, data e CNPJ
              </li>
              <li className="flex items-center gap-2.5 text-tinta-suave">
                <span className="etapa-marca h-6 w-6">3</span>
                Abrir a conferência
              </li>
            </ul>
            {segundos >= 20 && (
              <p className="mb-0 mt-4 text-sm text-tinta-suave" role="status">
                Notas em foto ou PDF digitalizado demoram mais para ler. Ainda estamos trabalhando nela.
              </p>
            )}
          </section>
        )}

        {pendingErro && (
          <section className="painel mt-6 border-limite-estourado-borda" role="alert">
            <h2 className="m-0 text-lg font-semibold text-limite-estourado">Não foi possível ler esta nota</h2>
            <p className="mb-0 mt-1 text-tinta-leve">{pendingErro}</p>
            <p className="mb-0 mt-1 text-sm text-tinta-suave">
              Tente de novo. Se continuar, envie uma foto mais nítida ou o PDF original.
            </p>
            <div className="mt-5 flex flex-wrap gap-2.5">
              <Botao onClick={handleRetry} carregando={retrying}>
                {retrying ? "Tentando de novo" : "Tentar de novo"}
              </Botao>
              <Botao variante="secundario" onClick={resetReview}>
                Enviar outra nota
              </Botao>
            </div>
          </section>
        )}

        {fotoRuim && !processando && (
          <AvisoFotoRuim
            foto={fotoRuim}
            visualNovo
            onTirarOutra={resetReview}
            onEnviarMesmoAssim={() => void enviar(true)}
          />
        )}

        {!result && !processando && !pendingErro && !fotoRuim && (
          <form className="painel mt-6" onSubmit={handleSubmit}>
            <SoltarArquivo arquivo={file} onEscolher={setFile} desabilitado={loading} />
            {error && (
              <p className="mb-0 mt-3 text-limite-estourado" role="alert">
                O envio falhou: {error}. Confira sua conexão e tente de novo.
              </p>
            )}
            <div className="mt-5 flex flex-wrap items-center justify-between gap-4">
              <p className="m-0 max-w-[56ch] text-sm text-tinta-suave">
                Seu CNPJ <strong className="text-tinta-leve">{userCnpj || "não informado"}</strong> decide se a
                nota é venda (você emitiu) ou compra (você recebeu). Você altera em “Meu CNPJ”, no menu.
              </p>
              <Botao type="submit" disabled={!file}>
                {error ? "Tentar de novo" : "Enviar e ler a nota"}
              </Botao>
            </div>
          </form>
        )}

        {result && !saved && repeticoes.length > 0 && (
          <AvisoNotaRepetida
            repeticoes={repeticoes}
            visualNovo
            onContinuar={continuarRepetida}
            onCancelar={resetReview}
          />
        )}

        {result && !saved && repeticoes.length === 0 && (
          <section className="painel mt-6" aria-labelledby="titulo-conferencia">
            <h2 id="titulo-conferencia" className="m-0 text-lg font-semibold text-tinta-forte">
              Confira os dados de {result.original_filename}
            </h2>
            <p className="mb-0 mt-1 text-tinta-suave">
              {result.extraction_method === "gemini" ? "Lido com IA" : "Lido por regras (sem IA configurada)"}
              {result.structured_data?.confidence != null &&
                `, com ${Math.round(result.structured_data.confidence * 100)}% de confiança`}
              . Corrija o que estiver errado e preencha o que faltou.
            </p>

            <fieldset className="m-0 mt-6 border-0 p-0">
              <legend className="mb-2 p-0 font-semibold text-tinta-leve">
                Esta nota é
                {txTypeAutoDetectado ? (
                  <span className="campo-origem campo-origem-lido">detectado pelo CNPJ</span>
                ) : (
                  <span className="campo-origem campo-origem-falta">escolha</span>
                )}
              </legend>
              <div className="flex flex-col gap-2.5 sm:flex-row">
                <button type="button" className="escolha" aria-pressed={txType === "venda"} onClick={() => setTxType("venda")}>
                  <span className="font-semibold text-tinta-forte">Venda</span>
                  <span className="text-sm text-tinta-suave">Você emitiu. Conta para o limite do MEI.</span>
                </button>
                <button type="button" className="escolha" aria-pressed={txType === "compra"} onClick={() => setTxType("compra")}>
                  <span className="font-semibold text-tinta-forte">Compra</span>
                  <span className="text-sm text-tinta-suave">Você recebeu. Entra como despesa, fora do limite.</span>
                </button>
              </div>
            </fieldset>

            <div className="mt-6 grid gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="campo-valor">
                  Valor (R$) {origem(extraido?.value)}
                </label>
                <input
                  id="campo-valor"
                  type="number"
                  inputMode="decimal"
                  step="0.01"
                  min="0"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  placeholder="0,00"
                  aria-describedby="valor-por-extenso"
                  required
                />
                <div id="valor-por-extenso" className="mt-1 text-sm text-tinta-suave">
                  {amount && Number.isFinite(valorNumero) ? formatBRL(valorNumero) : "Informe o valor total da nota"}
                </div>
              </div>
              <div>
                <label htmlFor="campo-data">Data {origem(extraido?.date)}</label>
                <input id="campo-data" type="date" value={txDate} onChange={(e) => setTxDate(e.target.value)} required />
              </div>
              <div>
                <label htmlFor="campo-emitente">CNPJ de quem emitiu {origem(extraido?.cnpj_emitente)}</label>
                <input
                  id="campo-emitente"
                  type="text"
                  inputMode="numeric"
                  value={cnpjEmitente}
                  onChange={(e) => setCnpjEmitente(e.target.value)}
                  placeholder="00.000.000/0000-00"
                />
              </div>
              <div>
                <label htmlFor="campo-destinatario">CNPJ de quem recebeu {origem(extraido?.cnpj_destinatario)}</label>
                <input
                  id="campo-destinatario"
                  type="text"
                  inputMode="numeric"
                  value={cnpjDestinatario}
                  onChange={(e) => setCnpjDestinatario(e.target.value)}
                  placeholder="00.000.000/0000-00"
                />
              </div>
              <div className="sm:col-span-2">
                <label htmlFor="campo-descricao">Descrição {origem(extraido?.description)}</label>
                <input
                  id="campo-descricao"
                  type="text"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Ex.: bolo de aniversário, conserto elétrico"
                />
              </div>
            </div>

            <div className="mt-6 flex flex-wrap items-center gap-2.5 border-t border-borda pt-5">
              <Botao
                onClick={handleConfirm}
                carregando={confirming}
                disabled={missing(amount) || !txType || insufficientBalance}
              >
                {confirming ? "Salvando a nota" : "Salvar nota"}
              </Botao>
              <Botao variante="secundario" onClick={handleDiscard} disabled={confirming}>
                Descartar
              </Botao>
              <span className="text-sm text-tinta-suave">
                {!txType
                  ? "Escolha se é venda ou compra para salvar."
                  : missing(amount)
                    ? "Informe o valor para salvar."
                    : ilimitado
                      ? "Salvar não gasta créditos na demonstração."
                      : `Salvar usa ${confirmCost} créditos (saldo ${balance ?? "—"}).`}
              </span>
            </div>
            {insufficientBalance && (
              <p className="mb-0 mt-2 text-limite-estourado" role="alert">
                Saldo de créditos insuficiente para salvar.
              </p>
            )}
            {confirmError && (
              <p className="mb-0 mt-2 text-limite-estourado" role="alert">
                Não foi possível salvar: {confirmError}. Seus dados continuam aqui; tente de novo.
              </p>
            )}

            <details className="mt-6">
              <summary className="cursor-pointer text-sm font-semibold text-tinta-leve">Ver o texto lido da nota</summary>
              <pre className="mb-0 mt-3 max-h-72 overflow-auto whitespace-pre-wrap rounded-campo bg-fundo-poco p-4 font-sans text-sm text-tinta-leve">
                {result.ocr_text || "Nenhum texto lido."}
              </pre>
            </details>
          </section>
        )}

        {saved && (
          <section className="painel mt-6 border-limite-ok/40" aria-labelledby="titulo-salvo">
            <div className="flex items-start gap-3">
              <span className="aviso-icone mt-0.5 h-8 w-8">
                <IconeVisto />
              </span>
              <div>
                <h2 id="titulo-salvo" className="m-0 text-lg font-semibold text-tinta-forte">
                  {txType === "compra" ? "Compra salva" : "Venda salva"}
                </h2>
                <p className="mb-0 mt-1 text-tinta-leve">
                  <span className="valor">{formatBRL(Number(amount))}</span> em {formatIsoDateBr(txDate)}.{" "}
                  {txType === "compra"
                    ? "Entrou como despesa e não muda seu limite."
                    : "Já conta no seu limite anual; o painel mostra o novo total."}
                </p>
              </div>
            </div>
            <div className="mt-5 flex flex-wrap gap-2.5">
              <Botao onClick={resetReview}>Enviar outra nota</Botao>
              <Link to="/dashboard" className={classesBotao("secundario")}>
                Ver no painel
              </Link>
            </div>
          </section>
        )}
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="pill">Upload real com OCR</div>
          <h2 className="title">Envie uma nota fiscal</h2>
          <div className="muted">
            O backend salva o arquivo e roda OCR. Nada é lançado no seu limite MEI até você revisar e confirmar os dados abaixo.
          </div>
        </div>
      </div>

      {pendingId && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="pill">Processando na fila</div>
          <h3 className="title" style={{ fontSize: 18, margin: "6px 0" }}>
            Recebemos sua nota — pode fechar esta tela
          </h3>
          <div className="muted">
            O OCR e a extração rodam em segundo plano. Estado atual:{" "}
            <strong>{pendingEstado === "processando" ? "processando" : "na fila"}</strong>. A
            revisão abre sozinha quando terminar.
          </div>
          <div className="muted mt-3 flex items-center gap-2">
            <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-acento-claro" />
            Atualizando…
          </div>
        </div>
      )}

      {pendingErro && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="pill border-limite-estourado/30 bg-limite-estourado/15">
            Falha no processamento
          </div>
          <div className="mt-2.5">{pendingErro}</div>
          <div className="mt-3 flex gap-2.5">
            <button className="cta" onClick={handleRetry} disabled={retrying}>
              {retrying ? "Reenviando…" : "Tentar de novo"}
            </button>
            <button
              type="button"
              onClick={resetReview}
              className="cursor-pointer rounded-campo border border-borda-forte bg-transparent px-4 py-3 text-tinta"
            >
              Enviar outra nota
            </button>
          </div>
        </div>
      )}

      {fotoRuim && !loading && (
        <AvisoFotoRuim
          foto={fotoRuim}
          visualNovo={false}
          onTirarOutra={resetReview}
          onEnviarMesmoAssim={() => void enviar(true)}
        />
      )}

      {!result && !pendingId && !pendingErro && !fotoRuim && (
        <form className="card" onSubmit={handleSubmit} style={{ marginTop: 16 }}>
          <SoltarArquivo arquivo={file} onEscolher={setFile} desabilitado={loading} />
          <div className="muted mt-3 flex flex-wrap items-center justify-between gap-3 text-[13px]">
            <span>
              Seu CNPJ: <strong className="text-tinta-leve">{userCnpj || "não informado"}</strong> — usado para
              saber se a nota é venda (você emitiu) ou compra (você recebeu). Altere no menu lateral.
            </span>
            <button className="cta" type="submit" disabled={loading || !file}>
              {loading ? "Lendo a nota com IA..." : "Enviar e extrair dados →"}
            </button>
          </div>
          {error && <div className="mt-2.5 text-limite-estourado">{error}</div>}
        </form>
      )}

      {result && !saved && repeticoes.length > 0 && (
        <AvisoNotaRepetida
          repeticoes={repeticoes}
          visualNovo={false}
          onContinuar={continuarRepetida}
          onCancelar={resetReview}
        />
      )}

      {result && !saved && repeticoes.length === 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="page-header" style={{ marginBottom: 10 }}>
            <div>
              <div className="pill">Revisão obrigatória</div>
              <h3 className="title" style={{ fontSize: 18, margin: "6px 0" }}>
                Confira os dados antes de salvar
              </h3>
              <div className="muted">
                Extração: {result.extraction_method === "gemini" ? "Gemini (IA multimodal)" : "regras (sem Gemini configurado)"}
                {" · "}Confiança: {result.structured_data?.confidence != null
                  ? `${Math.round(result.structured_data.confidence * 100)}%`
                  : "—"}
                {" · "}Corrija qualquer campo que estiver errado ou em branco.
              </div>
            </div>
          </div>

          <div className="section mt-0">
            <label>Tipo de operação</label>
            <div className="mt-1.5 flex gap-2.5">
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
            <div className="muted mt-1.5 text-xs">
              {txTypeAutoDetectado ? (
                <span className="text-acento-claro">
                  Detectado automaticamente comparando o CNPJ do documento com o seu CNPJ. Confira antes de confirmar.
                </span>
              ) : (
                <span className="text-limite-atencao">
                  Não foi possível detectar automaticamente (o CNPJ do documento não bate com o seu). Selecione manualmente.
                </span>
              )}
              {" "}Só vendas contam para o limite anual do MEI; compras entram como despesa no balancete.
            </div>
          </div>

          <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", marginTop: 16 }}>
            <div>
              <label>
                Valor (R$) {missing(amount) && <span className="text-limite-atencao">· não detectado</span>}
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="0.00"
                required
              />
            </div>
            <div>
              <label>Data</label>
              <input type="date" value={txDate} onChange={(e) => setTxDate(e.target.value)} required />
            </div>
            <div>
              <label>
                CNPJ do emitente {missing(cnpjEmitente) && <span className="text-tinta-suave">· não detectado</span>}
              </label>
              <input type="text" value={cnpjEmitente} onChange={(e) => setCnpjEmitente(e.target.value)} placeholder="00.000.000/0000-00" />
            </div>
            <div>
              <label>
                CNPJ do destinatário {missing(cnpjDestinatario) && <span className="text-tinta-suave">· não detectado</span>}
              </label>
              <input type="text" value={cnpjDestinatario} onChange={(e) => setCnpjDestinatario(e.target.value)} placeholder="00.000.000/0000-00" />
            </div>
            <div>
              <label>
                Descrição {missing(description) && <span className="text-tinta-suave">· não detectado</span>}
              </label>
              <input type="text" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Ex.: Serviço de consultoria" />
            </div>
          </div>

          <div className="muted" style={{ marginTop: 14 }}>
            Confirmar esta nota vai consumir <strong>{confirmCost} tokens</strong>
            {ilimitado ? " (demo: tokens ilimitados)" : balance !== null && ` (saldo atual: ${balance})`}.
            {insufficientBalance && (
              <span className="text-limite-estourado"> Saldo insuficiente para confirmar.</span>
            )}
          </div>
          <div style={{ marginTop: 10, display: "flex", gap: 10 }}>
            <button
              className="cta"
              onClick={handleConfirm}
              disabled={confirming || missing(amount) || !txType || insufficientBalance}
            >
              {confirming ? "Salvando..." : "Confirmar e salvar"}
            </button>
            <button
              type="button"
              onClick={handleDiscard}
              disabled={confirming}
              className="cursor-pointer rounded-campo border border-borda-forte bg-transparent px-4 py-3 text-tinta"
            >
              Descartar
            </button>
          </div>
          {!txType && (
            <div className="mt-2 text-[13px] text-limite-atencao">
              Selecione se o documento é uma venda ou uma compra antes de confirmar.
            </div>
          )}
          {confirmError && <div className="mt-2.5 text-limite-estourado">{confirmError}</div>}

          <div className="section">
            <div className="muted">Texto OCR (para conferência)</div>
            <div className="chat-bubble" style={{ marginTop: 8, whiteSpace: "pre-wrap" }}>
              {result.ocr_text || "Nenhum texto lido."}
            </div>
          </div>
        </div>
      )}

      {saved && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="pill border-limite-ok/30 bg-limite-ok/15">
            {txType === "compra" ? "Compra confirmada" : "Venda confirmada"}
          </div>
          <div style={{ marginTop: 10 }}>
            Valor de {formatBRL(Number(amount))} registrado em {formatIsoDateBr(txDate)}
            {" "}como {txType === "compra" ? "compra (despesa)" : "venda (faturamento)"}.
          </div>
          <button className="cta" style={{ marginTop: 14 }} onClick={resetReview}>
            Enviar outra nota
          </button>
        </div>
      )}
    </div>
  );
}
