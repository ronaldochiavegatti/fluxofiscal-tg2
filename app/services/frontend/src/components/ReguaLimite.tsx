import { formatBRLInteiro, formatIsoDateBr } from "../format";
import type { NivelRitmo, Ritmo, Summary } from "../types";

type Props = {
  summary: Summary;
  /** Opcional: com ele a régua ganha o marcador "hoje" e a frase de projeção. */
  ritmo?: Ritmo | null;
};

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

type Faixa = "ok" | "atencao" | "risco" | "estourado";

const FAIXA_DO_NIVEL: Record<NivelRitmo, Faixa> = {
  ok: "ok",
  atencao_ritmo: "atencao",
  atencao: "atencao",
  risco: "risco",
  estourado: "estourado",
  desenquadramento: "estourado",
};

const FAIXA_DO_ALERTA: Record<Summary["alert_level"], Faixa> = {
  ok: "ok",
  warning: "atencao",
  exceeded: "estourado",
};

// Classes por extenso (o Tailwind descarta nome de classe montado em runtime).
const CLASSE_FAIXA: Record<Faixa, { selo: string; preenchimento: string }> = {
  ok: { selo: "regua-selo-ok", preenchimento: "regua-ok" },
  atencao: { selo: "regua-selo-atencao", preenchimento: "regua-atencao" },
  risco: { selo: "regua-selo-risco", preenchimento: "regua-risco" },
  estourado: { selo: "regua-selo-estourado", preenchimento: "regua-estourado" },
};

// Cor nunca é o único sinal: a frase acima da régua diz o mesmo em texto.
const ROTULO_FAIXA: Record<Faixa, string> = {
  ok: "Dentro do limite",
  atencao: "Atenção ao limite",
  risco: "Risco de passar do limite",
  estourado: "Limite ultrapassado",
};

/** Segunda frase do topo do painel: o que o número significa para o resto do ano. */
function previsao(summary: Summary, ritmo?: Ritmo | null): string {
  if (summary.exceeded) {
    return `Você passou ${formatBRLInteiro(summary.total_revenue - summary.annual_limit)} do limite. Fale com um contador sobre o desenquadramento.`;
  }
  if (ritmo?.projecao_disponivel && ritmo.projecao_anual != null) {
    // Só avisa a data se ela cai dentro do próprio ano: um estouro previsto
    // para anos depois não é o recado de quem olha o limite deste ano.
    if (ritmo.data_prevista_estouro && ritmo.data_prevista_estouro.startsWith(String(ritmo.year))) {
      return `No ritmo atual, você chega ao limite em ${formatIsoDateBr(ritmo.data_prevista_estouro)}.`;
    }
    return `No ritmo atual, fecha ${ritmo.year} em ${formatBRLInteiro(ritmo.projecao_anual)}, dentro do limite.`;
  }
  return `Ainda cabem ${formatBRLInteiro(summary.remaining)} até o fim do ano.`;
}

/**
 * Régua do limite anual: o ano como uma régua de 12 meses, preenchida até o
 * que já foi faturado, com o marcador de onde o faturamento estaria hoje se
 * seguisse em linha reta até o teto em 31/12 (a mesma referência do gráfico
 * de corrida, `CorridaContraLimite`).
 */
export function ReguaLimite({ summary, ritmo }: Props) {
  const limite = ritmo?.limite_aplicavel ?? summary.annual_limit;
  const total = summary.total_revenue;
  const preenchido = limite > 0 ? Math.min(100, (total / limite) * 100) : 0;
  const faixa = ritmo ? FAIXA_DO_NIVEL[ritmo.nivel] : FAIXA_DO_ALERTA[summary.alert_level];

  const hoje = ritmo && ritmo.total_dias_ano > 0 ? (ritmo.dias_decorridos / ritmo.total_dias_ano) * 100 : null;
  const referenciaHoje = hoje != null ? (limite * hoje) / 100 : null;

  return (
    <section className="regua" aria-labelledby="regua-frase">
      <h1 id="regua-frase" className="regua-frase">
        Você faturou <span className="valor">{formatBRLInteiro(total)}</span> dos{" "}
        <span className="valor">{formatBRLInteiro(limite)}</span> permitidos ao MEI em {summary.year}.
      </h1>
      <p className="regua-previsao">
        <span className={`regua-selo ${CLASSE_FAIXA[faixa].selo}`}>{ROTULO_FAIXA[faixa]}</span>{" "}
        {previsao(summary, ritmo)}
      </p>

      <div
        className="regua-trilho"
        role="meter"
        aria-label="Faturamento do ano em relação ao limite do MEI"
        aria-valuemin={0}
        aria-valuemax={limite}
        aria-valuenow={Math.min(total, limite)}
        aria-valuetext={`${formatBRLInteiro(total)} de ${formatBRLInteiro(limite)}`}
      >
        <div className={`regua-preenchimento ${CLASSE_FAIXA[faixa].preenchimento}`} style={{ width: `${preenchido}%` }} />
        {MESES.slice(1).map((mes, i) => (
          <span key={mes} className="regua-marca" style={{ left: `${((i + 1) / 12) * 100}%` }} aria-hidden="true" />
        ))}
        {hoje != null && referenciaHoje != null && (
          <span
            className="regua-hoje"
            style={{ left: `${Math.min(100, hoje)}%` }}
            title={`Hoje, no ritmo que leva ao limite em 31/12: ${formatBRLInteiro(referenciaHoje)}`}
          />
        )}
      </div>

      <div className="regua-meses" aria-hidden="true">
        {MESES.map((mes) => (
          <span key={mes}>{mes}</span>
        ))}
      </div>

      {hoje != null && referenciaHoje != null && (
        <p className="regua-legenda">
          <span className="regua-legenda-hoje" aria-hidden="true" />
          Hoje, quem vende em linha reta até o limite estaria em {formatBRLInteiro(referenciaHoje)}.
        </p>
      )}
    </section>
  );
}
