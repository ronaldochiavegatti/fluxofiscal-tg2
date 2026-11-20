import { useCallback, useState, type ReactNode } from "react";
import { formatBRL } from "../format";

/**
 * Peças de interação compartilhadas pelos gráficos do dashboard.
 *
 * A legenda é feita de botões (`aria-pressed`) em vez da legenda SVG do
 * Recharts: dá para ligar/desligar séries com mouse ou teclado, e o estado
 * fica anunciado para leitor de tela.
 */

export type Serie = { chave: string; nome: string; cor: string; tracejada?: boolean };

export function useSeriesOcultas() {
  const [ocultas, setOcultas] = useState<Set<string>>(new Set());
  const alternar = useCallback((chave: string) => {
    setOcultas((atual) => {
      const nova = new Set(atual);
      if (nova.has(chave)) nova.delete(chave);
      else nova.add(chave);
      return nova;
    });
  }, []);
  return [ocultas, alternar] as const;
}

export function LegendaInterativa({
  series,
  ocultas,
  onAlternar,
}: {
  series: Serie[];
  ocultas: Set<string>;
  onAlternar: (chave: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5" role="group" aria-label="Séries do gráfico">
      {series.map((serie) => {
        const visivel = !ocultas.has(serie.chave);
        return (
          <button
            key={serie.chave}
            type="button"
            aria-pressed={visivel}
            title={visivel ? `Ocultar ${serie.nome}` : `Mostrar ${serie.nome}`}
            onClick={() => onAlternar(serie.chave)}
            className={`pill cursor-pointer py-1 text-xs transition ${
              visivel ? "hover:border-borda-forte" : "opacity-45 line-through"
            }`}
          >
            <span
              aria-hidden="true"
              className="inline-block h-2.5 w-2.5 rounded-sm"
              style={{
                background: serie.tracejada ? "transparent" : serie.cor,
                border: serie.tracejada ? `2px dashed ${serie.cor}` : "none",
              }}
            />
            {serie.nome}
          </button>
        );
      })}
    </div>
  );
}

type ItemTooltip = { dataKey?: string | number; name?: string; value?: number | number[]; color?: string };

/** Conteúdo de tooltip no tema do app; valores em reais, faixas como "a – b". */
export function TooltipCartao({
  active,
  payload,
  label,
  titulo,
  rodape,
}: {
  active?: boolean;
  payload?: ItemTooltip[];
  label?: string | number;
  titulo?: (label: string | number | undefined) => ReactNode;
  rodape?: (payload: ItemTooltip[]) => ReactNode;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const itens = payload.filter((item) => item.value != null);
  return (
    <div className="min-w-[180px] rounded-xl border border-borda-forte bg-fundo-elevado/95 px-3 py-2.5 text-[13px] shadow-card backdrop-blur">
      <div className="mb-1.5 font-semibold text-tinta-forte">{titulo ? titulo(label) : label}</div>
      {itens.map((item) => (
        <div key={String(item.dataKey)} className="flex items-center justify-between gap-4 py-0.5">
          <span className="flex items-center gap-1.5 text-tinta-leve">
            <span className="h-2 w-2 rounded-full" style={{ background: item.color }} aria-hidden="true" />
            {item.name}
          </span>
          <span className="font-semibold tabular-nums text-tinta-forte">
            {Array.isArray(item.value)
              ? `${formatBRL(item.value[0])} – ${formatBRL(item.value[1])}`
              : formatBRL(item.value as number)}
          </span>
        </div>
      ))}
      {rodape?.(itens)}
    </div>
  );
}
