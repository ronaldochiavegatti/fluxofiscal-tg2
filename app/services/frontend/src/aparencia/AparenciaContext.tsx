import { createContext, useContext, useEffect, useLayoutEffect, useState, type PropsWithChildren } from "react";
import { useFeatureFlag } from "../flags/useFeatureFlag";
import { useLocalStorage } from "../hooks/useLocalStorage";

export type PreferenciaTema = "claro" | "escuro" | "sistema";

type Aparencia = {
  /** Flag `visual-novo` ligada: identidade nova (papel + caneta) e tema claro/escuro. */
  visualNovo: boolean;
  preferencia: PreferenciaTema;
  setPreferencia: (p: PreferenciaTema) => void;
  /** Tema efetivo depois de resolver "sistema". */
  escuro: boolean;
};

const AparenciaContext = createContext<Aparencia>({
  visualNovo: false,
  preferencia: "sistema",
  setPreferencia: () => undefined,
  escuro: true,
});

const CONSULTA_ESCURO = "(prefers-color-scheme: dark)";

function useSistemaEscuro() {
  const [escuro, setEscuro] = useState(
    () => typeof window !== "undefined" && !!window.matchMedia?.(CONSULTA_ESCURO).matches
  );
  useEffect(() => {
    const mq = window.matchMedia?.(CONSULTA_ESCURO);
    if (!mq) return;
    const aoMudar = (e: MediaQueryListEvent) => setEscuro(e.matches);
    mq.addEventListener("change", aoMudar);
    return () => mq.removeEventListener("change", aoMudar);
  }, []);
  return escuro;
}

const CHAVE_ULTIMO_VALOR = "visual-novo-ultimo";

/**
 * Padrão da flag enquanto o Unleash não respondeu (ou se ele estiver fora):
 * o último valor que este navegador recebeu dele. Sem isso, toda recarga
 * mostrava o visual atual por um instante e trocava para o novo quando as
 * flags chegavam. Sem valor guardado: desligada, salvo se o build local pedir
 * o contrário com `VITE_VISUAL_NOVO=true` (apresentação sem Unleash no ar).
 */
export function padraoVisualNovo(): boolean {
  try {
    const ultimo = localStorage.getItem(CHAVE_ULTIMO_VALOR);
    if (ultimo === "true" || ultimo === "false") return ultimo === "true";
  } catch {
    // Armazenamento bloqueado (modo privado): segue para o padrão do build.
  }
  return import.meta.env.VITE_VISUAL_NOVO === "true";
}

function guardarUltimoValor(ativo: boolean) {
  try {
    localStorage.setItem(CHAVE_ULTIMO_VALOR, String(ativo));
  } catch {
    // Sem armazenamento, a próxima carga usa o padrão do build.
  }
}

/**
 * Fonte do visual novo. Só é pedida ao Google Fonts com a flag ligada: com ela
 * desligada o visual atual não faz nenhuma requisição a mais.
 */
export const URL_FONTE_VISUAL_NOVO =
  "https://fonts.googleapis.com/css2?family=Instrument+Sans:wdth,wght@75..100,400..700&display=swap";
const ID_FONTE = "fonte-visual-novo";

function carregarFonteVisualNovo() {
  if (document.getElementById(ID_FONTE)) return;
  const link = document.createElement("link");
  link.id = ID_FONTE;
  link.rel = "stylesheet";
  link.href = URL_FONTE_VISUAL_NOVO;
  document.head.appendChild(link);
}

/**
 * Liga o visual novo no `<html>` (`data-visual="novo"`) e aplica o tema
 * (`data-tema`). As paletas moram em `tailwind.config.js`; aqui só se escolhe
 * qual delas vale. Com a flag desligada os atributos saem e o visual atual
 * volta intacto.
 */
export function AparenciaProvider({ children }: PropsWithChildren) {
  const visualNovo = useFeatureFlag("visual-novo", padraoVisualNovo());
  const [preferencia, setPreferencia] = useLocalStorage<PreferenciaTema>("tema", "sistema");
  const sistemaEscuro = useSistemaEscuro();
  const escuro = visualNovo ? preferencia === "escuro" || (preferencia === "sistema" && sistemaEscuro) : true;

  // useLayoutEffect: o atributo muda antes da pintura, sem um quadro com o
  // visual errado quando a flag chega diferente do valor guardado.
  useLayoutEffect(() => {
    guardarUltimoValor(visualNovo);
    const raiz = document.documentElement;
    if (visualNovo) {
      carregarFonteVisualNovo();
      raiz.dataset.visual = "novo";
      raiz.dataset.tema = escuro ? "escuro" : "claro";
    } else {
      delete raiz.dataset.visual;
      delete raiz.dataset.tema;
    }
  }, [visualNovo, escuro]);

  return (
    <AparenciaContext.Provider value={{ visualNovo, preferencia, setPreferencia, escuro }}>
      {children}
    </AparenciaContext.Provider>
  );
}

export function useAparencia() {
  return useContext(AparenciaContext);
}
