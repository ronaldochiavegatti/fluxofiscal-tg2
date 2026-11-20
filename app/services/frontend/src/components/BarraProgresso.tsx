type Marco = { em: number; rotulo: string };

type Props = {
  /** Percentual do valor (pode passar de 100 — a barra trava no fim e muda de cor). */
  percentual: number;
  marcos?: Marco[];
  /** Rótulo acessível da barra. */
  rotulo: string;
  fina?: boolean;
};

function corDaBarra(percentual: number) {
  if (percentual >= 100) return "!bg-limite-estourado";
  if (percentual >= 80) return "!bg-limite-atencao";
  return "";
}

/**
 * Barra de progresso com marcos (ex.: 80% = atenção, 100% = teto). A cor
 * acompanha a faixa, mas o número e os marcos rotulados também contam a
 * história — cor nunca é o único sinal (`docs/dashboard-v2.md` §6).
 */
export function BarraProgresso({ percentual, marcos = [], rotulo, fina }: Props) {
  const largura = Math.min(100, Math.max(0, percentual));
  return (
    <div>
      <div
        className={`progress relative ${fina ? "!h-1.5" : "!h-3"}`}
        role="progressbar"
        aria-label={rotulo}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(largura)}
      >
        <div className={`progress-bar ${corDaBarra(percentual)}`} style={{ width: `${largura}%` }} />
        {marcos.map((marco) => (
          <div
            key={marco.em}
            aria-hidden="true"
            className="absolute top-0 h-full w-0.5 bg-tinta-forte/40"
            style={{ left: `${marco.em}%` }}
          />
        ))}
      </div>
      {marcos.length > 0 && (
        <div className="relative mt-1 h-4 text-[10.5px] text-tinta-suave">
          {marcos.map((marco) => (
            <span
              key={marco.em}
              className="absolute -translate-x-1/2 whitespace-nowrap"
              style={{ left: `${Math.min(marco.em, 96)}%` }}
            >
              {marco.rotulo}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
