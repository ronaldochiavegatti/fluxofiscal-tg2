import { useEffect, useState, type ReactNode } from "react";

/**
 * Peças de interação do visual novo (flag `visual-novo`): cabeçalho de página,
 * etapas, progresso de espera, contador de tempo e estado vazio. Todas usam
 * as classes de `index.css` e os tokens do tema.
 */

/** Segundos desde que `ativo` virou true; zera quando volta a false. */
export function useSegundos(ativo: boolean): number {
  const [segundos, setSegundos] = useState(0);
  useEffect(() => {
    if (!ativo) {
      setSegundos(0);
      return;
    }
    const inicio = Date.now();
    const t = window.setInterval(() => setSegundos(Math.floor((Date.now() - inicio) / 1000)), 1000);
    return () => window.clearInterval(t);
  }, [ativo]);
  return segundos;
}

/** Cabeçalho padrão: título da tela, uma frase do que ela faz e as ações. */
export function CabecalhoPagina({
  titulo,
  descricao,
  acoes,
}: {
  titulo: string;
  descricao?: ReactNode;
  acoes?: ReactNode;
}) {
  return (
    <header className="cabecalho-pagina">
      <div className="min-w-0">
        <h1 className="cabecalho-titulo">{titulo}</h1>
        {descricao && <p className="cabecalho-descricao">{descricao}</p>}
      </div>
      {acoes && <div className="flex flex-wrap items-center gap-2.5">{acoes}</div>}
    </header>
  );
}

/**
 * Etapas de um fluxo ("Etapa 2 de 4"). A etapa atual leva
 * `aria-current="step"`; as anteriores, um visto.
 */
export function Etapas({ etapas, atual }: { etapas: string[]; atual: number }) {
  return (
    <nav aria-label={`Etapa ${atual + 1} de ${etapas.length}`} className="etapas">
      <ol>
        {etapas.map((etapa, i) => {
          const estado = i < atual ? "feita" : i === atual ? "atual" : "proxima";
          return (
            <li key={etapa} className={CLASSE_ETAPA[estado]} aria-current={i === atual ? "step" : undefined}>
              <span className="etapa-marca" aria-hidden="true">
                {i < atual ? <IconeVisto /> : i + 1}
              </span>
              <span className="etapa-rotulo">{etapa}</span>
              {i < atual && <span className="sr-only"> (concluída)</span>}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

const CLASSE_ETAPA = { feita: "etapa etapa-feita", atual: "etapa etapa-atual", proxima: "etapa" } as const;

export function IconeVisto() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="m5 12.5 4.5 4.5L19 7.5" />
    </svg>
  );
}

/** Barra para espera sem duração conhecida: mostra movimento sem inventar percentual. */
export function ProgressoIndeterminado({ rotulo }: { rotulo: string }) {
  return (
    <div className="barra-indeterminada" role="progressbar" aria-label={rotulo} aria-busy="true">
      <span />
    </div>
  );
}

/** "12 s", "1 min 05 s". */
export function formatarDuracao(segundos: number): string {
  if (segundos < 60) return `${segundos} s`;
  const min = Math.floor(segundos / 60);
  return `${min} min ${String(segundos % 60).padStart(2, "0")} s`;
}

/** Tela vazia que diz o que fazer em seguida. */
export function EstadoVazio({
  titulo,
  texto,
  acao,
  icone,
}: {
  titulo: string;
  texto: string;
  acao?: ReactNode;
  icone?: ReactNode;
}) {
  return (
    <div className="estado-vazio">
      {icone && (
        <div className="estado-vazio-icone" aria-hidden="true">
          {icone}
        </div>
      )}
      <div className="text-lg font-semibold text-tinta-forte">{titulo}</div>
      <p className="m-0 mt-1 max-w-[48ch] text-tinta-suave">{texto}</p>
      {acao && <div className="mt-5">{acao}</div>}
    </div>
  );
}
