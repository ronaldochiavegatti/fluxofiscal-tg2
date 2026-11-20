import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, Tooltip, XAxis, YAxis } from "recharts";
import { formatBRL } from "../format";
import { useLargura } from "../hooks/useLargura";
import { LegendaInterativa, TooltipCartao, useSeriesOcultas, type Serie } from "./graficos";
import type { MesResumo } from "../types";

type Props = {
  mensal: MesResumo[];
};

const NOMES_MES = [
  "jan",
  "fev",
  "mar",
  "abr",
  "mai",
  "jun",
  "jul",
  "ago",
  "set",
  "out",
  "nov",
  "dez",
];

/**
 * "Mês a mês" do dashboard (US-27, `docs/dashboard-v2.md` §3.1): vendas e
 * despesas por mês, com a linha de meta mensal sobreposta. Mês acima da meta
 * ganha destaque — mas nunca só na cor da barra, também na tabela
 * equivalente abaixo (acessibilidade, `docs/dashboard-v2.md` §6).
 */
const SERIES: Serie[] = [
  { chave: "vendas", nome: "Vendas", cor: "var(--cor-vendas)" },
  { chave: "despesas", nome: "Despesas", cor: "var(--cor-despesas)" },
  { chave: "meta", nome: "Meta mensal", cor: "var(--cor-meta)", tracejada: true },
];

export function MesAMes({ mensal }: Props) {
  const meta = mensal[0]?.meta ?? 0;
  const pontos = mensal.map((ponto) => ({ ...ponto, rotulo: NOMES_MES[ponto.mes - 1] }));
  const [ref, largura] = useLargura<HTMLDivElement>(640);
  const [ocultas, alternar] = useSeriesOcultas();
  const [mesSelecionado, setMesSelecionado] = useState<number | null>(null);
  const selecionado = pontos.find((ponto) => ponto.mes === mesSelecionado);

  const selecionar = (dados: { mes?: number } | undefined) => {
    if (dados?.mes == null) return;
    setMesSelecionado((atual) => (atual === dados.mes ? null : (dados.mes as number)));
  };
  const opacidade = (mes: number) => (mesSelecionado == null || mesSelecionado === mes ? 1 : 0.35);

  return (
    <div className="card">
      <div className="page-header mb-3 items-start">
        <div>
          <div className="font-bold">Mês a mês</div>
          <div className="muted">
            Vendas e despesas, com a meta mensal de {formatBRL(meta)}
          </div>
        </div>
        <LegendaInterativa series={SERIES} ocultas={ocultas} onAlternar={alternar} />
      </div>

      {/* Largura medida pelo `useLargura` em vez do `ResponsiveContainer`, que
          depende de `ResizeObserver` sem fallback (jsdom não tem). */}
      <div ref={ref} style={{ overflowX: "auto" }}>
        <BarChart width={largura} height={240} data={pontos} barGap={4}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--cor-grade)" vertical={false} />
          <XAxis dataKey="rotulo" stroke="var(--cor-meta)" tickLine={false} axisLine={false} />
          <YAxis
            stroke="var(--cor-meta)"
            width={56}
            tickLine={false}
            axisLine={false}
            tickFormatter={(valor: number) => `${Math.round(valor / 1000)}k`}
          />
          <Tooltip
            cursor={{ fill: "var(--cor-grade)" }}
            content={
              <TooltipCartao
                rodape={() => <div className="mt-1.5 text-[11px] text-tinta-suave">Clique para fixar o mês</div>}
              />
            }
          />
          {!ocultas.has("meta") && (
            <ReferenceLine
              y={meta}
              stroke="var(--cor-meta)"
              strokeDasharray="4 4"
              label={{ value: "meta", fill: "var(--cor-meta)", position: "insideTopRight" }}
            />
          )}
          <Bar
            dataKey="vendas"
            name="Vendas"
            radius={[6, 6, 0, 0]}
            hide={ocultas.has("vendas")}
            onClick={selecionar}
            className="cursor-pointer"
          >
            {pontos.map((ponto) => (
              <Cell
                key={ponto.mes}
                fill={ponto.acima_da_meta ? "var(--cor-vendas-destaque)" : "var(--cor-vendas)"}
                fillOpacity={opacidade(ponto.mes)}
              />
            ))}
          </Bar>
          <Bar
            dataKey="despesas"
            name="Despesas"
            fill="var(--cor-despesas)"
            radius={[6, 6, 0, 0]}
            hide={ocultas.has("despesas")}
            onClick={selecionar}
            className="cursor-pointer"
          >
            {pontos.map((ponto) => (
              <Cell key={ponto.mes} fillOpacity={opacidade(ponto.mes)} />
            ))}
          </Bar>
        </BarChart>
      </div>

      {selecionado && (
        <div className="mt-2 grid grid-cols-2 gap-2 rounded-xl border border-acento/25 bg-acento/[0.07] p-3 text-sm sm:grid-cols-4">
          <div className="col-span-2 flex items-center justify-between sm:col-span-4">
            <span className="font-semibold capitalize text-tinta-forte">{selecionado.rotulo}</span>
            <button type="button" className="text-xs text-tinta-suave hover:text-tinta" onClick={() => setMesSelecionado(null)}>
              Limpar seleção ✕
            </button>
          </div>
          <Detalhe rotulo="Vendas" valor={formatBRL(selecionado.vendas)} />
          <Detalhe rotulo="Despesas" valor={formatBRL(selecionado.despesas)} />
          <Detalhe rotulo="Saldo" valor={formatBRL(selecionado.vendas - selecionado.despesas)} />
          <Detalhe
            rotulo="Contra a meta"
            valor={`${selecionado.vendas >= selecionado.meta ? "+" : "−"}${formatBRL(Math.abs(selecionado.vendas - selecionado.meta))}`}
            destaque={selecionado.acima_da_meta ? "text-limite-ok" : "text-tinta-leve"}
          />
        </div>
      )}

      <details className="mt-2">
        <summary className="cursor-pointer text-sm text-tinta-suave">
          Ver como tabela
        </summary>
        <div className="tabela-rolavel">
          <table className="table" aria-label="Vendas e despesas por mês, com a meta mensal">
            <thead>
              <tr>
                <th>Mês</th>
                <th>Vendas</th>
                <th>Despesas</th>
                <th>Meta</th>
                <th>Acima da meta</th>
              </tr>
            </thead>
            <tbody>
              {pontos.map((ponto) => (
                <tr key={ponto.mes}>
                  <td>{ponto.rotulo}</td>
                  <td>{formatBRL(ponto.vendas)}</td>
                  <td>{formatBRL(ponto.despesas)}</td>
                  <td>{formatBRL(ponto.meta)}</td>
                  <td>{ponto.acima_da_meta ? "Sim" : "Não"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

function Detalhe({ rotulo, valor, destaque }: { rotulo: string; valor: string; destaque?: string }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-tinta-suave">{rotulo}</div>
      <div className={`font-semibold tabular-nums ${destaque ?? "text-tinta-forte"}`}>{valor}</div>
    </div>
  );
}
