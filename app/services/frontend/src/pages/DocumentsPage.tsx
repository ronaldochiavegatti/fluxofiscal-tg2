import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useDocuments } from "../App";
import { listDocuments } from "../api";
import { useFeatureFlag } from "../flags/useFeatureFlag";
import { formatBRL, formatIsoDateBr } from "../format";
import { useLocalStorage } from "../hooks/useLocalStorage";
import type { DemoUser, DocumentoPersistido, EstadoDocumento, TxType } from "../types";
import { useAparencia } from "../aparencia/AparenciaContext";
import { classesBotao } from "../components/Botao";
import { CabecalhoPagina, EstadoVazio } from "../components/interacao";

type Linha = {
  id: string;
  filename: string;
  txType: TxType;
  value?: number | null;
  date?: string | null;
  cnpjEmitente?: string | null;
  confidence?: number | null;
  estado?: EstadoDocumento;
  repetida: boolean;
};

/** Nota salva mesmo depois do aviso de repetição (#93): o valor dela entrou de novo no faturamento. */
function SeloRepetida() {
  return (
    <span
      className="badge ml-2 bg-limite-atencao/15 align-middle text-limite-atencao"
      title="Salva mesmo após o aviso de que esta nota já tinha sido enviada"
    >
      Repetida
    </span>
  );
}

const ESTADO_ROTULO: Record<EstadoDocumento, string> = {
  recebido: "Recebido",
  processando: "Processando",
  extraido: "Extraído",
  confirmado: "Confirmado",
  descartado: "Descartado",
  erro: "Erro",
};

export function DocumentsPage() {
  const { docs } = useDocuments();
  const [user] = useLocalStorage<DemoUser | null>("demo-user", null);
  const persistido = useFeatureFlag("documentos-persistidos", false);

  const [remotos, setRemotos] = useState<DocumentoPersistido[] | null>(null);
  const [erroRemoto, setErroRemoto] = useState(false);

  useEffect(() => {
    if (!persistido || !user?.email) return;
    let vivo = true;
    listDocuments(user.email)
      .then((lista) => vivo && setRemotos(lista))
      .catch(() => vivo && setErroRemoto(true));
    return () => {
      vivo = false;
    };
  }, [persistido, user?.email]);

  const usandoServidor = persistido && remotos !== null && !erroRemoto;
  const { visualNovo } = useAparencia();
  const carregandoServidor = persistido && !!user?.email && remotos === null && !erroRemoto;

  const linhas: Linha[] = usandoServidor
    ? remotos!.map((d) => {
        // Confirmado: mostra o que o usuário confirmou (com correções), que é
        // o que entrou no faturamento; senão, o que a extração leu.
        const campos = d.confirmacao?.campos ?? d.extracao.campos;
        return {
          id: d.id,
          filename: d.nome_original,
          txType: d.confirmacao?.campos.tx_type ?? "venda",
          value: campos.value,
          date: campos.date,
          cnpjEmitente: campos.cnpj_emitente,
          confidence: d.extracao.confianca,
          estado: d.estado,
          repetida: (d.repeticao_de?.length ?? 0) > 0,
        };
      })
    : docs.map((doc) => ({
        id: doc.id,
        filename: doc.filename,
        txType: doc.limitsTransaction?.tx_type ?? "venda",
        value: doc.structured.value,
        date: doc.structured.date,
        cnpjEmitente: doc.structured.cnpj_emitente,
        confidence: doc.structured.confidence,
        repetida: Boolean(doc.repetida),
      }));

  if (visualNovo) {
    return (
      <div>
        <CabecalhoPagina
          titulo="Documentos"
          descricao={
            usandoServidor
              ? "Notas enviadas, salvas no servidor e visíveis em qualquer aparelho."
              : "Notas enviadas por este navegador."
          }
          acoes={
            <Link to="/upload" className={classesBotao("primario")}>
              Enviar nota
            </Link>
          }
        />

        {persistido && erroRemoto && (
          <p className="painel mt-6 text-tinta-leve" role="status">
            Não foi possível carregar o histórico do servidor. Mostrando as notas guardadas neste navegador.
          </p>
        )}

        {carregandoServidor ? (
          <div className="painel mt-6 space-y-3" aria-busy="true" aria-label="Carregando documentos">
            {[0, 1, 2, 3].map((n) => (
              <div key={n} className="esqueleto h-11" />
            ))}
          </div>
        ) : linhas.length === 0 ? (
          <div className="mt-6">
            <EstadoVazio
              titulo="Nenhuma nota enviada ainda"
              texto="Envie a primeira nota. O sistema lê os dados, você confere, e ela passa a contar no painel."
              icone={
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z" />
                  <path d="M14 3v5h5M9 13h6M9 17h4" />
                </svg>
              }
              acao={
                <Link to="/upload" className={classesBotao("primario")}>
                  Enviar a primeira nota
                </Link>
              }
            />
          </div>
        ) : (
          <div className="painel painel-lista mt-6">
            <p className="m-0 border-b border-borda px-5 py-3.5 text-sm text-tinta-suave">
              {linhas.length} {linhas.length === 1 ? "nota" : "notas"}
            </p>
            {/* Celular: um cartão tocável por nota, com o essencial. */}
            <ul className="m-0 list-none divide-y divide-borda p-0 sm:hidden">
              {linhas.map((l) => (
                <li key={l.id}>
                  <Link
                    to={`/documents/${l.id}`}
                    className="flex min-h-[64px] items-center gap-3 px-5 py-3.5 transition-colors hover:bg-veu/[0.03] focus-visible:shadow-foco focus-visible:outline-none"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-medium text-tinta-forte">
                        {l.filename}
                        {l.repetida && <SeloRepetida />}
                      </div>
                      <div className="mt-0.5 text-sm text-tinta-suave">
                        {l.txType === "compra" ? "Compra" : "Venda"}
                        {l.date && `, ${formatIsoDateBr(l.date)}`}
                        {usandoServidor && l.estado && `, ${ESTADO_ROTULO[l.estado].toLowerCase()}`}
                      </div>
                    </div>
                    <div className="valor shrink-0 whitespace-nowrap">{l.value ? formatBRL(l.value) : "—"}</div>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4 shrink-0 text-tinta-suave" aria-hidden="true">
                      <path d="m9 6 6 6-6 6" />
                    </svg>
                  </Link>
                </li>
              ))}
            </ul>
            <div className="tabela-rolavel hidden sm:block">
              <table className="table mt-0 min-w-[640px]">
                <thead>
                  <tr>
                    <th scope="col">Arquivo</th>
                    <th scope="col">Tipo</th>
                    {usandoServidor && <th scope="col">Situação</th>}
                    <th scope="col" className="num">
                      Valor
                    </th>
                    <th scope="col">Data</th>
                    <th scope="col">CNPJ de quem emitiu</th>
                    <th scope="col" className="num">
                      Confiança da leitura
                    </th>
                    <th scope="col">
                      <span className="sr-only">Ações</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {linhas.map((l) => (
                    <tr key={l.id}>
                      <td className="max-w-[240px] truncate font-medium text-tinta-forte" title={l.filename}>
                        {l.filename}
                        {l.repetida && <SeloRepetida />}
                      </td>
                      <td>{l.txType === "compra" ? "Compra" : "Venda"}</td>
                      {usandoServidor && <td>{l.estado ? ESTADO_ROTULO[l.estado] : "—"}</td>}
                      <td className="num font-semibold text-tinta-forte">{l.value ? formatBRL(l.value) : "—"}</td>
                      <td className="tabular-nums">{l.date ? formatIsoDateBr(l.date) : "—"}</td>
                      <td className="tabular-nums text-tinta-suave">{l.cnpjEmitente || "—"}</td>
                      <td className="num text-tinta-suave">{l.confidence ? `${Math.round(l.confidence * 100)}%` : "—"}</td>
                      <td className="text-right">
                        <Link
                          to={`/documents/${l.id}`}
                          className={classesBotao("discreto", "sm")}
                          aria-label={`Abrir ${l.filename}`}
                        >
                          Abrir
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="pill">Documentos</div>
          <h2 className="title">Uploads recentes</h2>
          <div className="muted">
            {usandoServidor
              ? "Sincronizado com o servidor — visível de qualquer dispositivo."
              : "Persistido em localStorage para a demo."}
          </div>
        </div>
        <Link to="/upload">
          <button className="cta">Novo upload</button>
        </Link>
      </div>

      {persistido && erroRemoto && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="muted">
            Não foi possível carregar o histórico do servidor. Mostrando o que está neste
            navegador.
          </div>
        </div>
      )}

      {linhas.length === 0 ? (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="muted">Ainda não há uploads. Envie um arquivo para ver aqui.</div>
        </div>
      ) : (
        <div className="card" style={{ marginTop: 16 }}>
          <table className="table">
            <thead>
              <tr>
                <th>Arquivo</th>
                <th>Tipo</th>
                {usandoServidor && <th>Estado</th>}
                <th>Valor</th>
                <th>Data</th>
                <th>CNPJ emitente</th>
                <th>Confiança</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {linhas.map((l) => (
                <tr key={l.id}>
                  <td>
                    {l.filename}
                    {l.repetida && <SeloRepetida />}
                  </td>
                  <td>
                    <span
                      className={`badge ${
                        l.txType === "compra"
                          ? "bg-limite-atencao/15 text-limite-atencao"
                          : "bg-limite-ok/15 text-limite-ok"
                      }`}
                    >
                      {l.txType === "compra" ? "Compra" : "Venda"}
                    </span>
                  </td>
                  {usandoServidor && <td>{l.estado ? ESTADO_ROTULO[l.estado] : "—"}</td>}
                  <td>{l.value ? formatBRL(l.value) : "—"}</td>
                  <td>{l.date ? formatIsoDateBr(l.date) : "—"}</td>
                  <td>{l.cnpjEmitente || "—"}</td>
                  <td>{l.confidence ? `${Math.round(l.confidence * 100)}%` : "—"}</td>
                  <td>
                    <Link to={`/documents/${l.id}`}>Detalhes</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
