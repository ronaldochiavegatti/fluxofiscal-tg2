import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { StatCard } from "../components/StatCard";
import { SectionCard } from "../components/SectionCard";
import { Markdown } from "../components/Markdown";
import { BarraProgresso } from "../components/BarraProgresso";
import { useTokens } from "../TokensContext";
import { Gauge } from "../components/Gauge";
import { PainelRitmo } from "../components/PainelRitmo";
import { CorridaContraLimite } from "../components/CorridaContraLimite";
import { MesAMes } from "../components/MesAMes";
import { OrigemFaturamento } from "../components/OrigemFaturamento";
import { ReguaLimite } from "../components/ReguaLimite";
import { Botao, classesBotao } from "../components/Botao";
import { useAparencia } from "../aparencia/AparenciaContext";
import {
  chatAgent,
  getConcentracao,
  getMensal,
  getReportUrl,
  getRitmo,
  getSerieAcumulada,
  getSummary,
  getTransactions,
  resetAllData,
} from "../api";
import { formatBRL, formatIsoDateBr, formatPercentual } from "../format";
import { useDocuments } from "../App";
import { useFeatureFlag } from "../flags/useFeatureFlag";
import { DEMO_CNPJ_PLACEHOLDER, useUserCnpj } from "../useUserCnpj";
import { CHAVE_HISTORICO_CHAT } from "./AgentPage";
import type {
  ConcentracaoCliente,
  DemoUser,
  MesResumo,
  PontoSerieAcumulada,
  Ritmo,
  Summary,
  Transaction,
} from "../types";

type Props = {
  user: DemoUser;
};

const BOTAO_SECUNDARIO =
  "inline-flex cursor-pointer items-center gap-2 rounded-campo border border-borda-forte bg-veu/[0.03] px-4 py-[11px] text-sm font-semibold text-tinta transition-colors hover:bg-veu/[0.07]";

const NOMES_MES = [
  "janeiro", "fevereiro", "março", "abril", "maio", "junho",
  "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
];

type FiltroTipo = "todas" | "venda" | "compra";

const PASSOS_INICIO = [
  { icone: "📄", titulo: "Envie uma nota", texto: "PDF, foto ou texto. A IA extrai valor, data e CNPJ.", para: "/upload" },
  { icone: "✅", titulo: "Revise e confirme", texto: "Venda conta para o limite; compra entra como despesa.", para: "/documents" },
  { icone: "💬", titulo: "Pergunte ao agente", texto: "Tire dúvidas do MEI com base nos seus números.", para: "/chat" },
];

export function DashboardPage({ user }: Props) {
  const dashboardV2 = useFeatureFlag("dashboard-v2", false);
  const { visualNovo } = useAparencia();
  // A régua do visual novo usa o ritmo para o marcador "hoje" e a projeção.
  const precisaRitmo = dashboardV2 || visualNovo;
  const clsPrimario = visualNovo ? classesBotao("primario") : "cta";
  const clsSecundario = visualNovo ? classesBotao("secundario") : BOTAO_SECUNDARIO;

  const [summary, setSummary] = useState<Summary | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [ritmo, setRitmo] = useState<Ritmo | null>(null);
  const [serieAcumulada, setSerieAcumulada] = useState<PontoSerieAcumulada[]>([]);
  const [mensal, setMensal] = useState<MesResumo[]>([]);
  const [concentracao, setConcentracao] = useState<ConcentracaoCliente[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [agentPreview, setAgentPreview] = useState<string>("");
  const [carregandoResumo, setCarregandoResumo] = useState(false);
  const [filtroTipo, setFiltroTipo] = useState<FiltroTipo>("todas");

  const { docs, clearDocs } = useDocuments();
  const { balance, ilimitado, costs } = useTokens();
  // Atualização: botão "Atualizar", a cada minuto e ao voltar para a aba.
  const [atualizacao, setAtualizacao] = useState(0);
  const [atualizadoEm, setAtualizadoEm] = useState<Date | null>(null);
  const [, setUserCnpj] = useUserCnpj();
  const [showResetModal, setShowResetModal] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [resetError, setResetError] = useState<string | null>(null);
  const [confirmText, setConfirmText] = useState("");

  const now = new Date();
  const year = now.getFullYear();
  const [month, setMonth] = useState(now.getMonth() + 1);
  const mudarMes = (delta: number) => setMonth((m) => Math.min(12, Math.max(1, m + delta)));

  useEffect(() => {
    const recarregar = () => setAtualizacao((n) => n + 1);
    const intervalo = window.setInterval(recarregar, 60_000);
    const aoVoltar = () => document.visibilityState === "visible" && recarregar();
    document.addEventListener("visibilitychange", aoVoltar);
    return () => {
      window.clearInterval(intervalo);
      document.removeEventListener("visibilitychange", aoVoltar);
    };
  }, []);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [sum, txs] = await Promise.all([
          getSummary(user.email),
          getTransactions({ email: user.email, month, year }),
        ]);
        setSummary(sum);
        setTransactions(txs);
        setAtualizadoEm(new Date());
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [user.email, month, year, atualizacao]);

  useEffect(() => {
    // Só busca o ritmo quando o dashboard novo está ligado — o antigo nunca
    // usa esse dado, e as rotas nem existiam até a US-25/US-26.
    if (!precisaRitmo) return;
    let vivo = true;
    Promise.all([getRitmo(user.email, year), getSerieAcumulada(user.email, year)])
      .then(([r, serie]) => {
        if (!vivo) return;
        setRitmo(r);
        setSerieAcumulada(serie);
      })
      .catch(() => {
        if (!vivo) return;
        setRitmo(null);
        setSerieAcumulada([]);
      });
    return () => {
      vivo = false;
    };
  }, [precisaRitmo, user.email, year, atualizacao]);

  useEffect(() => {
    // "Mês a mês" e "origem do faturamento" (US-27) — mesmas rotas novas,
    // mesma régua da flag do ritmo.
    if (!dashboardV2) return;
    let vivo = true;
    Promise.all([getMensal(user.email, year), getConcentracao(user.email, year)])
      .then(([m, c]) => {
        if (!vivo) return;
        setMensal(m);
        setConcentracao(c);
      })
      .catch(() => {
        if (!vivo) return;
        setMensal([]);
        setConcentracao([]);
      });
    return () => {
      vivo = false;
    };
  }, [dashboardV2, user.email, year, atualizacao]);

  // Resumo do agente só quando pedido: chamar o Gemini a cada visita ao
  // dashboard gastava cota (e tempo) sem o usuário ter perguntado nada.
  const pedirResumo = async () => {
    setCarregandoResumo(true);
    try {
      const { reply } = await chatAgent(
        user.email,
        "Faça um resumo rápido: quanto já faturei e quanto falta para o limite MEI?"
      );
      setAgentPreview(reply);
    } catch (err) {
      setAgentPreview(`Não consegui falar com o agente agora: ${(err as Error).message}`);
    } finally {
      setCarregandoResumo(false);
    }
  };

  const monthlyRevenue = useMemo(
    () => transactions.filter((tx) => tx.tx_type !== "compra").reduce((acc, tx) => acc + (tx.amount || 0), 0),
    [transactions]
  );

  const monthlyExpenses = useMemo(
    () => transactions.filter((tx) => tx.tx_type === "compra").reduce((acc, tx) => acc + (tx.amount || 0), 0),
    [transactions]
  );

  const percent = useMemo(() => {
    if (!summary) return 0;
    const p = (summary.total_revenue / summary.annual_limit) * 100;
    return Math.min(100, Math.max(0, p));
  }, [summary]);

  const transacoesFiltradas = useMemo(
    () =>
      transactions.filter(
        (tx) => filtroTipo === "todas" || (tx.tx_type === "compra") === (filtroTipo === "compra")
      ),
    [transactions, filtroTipo]
  );
  const semDados = summary != null && summary.total_revenue === 0 && summary.total_despesas === 0;
  const metaMensal = mensal[0]?.meta ?? (summary ? summary.annual_limit / 12 : 0);

  const CONFIRM_WORD = "RESETAR";
  const exceeded = summary?.alert_level === "exceeded";

  const handleReset = async () => {
    if (confirmText.trim().toUpperCase() !== CONFIRM_WORD) return;
    setResetting(true);
    setResetError(null);
    try {
      const results = await resetAllData(user.email);
      const failed = results.filter((r) => !r.ok);
      if (failed.length > 0) {
        throw new Error(
          `Falha ao resetar: ${failed.map((f) => `${f.service} (${f.detail || "erro"})`).join(", ")}`
        );
      }
      clearDocs();
      setUserCnpj(DEMO_CNPJ_PLACEHOLDER);
      localStorage.removeItem(CHAVE_HISTORICO_CHAT);
      // Recarrega a página inteira para garantir que todo estado (dashboard,
      // saldo de tokens, documentos) reflita o reset de forma consistente.
      window.location.reload();
    } catch (err) {
      setResetError((err as Error).message);
      setResetting(false);
    }
  };

  const atualizadoTexto = atualizadoEm
    ? atualizadoEm.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })
    : null;

  return (
    <div>
      {visualNovo ? (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-1 text-sm text-tinta-suave">
            <span aria-live="polite">
              {loading && !summary ? "Carregando seus números…" : atualizadoTexto ? `Atualizado às ${atualizadoTexto}` : ""}
            </span>
            <Botao
              variante="discreto"
              tamanho="sm"
              carregando={loading && !!summary}
              onClick={() => setAtualizacao((n) => n + 1)}
            >
              {loading && summary ? "Atualizando" : "Atualizar"}
            </Botao>
          </div>
          <div className="flex flex-wrap items-center gap-2.5">
            <a href={getReportUrl(user.email, year)} target="_blank" rel="noreferrer" className={clsSecundario}>
              Baixar relatório (PDF)
            </a>
            <Link to="/upload" className={clsPrimario}>
              Enviar nota
            </Link>
          </div>
        </div>
      ) : (
      <div className="page-header">
        <div>
          <div className="pill">
            <span className="h-2 w-2 animate-pulse rounded-full bg-limite-ok" aria-hidden="true" />
            Dashboard em tempo real
          </div>
          <h2 className="title mt-1.5">Bem-vindo, {user.name}</h2>
          <div className="muted flex flex-wrap items-center gap-x-2">
            <span>Limite do MEI, ritmo de vendas e movimentação de {year}.</span>
            {atualizadoEm && (
              <span className="text-xs">
                · Atualizado às {atualizadoEm.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}
              </span>
            )}
            <button
              type="button"
              onClick={() => setAtualizacao((n) => n + 1)}
              className="text-xs font-semibold text-acento-claro hover:underline"
            >
              ↻ Atualizar
            </button>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <a href={getReportUrl(user.email, year)} target="_blank" rel="noreferrer" className={BOTAO_SECUNDARIO}>
            ⬇ Relatório PDF
          </a>
          <Link to="/upload" className="cta">
            + Enviar nota
          </Link>
        </div>
      </div>
      )}

      {error && <div className="card mt-3.5 text-limite-estourado">{error}</div>}

      {!visualNovo && summary && summary.alert_level !== "ok" && (
        <div
          className={`card mt-4 ${
            exceeded
              ? "border-limite-estourado-borda bg-limite-estourado-suave"
              : "border-limite-atencao-borda bg-limite-atencao-suave"
          }`}
        >
          <div className={`font-bold ${exceeded ? "text-limite-estourado" : "text-limite-atencao"}`}>
            {exceeded
              ? "Você ultrapassou o limite anual do MEI"
              : `Atenção: você já usou ${summary.percent_used.toFixed(1)}% do limite anual do MEI`}
          </div>
          <div className="muted mt-1">
            {exceeded
              ? `Faturamento acima de ${formatBRL(summary.annual_limit)} no ano pode exigir o desenquadramento do MEI. Consulte o agente ou um contador.`
              : "Fique de olho nos próximos lançamentos para não estourar o teto anual."}
          </div>
        </div>
      )}

      {semDados && (
        <div className="card mt-4 flex flex-wrap items-center justify-between gap-3 border-acento/25 bg-acento/[0.06]">
          <div>
            <div className="font-semibold text-tinta-forte">Nenhum lançamento em {year} ainda</div>
            <div className="muted text-[13px]">
              Envie uma nota e confirme os dados: os indicadores e gráficos abaixo se atualizam na hora.
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {PASSOS_INICIO.map((passo, indice) => (
              <Link
                key={passo.titulo}
                to={passo.para}
                className="pill transition-colors hover:border-acento/50 hover:bg-acento/10"
              >
                {!visualNovo && passo.icone} {indice + 1}. {passo.titulo}
              </Link>
            ))}
          </div>
        </div>
      )}

      {visualNovo && (
        <div className="mt-10">
          {summary ? (
            <ReguaLimite summary={summary} ritmo={ritmo} />
          ) : loading ? (
            <div aria-hidden="true">
              <div className="esqueleto h-10 max-w-[60ch]" />
              <div className="esqueleto mt-3 h-6 max-w-[40ch]" />
              <div className="esqueleto mt-8 h-14" />
            </div>
          ) : null}
          {summary && (
            <dl className="mt-10 grid gap-x-10 gap-y-4 border-t border-borda pt-6 sm:grid-cols-3">
              <div>
                <dt className="text-sm text-tinta-suave">Despesas no ano</dt>
                <dd className="valor m-0 mt-1 text-2xl">{formatBRL(summary.total_despesas)}</dd>
                <dd className="m-0 mt-0.5 text-[13px] text-tinta-suave">Não contam para o limite</dd>
              </div>
              <div>
                <dt className="text-sm text-tinta-suave">Saldo (vendas menos despesas)</dt>
                <dd className={`valor m-0 mt-1 text-2xl ${summary.saldo_liquido < 0 ? "!text-limite-estourado" : ""}`}>
                  {formatBRL(summary.saldo_liquido)}
                </dd>
              </div>
              <div>
                <dt className="text-sm text-tinta-suave">Ainda cabe no limite</dt>
                <dd className="valor m-0 mt-1 text-2xl">{formatBRL(Math.max(0, summary.remaining))}</dd>
              </div>
            </dl>
          )}
        </div>
      )}

      {!visualNovo && (
      <>
      <div className="card-grid">
        <StatCard
          title="Faturamento anual (vendas)"
          value={summary ? formatBRL(summary.total_revenue) : "—"}
          helper={summary ? `Limite ${formatBRL(summary.annual_limit)}` : "Carregando..."}
        >
          <BarraProgresso percentual={percent} rotulo="Uso do limite anual" fina />
        </StatCard>
        <StatCard
          title="Despesas anuais (compras)"
          value={summary ? formatBRL(summary.total_despesas) : "—"}
          helper="Não conta para o limite do MEI"
        />
        <StatCard
          title="Saldo líquido"
          value={summary ? formatBRL(summary.saldo_liquido) : "—"}
          helper="Vendas menos compras"
          accent={summary && summary.saldo_liquido < 0 ? "text-limite-estourado" : "text-limite-ok"}
        />
        <StatCard
          title="% do limite MEI"
          value={`${percent.toFixed(1)}%`}
          helper={summary ? (summary.exceeded ? "Limite ultrapassado" : "Dentro do limite") : ""}
          accent={summary?.exceeded ? "text-limite-estourado" : "text-acento-claro"}
        />
      </div>

      {summary && (
        <div className="card mt-4">
          <div className="flex flex-wrap items-end justify-between gap-2">
            <div>
              <div className="muted">Progresso no ano</div>
              <div className="mt-1 text-lg font-bold text-tinta-forte">
                {summary.exceeded
                  ? `Passou ${formatBRL(summary.total_revenue - summary.annual_limit)} do teto`
                  : `Restam ${formatBRL(summary.remaining)}`}
              </div>
            </div>
            <div className="text-right text-sm text-tinta-suave">
              <span className="font-display text-2xl font-bold text-tinta-forte">{percent.toFixed(1)}%</span> de{" "}
              {formatBRL(summary.annual_limit)}
            </div>
          </div>
          <div className="mt-3">
            <BarraProgresso
              percentual={summary.percent_used}
              rotulo="Progresso do faturamento no ano"
              marcos={[
                {
                  em: summary.alert_threshold_percent ?? 80,
                  rotulo: `${formatPercentual(summary.alert_threshold_percent ?? 80, 0)} · atenção`,
                },
                { em: 100, rotulo: "teto" },
              ]}
            />
          </div>
        </div>
      )}

      <div className="card-grid">
        <StatCard
          title="Vendas do mês"
          value={formatBRL(monthlyRevenue)}
          helper={`${NOMES_MES[month - 1]} · meta de ${formatBRL(metaMensal)}`}
        >
          <BarraProgresso
            percentual={metaMensal > 0 ? (monthlyRevenue / metaMensal) * 100 : 0}
            rotulo="Vendas do mês contra a meta mensal"
            fina
          />
        </StatCard>
        <StatCard
          title="Compras do mês"
          value={formatBRL(monthlyExpenses)}
          helper={`${NOMES_MES[month - 1]} · ${transactions.filter((tx) => tx.tx_type === "compra").length} lançamento(s)`}
          accent="text-tinta-suave"
        />
      </div>
      </>
      )}

      {dashboardV2 && ritmo ? (
        <>
          {visualNovo ? (
            <div className="mt-10">
              <PainelRitmo ritmo={ritmo} />
            </div>
          ) : (
          <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(260px,1fr)_2fr]">
            <Gauge
              percentual={ritmo.percent_used}
              acumulado={ritmo.total_vendas}
              restante={ritmo.restante}
              nivel={ritmo.nivel}
            />
            <PainelRitmo ritmo={ritmo} />
          </div>
          )}
          <div className="section">
            <CorridaContraLimite ritmo={ritmo} serie={serieAcumulada} />
          </div>
          <div className="mt-4 grid gap-4 xl:grid-cols-[3fr_2fr]">
            <MesAMes mensal={mensal} />
            <OrigemFaturamento concentracao={concentracao} />
          </div>
        </>
      ) : null}

      <div className="card-grid">
        <SectionCard
          title="Documentos"
          description="Envie notas fiscais e deixe a IA extrair valor, data e CNPJ."
          action={
            <Link to="/upload" className={visualNovo ? classesBotao("secundario", "sm") : "cta"}>
              {visualNovo ? "Enviar nota" : "Upload"}
            </Link>
          }
        >
          <div className="muted">
            {docs.length === 0
              ? "Nenhum documento enviado neste navegador ainda."
              : `${docs.length} documento(s) enviados · `}
            {docs.length > 0 && (
              <Link to="/documents" className="font-semibold text-acento-claro hover:underline">
                ver lista
              </Link>
            )}
          </div>
          <div className="muted mt-1 text-[13px]">
            Ao confirmar, o lançamento vai para o Limits e o limite é recalculado em tempo real.
          </div>
        </SectionCard>

        <SectionCard
          title="Agente Contábil (IA)"
          description="Conversa alimentada pelo resumo do MEI e pelos documentos enviados."
          action={
            <Link to="/chat" className={visualNovo ? classesBotao("secundario", "sm") : "cta"}>
              {visualNovo ? "Abrir conversa" : "Abrir chat"}
            </Link>
          }
        >
          {agentPreview ? (
            <div className="chat-bubble max-w-none">
              <Markdown texto={agentPreview} />
            </div>
          ) : visualNovo ? (
            <Botao variante="secundario" className="w-full" onClick={pedirResumo} carregando={carregandoResumo}>
              {carregandoResumo ? "Resumindo seu ano…" : "Resumir meu ano"}
            </Botao>
          ) : (
            <button type="button" className={`${BOTAO_SECUNDARIO} w-full justify-center`} onClick={pedirResumo} disabled={carregandoResumo}>
              {carregandoResumo ? "Consultando o agente..." : "✨ Gerar resumo com IA"}
            </button>
          )}
        </SectionCard>

        <SectionCard
          title="Tokens"
          description="Consumo de IA por ação (upload confirmado e mensagem ao agente)."
          action={<div className="badge">{ilimitado ? "Demo · ilimitado" : `${balance ?? "—"} restantes`}</div>}
        >
          <div className="muted text-[13px]">
            {Object.entries(costs)
              .map(([acao, custo]) => `${acao === "document_confirm" ? "Confirmar nota" : "Mensagem ao agente"}: ${custo}`)
              .join(" · ")}
          </div>
        </SectionCard>
      </div>

      <div className="section">
        <SectionCard
          title="Movimentação do mês"
          description={`${formatBRL(monthlyRevenue)} em vendas · ${formatBRL(monthlyExpenses)} em compras`}
          action={
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                aria-label="Mês anterior"
                className="pill cursor-pointer px-2.5 disabled:opacity-40"
                onClick={() => mudarMes(-1)}
                disabled={month === 1}
              >
                ‹
              </button>
              <span className="min-w-[96px] text-center text-sm font-semibold capitalize">
                {NOMES_MES[month - 1]}
              </span>
              <button
                type="button"
                aria-label="Próximo mês"
                className="pill cursor-pointer px-2.5 disabled:opacity-40"
                onClick={() => mudarMes(1)}
                disabled={month === 12}
              >
                ›
              </button>
            </div>
          }
        >
          <div className="mb-1 flex gap-1.5" role="group" aria-label="Filtrar por tipo">
            {(["todas", "venda", "compra"] as FiltroTipo[]).map((tipo) => (
              <button
                key={tipo}
                type="button"
                aria-pressed={filtroTipo === tipo}
                onClick={() => setFiltroTipo(tipo)}
                className={`pill cursor-pointer py-1 text-xs ${
                  filtroTipo === tipo ? "border-acento/50 bg-acento/15 text-tinta-forte" : ""
                }`}
              >
                {tipo === "todas" ? "Todas" : tipo === "venda" ? "Vendas" : "Compras"}
              </button>
            ))}
          </div>
          {loading && transactions.length === 0 ? (
            <div className="mt-3 space-y-2">
              {[0, 1, 2].map((n) => (
                <div key={n} className="esqueleto h-9" />
              ))}
            </div>
          ) : transacoesFiltradas.length === 0 ? (
            <div className="muted py-6 text-center">Nenhum lançamento em {NOMES_MES[month - 1]}.</div>
          ) : (
            <div className="tabela-rolavel">
              <table className="table">
                <thead>
                  <tr>
                    <th>Data</th>
                    <th>Tipo</th>
                    <th className="!text-right">Valor</th>
                    <th>Origem</th>
                  </tr>
                </thead>
                <tbody>
                  {transacoesFiltradas.map((tx) => (
                    <tr key={tx.id}>
                      <td>{formatIsoDateBr(tx.tx_date)}</td>
                      <td>
                        <span
                          className={`badge ${
                            tx.tx_type === "compra"
                              ? "bg-limite-atencao/15 text-limite-atencao"
                              : "bg-limite-ok/15 text-limite-ok"
                          }`}
                        >
                          {tx.tx_type === "compra" ? "Compra" : "Venda"}
                        </span>
                      </td>
                      <td className="text-right font-semibold tabular-nums">{formatBRL(tx.amount)}</td>
                      <td className="text-tinta-suave">{tx.source || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </SectionCard>
      </div>

      <div className="mt-8 flex items-center justify-between border-t border-borda-sutil pt-4 text-xs text-tinta-suave">
        <span>Ambiente de demonstração · dados de {user.email}</span>
        <button
          type="button"
          onClick={() => {
            setConfirmText("");
            setResetError(null);
            setShowResetModal(true);
          }}
          className={
            visualNovo
              ? classesBotao("perigo", "sm")
              : "cursor-pointer rounded-lg border border-limite-estourado-borda bg-transparent px-3 py-1.5 font-semibold text-limite-estourado transition-colors hover:bg-limite-estourado-suave"
          }
        >
          Resetar dados de teste
        </button>
      </div>

      {showResetModal && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/60"
          onKeyDown={(e) => {
            if (visualNovo && e.key === "Escape" && !resetting) setShowResetModal(false);
          }}
        >
          <div
            className={`card w-[90%] max-w-[480px] border-limite-estourado-borda ${visualNovo ? "bg-fundo-elevado" : ""}`}
            role="dialog"
            aria-modal="true"
            aria-labelledby="titulo-reset"
          >
            <div className="pill border-limite-estourado-forte/35 bg-limite-estourado/15 text-limite-estourado">
              Ação irreversível
            </div>
            <h3 id="titulo-reset" className="title my-2.5 text-xl">Resetar todos os dados de teste?</h3>
            <div className="muted">
              Isso vai apagar <strong>permanentemente</strong>, para {user.email}:
            </div>
            <ul className="my-2 pl-5 text-sm text-tinta-leve">
              <li>Todas as vendas e compras registradas no Limits</li>
              <li>O saldo de tokens (volta para o valor inicial)</li>
              <li>Os documentos indexados no agente (RAG por usuário)</li>
              <li>Os arquivos enviados no Documents Service</li>
              <li>A lista de documentos, o histórico do chat e o CNPJ salvos neste navegador</li>
            </ul>
            <div className="muted mb-1">
              Digite <strong>{CONFIRM_WORD}</strong> para confirmar:
            </div>
            <input
              type="text"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder={CONFIRM_WORD}
              disabled={resetting}
              aria-label={`Digite ${CONFIRM_WORD} para confirmar`}
              autoFocus={visualNovo}
            />
            {resetError && <div className="mt-2.5 text-limite-estourado">{resetError}</div>}
            {visualNovo ? (
              <div className="mt-4 flex flex-wrap gap-2.5">
                <Botao
                  variante="perigo"
                  onClick={handleReset}
                  carregando={resetting}
                  disabled={confirmText.trim().toUpperCase() !== CONFIRM_WORD}
                >
                  {resetting ? "Apagando os dados" : "Apagar tudo"}
                </Botao>
                <Botao variante="secundario" onClick={() => setShowResetModal(false)} disabled={resetting}>
                  Cancelar
                </Botao>
              </div>
            ) : (
            <div className="mt-4 flex gap-2.5">
              <button
                type="button"
                onClick={handleReset}
                disabled={resetting || confirmText.trim().toUpperCase() !== CONFIRM_WORD}
                className={`cursor-pointer rounded-campo border-none bg-perigo px-4 py-3 font-bold text-tinta-forte ${
                  confirmText.trim().toUpperCase() !== CONFIRM_WORD ? "opacity-50" : "opacity-100"
                }`}
              >
                {resetting ? "Resetando..." : "Sim, resetar tudo"}
              </button>
              <button
                type="button"
                onClick={() => setShowResetModal(false)}
                disabled={resetting}
                className="cursor-pointer rounded-campo border border-borda-forte bg-transparent px-4 py-3 text-tinta"
              >
                Cancelar
              </button>
            </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
