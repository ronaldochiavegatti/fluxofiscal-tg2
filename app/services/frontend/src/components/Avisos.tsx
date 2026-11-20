import { createContext, useCallback, useContext, useRef, useState, type PropsWithChildren } from "react";
import { useAparencia } from "../aparencia/AparenciaContext";
import { IconeVisto } from "./interacao";

type TipoAviso = "sucesso" | "erro" | "info";
type Aviso = { id: number; tipo: TipoAviso; texto: string };

const DURACAO_MS = 4500;

const AvisosContext = createContext<(tipo: TipoAviso, texto: string) => void>(() => undefined);

const CLASSE_AVISO: Record<TipoAviso, string> = {
  sucesso: "aviso aviso-sucesso",
  erro: "aviso aviso-erro",
  info: "aviso",
};

/**
 * Avisos temporários (toast) para confirmar uma ação concluída: somem
 * sozinhos em 4,5 s ou no botão fechar, e são lidos pelo leitor de tela via
 * `aria-live`. Só aparecem no visual novo; no atual, `avisar` não faz nada.
 */
export function AvisosProvider({ children }: PropsWithChildren) {
  const { visualNovo } = useAparencia();
  const [avisos, setAvisos] = useState<Aviso[]>([]);
  const proximoId = useRef(1);

  const fechar = useCallback((id: number) => setAvisos((lista) => lista.filter((a) => a.id !== id)), []);

  const avisar = useCallback(
    (tipo: TipoAviso, texto: string) => {
      if (!visualNovo) return;
      const id = proximoId.current++;
      setAvisos((lista) => [...lista.slice(-2), { id, tipo, texto }]);
      window.setTimeout(() => fechar(id), DURACAO_MS);
    },
    [visualNovo, fechar]
  );

  return (
    <AvisosContext.Provider value={avisar}>
      {children}
      <div className="avisos" aria-live="polite" aria-atomic="false">
        {avisos.map((aviso) => (
          <div key={aviso.id} className={CLASSE_AVISO[aviso.tipo]} role={aviso.tipo === "erro" ? "alert" : "status"}>
            {aviso.tipo === "sucesso" && (
              <span className="aviso-icone">
                <IconeVisto />
              </span>
            )}
            <span className="flex-1">{aviso.texto}</span>
            <button type="button" className="aviso-fechar" aria-label="Fechar aviso" onClick={() => fechar(aviso.id)}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
                <path d="M6 6l12 12M18 6 6 18" />
              </svg>
            </button>
          </div>
        ))}
      </div>
    </AvisosContext.Provider>
  );
}

export function useAvisos() {
  return useContext(AvisosContext);
}
