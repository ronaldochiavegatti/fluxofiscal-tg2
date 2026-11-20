import type { ReactNode } from "react";
import { useAparencia, type PreferenciaTema } from "./AparenciaContext";

const OPCOES: { valor: PreferenciaTema; rotulo: string; icone: ReactNode }[] = [
  {
    valor: "claro",
    rotulo: "Claro",
    icone: (
      <path d="M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10Zm0-5 1 3h-2l1-3Zm0 20-1-3h2l-1 3ZM2 12l3-1v2l-3-1Zm20 0-3 1v-2l3 1ZM4.9 4.9l2.8 1.4-1.4 1.4-1.4-2.8Zm14.2 14.2-2.8-1.4 1.4-1.4 1.4 2.8Zm0-14.2-1.4 2.8-1.4-1.4 2.8-1.4ZM4.9 19.1l1.4-2.8 1.4 1.4-2.8 1.4Z" />
    ),
  },
  {
    valor: "escuro",
    rotulo: "Escuro",
    icone: <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" />,
  },
  {
    valor: "sistema",
    rotulo: "Sistema",
    icone: <path d="M3 4h18v12H3V4Zm2 2v8h14V6H5Zm3 12h8v2H8v-2Z" />,
  },
];

/** Escolha de tema (claro, escuro ou o do sistema). Só aparece no visual novo. */
export function SeletorTema() {
  const { visualNovo, preferencia, setPreferencia } = useAparencia();
  if (!visualNovo) return null;

  return (
    <div role="radiogroup" aria-label="Tema" className="seletor-tema">
      {OPCOES.map((opcao) => (
        <button
          key={opcao.valor}
          type="button"
          role="radio"
          aria-checked={preferencia === opcao.valor}
          title={opcao.rotulo}
          onClick={() => setPreferencia(opcao.valor)}
          className="seletor-tema-opcao"
        >
          <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            {opcao.icone}
          </svg>
          <span className="sr-only">{opcao.rotulo}</span>
        </button>
      ))}
    </div>
  );
}
