import {
  Area,
  Brush,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceDot,
  ReferenceLine,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatBRL, formatIsoDateBr } from "../format";
import type { PontoSerieAcumulada, Ritmo } from "../types";
import { useLargura } from "../hooks/useLargura";
import { LegendaInterativa, TooltipCartao, useSeriesOcultas, type Serie } from "./graficos";

type Props = {
  ritmo: Ritmo;
  serie: PontoSerieAcumulada[];
};

type PontoGrafico = {
  dia: number;
  data: string;
  realizado?: number;
  referencia: number;
  provavel?: number;
  faixa?: [number, number];
};

// Aritmética de data em UTC, por inteiro — evitar `new Date(iso)` direto, que
// assume fuso e pode cair no dia anterior num fuso negativo como o do Brasil
// (mesma cautela de `formatIsoDateBr` em format.ts).
const UM_DIA_MS = 86_400_000;

function diaDoAno(iso: string): number {
  const [ano, mes, dia] = iso.split("-").map(Number);
  const inicio = Date.UTC(ano, 0, 1);
  const atual = Date.UTC(ano, mes - 1, dia);
  return Math.round((atual - inicio) / UM_DIA_MS) + 1;
}

function dataDoDiaDoAno(ano: number, dia: number): string {
  const d = new Date(Date.UTC(ano, 0, 1) + (dia - 1) * UM_DIA_MS);
  const mes = String(d.getUTCMonth() + 1).padStart(2, "0");
  const diaDoMes = String(d.getUTCDate()).padStart(2, "0");
  return `${d.getUTCFullYear()}-${mes}-${diaDoMes}`;
}

/** Monta um ponto por dia do ano: realizado (serie real) até hoje, cone de
 * projeção (faixa pessimista–otimista + linha "provável") depois. */
function montarPontos(ritmo: Ritmo, serie: PontoSerieAcumulada[]): PontoGrafico[] {
  const diaHoje = serie.length > 0 ? diaDoAno(serie[serie.length - 1].data) : 0;
  const acumuladoHoje = serie.length > 0 ? serie[serie.length - 1].acumulado : 0;
  const referenciaPorDia = ritmo.limite_aplicavel / ritmo.total_dias_ano;

  const pontos: PontoGrafico[] = [];
  for (let dia = 1; dia <= ritmo.total_dias_ano; dia++) {
    const ponto: PontoGrafico = {
      dia,
      data: dataDoDiaDoAno(ritmo.year, dia),
      referencia: Math.round(referenciaPorDia * dia * 100) / 100,
    };

    if (dia <= diaHoje) {
      ponto.realizado = serie[dia - 1]?.acumulado;
    } else if (ritmo.projecao_disponivel) {
      const diasAFrente = dia - diaHoje;
      const pessimista = acumuladoHoje + ritmo.taxa_diaria_recente * diasAFrente;
      const otimista = acumuladoHoje + ritmo.taxa_diaria_90d * diasAFrente;
      ponto.provavel = acumuladoHoje + ritmo.taxa_diaria * diasAFrente;
      ponto.faixa = [Math.min(pessimista, otimista), Math.max(pessimista, otimista)];
    }
    pontos.push(ponto);
  }
  return pontos;
}

/** Resumo mensal para a alternativa textual — a mesma trajetória, em 12
 * linhas em vez de até 365 pontos. */
function resumoMensal(pontos: PontoGrafico[]) {
  const linhas: { mes: number; acumulado: number | null; referencia: number }[] = [];
  for (let mes = 1; mes <= 12; mes++) {
    const doMes = pontos.filter((p) => Number(p.data.slice(5, 7)) === mes);
    const ultimo = doMes.at(-1);
    if (!ultimo) continue;
    const acumulado = ultimo.realizado ?? ultimo.provavel ?? null;
    linhas.push({ mes, acumulado, referencia: ultimo.referencia });
  }
  return linhas;
}

const NOMES_MES = [
  "Jan",
  "Fev",
  "Mar",
  "Abr",
  "Mai",
  "Jun",
  "Jul",
  "Ago",
  "Set",
  "Out",
  "Nov",
  "Dez",
];

export function CorridaContraLimite({ ritmo, serie }: Props) {
  const pontos = montarPontos(ritmo, serie);
  const [ref, largura] = useLargura<HTMLDivElement>(640);
  const [ocultas, alternar] = useSeriesOcultas();
  const series: Serie[] = [
    { chave: "realizado", nome: "Realizado", cor: "var(--cor-realizado)" },
    { chave: "referencia", nome: "Ritmo de referência", cor: "var(--cor-referencia)", tracejada: true },
    ...(ritmo.projecao_disponivel
      ? [
          { chave: "provavel", nome: "Projeção provável", cor: "var(--cor-atencao)", tracejada: true },
          { chave: "faixa", nome: "Cone de projeção", cor: "var(--cor-atencao)" },
        ]
      : []),
  ];
  const mensal = resumoMensal(pontos);
  // Rótulo no dia 1º de cada mês (antes, a cada 29 pontos, "Jan" saía duas
  // vezes); em gráfico estreito (celular), um a cada três meses.
  const primeirosDoMes = pontos.map((p) => p.data).filter((iso) => iso.endsWith("-01"));
  const marcasEixo = largura < 520 ? primeirosDoMes.filter((_, i) => i % 3 === 0) : primeirosDoMes;
  const estouroNoAno =
    ritmo.data_prevista_estouro != null && ritmo.data_prevista_estouro.startsWith(String(ritmo.year));

  return (
    <div className="card">
      <div className="page-header mb-3 items-start">
        <div>
          <div className="flex items-center gap-2 font-bold">
            Corrida contra o limite
            {!ritmo.projecao_disponivel && (
              <span className="badge font-normal">{ritmo.motivo_indisponivel}</span>
            )}
          </div>
          <div className="muted">
            Faturamento acumulado contra o teto de {formatBRL(ritmo.limite_aplicavel)}. Arraste a
            barra inferior para dar zoom em um período.
          </div>
        </div>
        <LegendaInterativa series={series} ocultas={ocultas} onAlternar={alternar} />
      </div>

      <div ref={ref}>
        <ComposedChart
          width={largura}
          height={320}
          data={pontos}
          margin={{ top: 10, right: 20, left: 0, bottom: 0 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="var(--cor-referencia)" opacity={0.15} />
          <XAxis
            dataKey="data"
            tickFormatter={(iso: string) => NOMES_MES[Number(iso.slice(5, 7)) - 1]}
            ticks={marcasEixo}
            interval={0}
            tick={{ fontSize: 12 }}
          />
          <YAxis
            tickFormatter={(v: number) => `${Math.round(v / 1000)}k`}
            width={40}
            tick={{ fontSize: 12 }}
          />
          <Tooltip
            content={<TooltipCartao titulo={(iso) => formatIsoDateBr(String(iso))} />}
            cursor={{ stroke: "var(--cor-referencia)", strokeDasharray: "3 3" }}
          />
          <ReferenceLine
            y={ritmo.limite_aplicavel}
            stroke="var(--cor-estourado)"
            strokeDasharray="4 4"
            label={{ value: "Teto", position: "insideTopRight", fill: "var(--cor-estourado)" }}
          />
          <Area
            type="monotone"
            dataKey="realizado"
            hide={ocultas.has("realizado")}
            name="Realizado"
            stroke="var(--cor-realizado)"
            fill="var(--cor-realizado)"
            fillOpacity={0.25}
            isAnimationActive={false}
            connectNulls
          />
          <Line
            type="monotone"
            dataKey="referencia"
            hide={ocultas.has("referencia")}
            name="Ritmo de referência"
            stroke="var(--cor-referencia)"
            strokeDasharray="6 4"
            dot={false}
            isAnimationActive={false}
          />
          {ritmo.projecao_disponivel && (
            <>
              <Area
                type="monotone"
                dataKey="faixa"
                hide={ocultas.has("faixa")}
                name="Cone de projeção"
                stroke="none"
                fill="var(--cor-atencao)"
                fillOpacity={0.18}
                isAnimationActive={false}
                connectNulls
              />
              <Line
                type="monotone"
                dataKey="provavel"
                hide={ocultas.has("provavel")}
                name="Projeção provável"
                stroke="var(--cor-atencao)"
                strokeDasharray="3 3"
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
            </>
          )}
          {ritmo.projecao_disponivel && estouroNoAno && (
            <ReferenceDot
              x={ritmo.data_prevista_estouro as string}
              y={ritmo.limite_aplicavel}
              r={5}
              fill="var(--cor-estourado)"
              stroke="none"
              label={{
                value: `Estouro em ${formatIsoDateBr(ritmo.data_prevista_estouro as string)}`,
                position: "top",
                fill: "var(--cor-estourado)",
                fontSize: 12,
              }}
            />
          )}
          {pontos.length > 1 && (
            <Brush
              dataKey="data"
              height={24}
              travellerWidth={8}
              stroke="var(--cor-realizado)"
              fill="var(--cor-tooltip-fundo)"
              tickFormatter={(iso: string) => formatIsoDateBr(iso)}
            />
          )}
        </ComposedChart>
      </div>

      <details className="section">
        <summary className="cursor-pointer text-sm text-tinta-suave">
          Ver como tabela (alternativa ao gráfico)
        </summary>
        <div className="tabela-rolavel">
          <table className="table">
            <thead>
              <tr>
                <th>Mês</th>
                <th>Acumulado</th>
                <th>Referência</th>
              </tr>
            </thead>
            <tbody>
              {mensal.map((linha) => (
                <tr key={linha.mes}>
                  <td>{NOMES_MES[linha.mes - 1]}</td>
                  <td>{linha.acumulado != null ? formatBRL(linha.acumulado) : "—"}</td>
                  <td>{formatBRL(linha.referencia)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
