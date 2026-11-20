import { PolarAngleAxis, RadialBar, RadialBarChart } from "recharts";
import { formatBRL, formatPercentual } from "../format";
import type { NivelRitmo } from "../types";

type Props = {
  /** 0–100, já limitado pelo backend (`calcular_percentual_usado`). */
  percentual: number;
  acumulado: number;
  restante: number;
  nivel: NivelRitmo;
};

/**
 * Termômetro do limite (US-25, ADR-0010). Cor nunca é o único sinal: todo
 * nível também carrega rótulo textual e ícone — o teste `Gauge.test.tsx`
 * cobre isso, e é o critério de aceite "Cor não é o único sinal".
 *
 * A cor do arco vem de uma variável CSS (`--cor-*`, definida em `index.css`
 * a partir do token do tema) — nunca hex literal aqui, é o que
 * `theme.guard.test.ts` (US-24) reprovaria.
 */
const NIVEL_INFO: Record<
  NivelRitmo,
  { rotulo: string; icone: string; corTexto: string; corArco: string }
> = {
  ok: { rotulo: "Tranquilo", icone: "✅", corTexto: "text-limite-ok", corArco: "var(--cor-ok)" },
  atencao_ritmo: {
    rotulo: "Ritmo alto",
    icone: "📈",
    corTexto: "text-limite-atencao",
    corArco: "var(--cor-atencao)",
  },
  atencao: {
    rotulo: "Atenção",
    icone: "⚠️",
    corTexto: "text-limite-atencao",
    corArco: "var(--cor-atencao)",
  },
  risco: {
    rotulo: "Risco de estourar",
    icone: "🔺",
    corTexto: "text-limite-risco",
    corArco: "var(--cor-risco)",
  },
  estourado: {
    rotulo: "Limite estourado",
    icone: "🚨",
    corTexto: "text-limite-estourado",
    corArco: "var(--cor-estourado)",
  },
  desenquadramento: {
    rotulo: "Desenquadramento",
    icone: "🚨",
    corTexto: "text-limite-estourado",
    corArco: "var(--cor-estourado-forte)",
  },
};

const TAMANHO = 220;

export function Gauge({ percentual, acumulado, restante, nivel }: Props) {
  const info = NIVEL_INFO[nivel];
  const valor = Math.min(100, Math.max(0, percentual));

  return (
    <div className="card flex flex-col items-center">
      <div className="mb-2 self-start font-bold">Limite anual</div>
      <div className="relative" style={{ width: TAMANHO, height: TAMANHO }}>
        <RadialBarChart
          width={TAMANHO}
          height={TAMANHO}
          cx="50%"
          cy="50%"
          innerRadius="72%"
          outerRadius="100%"
          barSize={16}
          data={[{ valor }]}
          startAngle={90}
          endAngle={-270}
        >
          <PolarAngleAxis type="number" domain={[0, 100]} tick={false} axisLine={false} />
          <RadialBar background={{ fill: "var(--cor-grade)" }} dataKey="valor" cornerRadius={8} fill={info.corArco} />
        </RadialBarChart>
        <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
          <div className="text-3xl font-bold">{formatPercentual(percentual)}</div>
          <div className="mt-1 text-sm text-tinta-suave">{formatBRL(acumulado)}</div>
          <div className="mt-0.5 text-xs text-tinta-suave">restam {formatBRL(restante)}</div>
        </div>
      </div>
      <div className={`mt-3 flex items-center gap-1.5 font-semibold ${info.corTexto}`}>
        <span aria-hidden="true">{info.icone}</span>
        <span>{info.rotulo}</span>
      </div>
    </div>
  );
}
