import { formatBRL, formatIsoDateBr, formatNumeroBr } from "../format";
import type { Ritmo, Tendencia } from "../types";
import { useAparencia } from "../aparencia/AparenciaContext";

const TENDENCIA_INFO: Record<Tendencia, { seta: string; rotulo: string; cor: string }> = {
  acelerando: { seta: "▲", rotulo: "acelerando", cor: "text-limite-atencao" },
  estavel: { seta: "▬", rotulo: "estável", cor: "text-tinta-suave" },
  desacelerando: { seta: "▼", rotulo: "desacelerando", cor: "text-limite-ok" },
};

type Props = {
  ritmo: Ritmo;
};

/** Painel de ritmo (US-25): índice de ritmo com seta de tendência, taxas e
 * projeção. `docs/dashboard-v2.md` §2.2 é a fonte dos números. */
export function PainelRitmo({ ritmo }: Props) {
  const tendencia = TENDENCIA_INFO[ritmo.tendencia];
  const folga =
    ritmo.dias_ate_estouro != null && ritmo.data_prevista_estouro != null
      ? `${ritmo.dias_ate_estouro} (até ${formatIsoDateBr(ritmo.data_prevista_estouro)})`
      : null;

  return (
    <div className="card">
      <div className="mb-3 font-bold">Ritmo de vendas</div>

      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
        <Indicador
          rotulo="Índice de ritmo"
          explicacao="1,00 = vendendo exatamente no ritmo que leva ao teto em 31/12"
          destaque
        >
          <span className="flex items-baseline gap-2">
            {ritmo.indice_ritmo != null ? formatNumeroBr(ritmo.indice_ritmo) : "—"}
            <span className={`text-sm font-medium ${tendencia.cor}`}>
              {tendencia.seta} {tendencia.rotulo}
            </span>
          </span>
        </Indicador>
        <Indicador rotulo="Média diária" explicacao="Quanto você vendeu, em média, por dia no ano">
          {formatBRL(ritmo.taxa_diaria)}
        </Indicador>
        <Indicador rotulo="Referência do teto" explicacao="Média diária que esgota o limite em 31/12">
          {formatBRL(ritmo.taxa_diaria_referencia)}
        </Indicador>
        <Indicador rotulo={`Projeção ${ritmo.year}`} explicacao="Faturamento estimado no fim do ano, no ritmo atual">
          {ritmo.projecao_anual != null ? formatBRL(ritmo.projecao_anual) : "—"}
        </Indicador>
        {folga && (
          <Indicador rotulo="Dias de folga" explicacao="Até o limite estourar, mantido o ritmo">
            {folga}
          </Indicador>
        )}
        <Indicador rotulo="Pode faturar este mês" explicacao="Sem sair do ritmo seguro para o teto">
          {formatBRL(ritmo.faturamento_seguro_mes)}
        </Indicador>
      </div>

      {ritmo.influenciada_por_lancamento_atipico && (
        <div className="muted mt-3 text-xs">
          ⓘ Projeção influenciada por um lançamento fora do padrão do ano.
        </div>
      )}

      {!ritmo.projecao_disponivel && ritmo.motivo_indisponivel && (
        <div className="muted mt-3 text-xs">{ritmo.motivo_indisponivel}</div>
      )}
    </div>
  );
}

function Indicador({
  rotulo,
  explicacao,
  destaque,
  children,
}: {
  rotulo: string;
  explicacao: string;
  destaque?: boolean;
  children: React.ReactNode;
}) {
  const { visualNovo } = useAparencia();
  const classeDestaque = visualNovo ? "border-borda-forte bg-fundo-poco" : "border-acento/25 bg-acento/[0.07]";
  return (
    <div
      title={explicacao}
      className={`rounded-xl border p-3 transition-colors hover:border-borda-forte ${
        destaque ? classeDestaque : "border-borda-sutil bg-veu/[0.02]"
      }`}
    >
      <div className="text-[11px] font-semibold uppercase tracking-wider text-tinta-suave">{rotulo}</div>
      <div className="mt-1 font-display text-lg font-bold tabular-nums text-tinta-forte">{children}</div>
      <div className="mt-0.5 text-[11.5px] leading-snug text-tinta-suave">{explicacao}</div>
    </div>
  );
}
