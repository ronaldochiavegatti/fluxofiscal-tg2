import { useState } from "react";
import { Cell, Pie, PieChart, Sector } from "recharts";
import { formatPercentual } from "../format";
import type { ConcentracaoCliente } from "../types";

type Props = {
  concentracao: ConcentracaoCliente[];
};

const CORES = [1, 2, 3, 4, 5].map((n) => `var(--cor-serie-${n})`);
const corDe = (indice: number, alerta: boolean) =>
  alerta ? "var(--cor-estourado)" : CORES[indice % CORES.length];

/**
 * "Origem do faturamento" do dashboard (US-27, `docs/dashboard-v2.md`
 * §2.5/§3.1): concentração de venda por CNPJ do cliente, com aviso acima de
 * 70%. `nome` ainda não existe em nenhum serviço (ADR-0021) — usamos o CNPJ
 * formatado como rótulo até haver essa fonte.
 *
 * Donut e lista ficam sincronizados: passar o mouse (ou o foco do teclado)
 * em um destaca o mesmo cliente no outro.
 */
export function OrigemFaturamento({ concentracao }: Props) {
  const [ativo, setAtivo] = useState<number | null>(null);

  if (concentracao.length === 0) {
    return (
      <div className="card">
        <div className="font-bold">Origem do faturamento</div>
        <div className="muted mt-2">
          Nenhuma venda com cliente identificado ainda. Confirme documentos com o CNPJ do
          destinatário para ver a concentração aqui.
        </div>
      </div>
    );
  }

  const alerta = concentracao.find((item) => item.alerta);
  const emFoco = ativo != null ? concentracao[ativo] : null;

  return (
    <div className="card">
      <div className="font-bold">Origem do faturamento</div>
      <div className="muted mb-3">Concentração por CNPJ do cliente, extraída dos documentos</div>

      <div className="flex flex-wrap items-center gap-5">
        <div className="relative mx-auto h-[170px] w-[170px] shrink-0">
          <PieChart width={170} height={170}>
            <Pie
              data={concentracao}
              dataKey="percentual"
              nameKey="cnpj"
              innerRadius={52}
              outerRadius={74}
              paddingAngle={2}
              stroke="none"
              activeIndex={ativo ?? undefined}
              activeShape={(props: object) => (
                <Sector {...props} outerRadius={(props as { outerRadius: number }).outerRadius + 6} />
              )}
              onMouseEnter={(_, indice) => setAtivo(indice)}
              onMouseLeave={() => setAtivo(null)}
              isAnimationActive={false}
            >
              {concentracao.map((item, indice) => (
                <Cell
                  key={item.cnpj}
                  fill={corDe(indice, item.alerta)}
                  fillOpacity={ativo == null || ativo === indice ? 1 : 0.35}
                  className="cursor-pointer"
                />
              ))}
            </Pie>
          </PieChart>
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
            {emFoco ? (
              <>
                <div className="font-display text-xl font-bold text-tinta-forte">
                  {formatPercentual(emFoco.percentual)}
                </div>
                <div className="max-w-[90px] truncate text-[11px] text-tinta-suave">
                  {emFoco.nome ?? emFoco.cnpj}
                </div>
              </>
            ) : (
              <>
                <div className="font-display text-xl font-bold text-tinta-forte">{concentracao.length}</div>
                <div className="text-[11px] text-tinta-suave">
                  {concentracao.length === 1 ? "cliente" : "clientes"}
                </div>
              </>
            )}
          </div>
        </div>

        <ul aria-label="Concentração de faturamento por cliente" className="flex min-w-[200px] flex-1 flex-col gap-1">
          {concentracao.map((item, indice) => (
            <li
              key={item.cnpj}
              tabIndex={0}
              onMouseEnter={() => setAtivo(indice)}
              onMouseLeave={() => setAtivo(null)}
              onFocus={() => setAtivo(indice)}
              onBlur={() => setAtivo(null)}
              className={`cursor-default rounded-lg px-2 py-1.5 outline-none transition-colors ${
                ativo === indice ? "bg-veu/[0.06]" : ""
              }`}
            >
              <div className="flex items-center justify-between gap-3 text-sm">
                <span className="flex min-w-0 items-center gap-2">
                  <span
                    aria-hidden="true"
                    className="h-2.5 w-2.5 shrink-0 rounded-full"
                    style={{ background: corDe(indice, item.alerta) }}
                  />
                  <span className="truncate">{item.nome ?? item.cnpj}</span>
                </span>
                <span className={`font-semibold tabular-nums ${item.alerta ? "text-limite-estourado" : ""}`}>
                  {formatPercentual(item.percentual)}
                </span>
              </div>
            </li>
          ))}
        </ul>
      </div>

      {alerta && (
        <div className="mt-3 flex items-center gap-2 rounded-xl border border-limite-estourado-borda bg-limite-estourado-suave p-2.5 text-sm font-semibold text-limite-estourado">
          <span aria-hidden="true">⚠️</span>
          <span>
            {formatPercentual(alerta.percentual)} do faturamento vem de um só cliente (
            {alerta.nome ?? alerta.cnpj}) — risco de dependência.
          </span>
        </div>
      )}
    </div>
  );
}
