import { useState, type DragEvent } from "react";
import { useAparencia } from "../aparencia/AparenciaContext";

const ACEITOS = ".pdf,.png,.jpg,.jpeg,.txt";
const ICONES: Record<string, string> = { pdf: "📕", png: "🖼️", jpg: "🖼️", jpeg: "🖼️", txt: "📄" };

function tamanho(bytes: number) {
  return bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(0)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/**
 * Área de envio: arrastar e soltar ou clicar para escolher. O `<input
 * type="file">` continua no DOM (visualmente oculto) — teclado, leitor de
 * tela e testes usam o controle nativo.
 */
export function SoltarArquivo({
  arquivo,
  onEscolher,
  desabilitado,
}: {
  arquivo: File | null;
  onEscolher: (arquivo: File | null) => void;
  desabilitado?: boolean;
}) {
  const [arrastando, setArrastando] = useState(false);
  const { visualNovo } = useAparencia();

  const soltar = (e: DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    setArrastando(false);
    if (!desabilitado && e.dataTransfer.files[0]) onEscolher(e.dataTransfer.files[0]);
  };

  const extensao = arquivo?.name.split(".").pop()?.toLowerCase() ?? "";

  return (
    <div>
    <label
      onDragOver={(e) => {
        e.preventDefault();
        setArrastando(true);
      }}
      onDragLeave={() => setArrastando(false)}
      onDrop={soltar}
      className={`mb-0 flex cursor-pointer flex-col items-center justify-center gap-2 border-2 border-dashed px-6 py-10 text-center font-normal transition-colors focus-within:border-acento ${
        visualNovo ? "rounded-card focus-within:shadow-foco" : "rounded-2xl"
      } ${
        visualNovo
          ? arrastando
            ? "scale-[1.01] border-acento bg-acento/[0.06]"
            : arquivo
              ? "border-limite-ok/60 bg-limite-ok-suave"
              : "border-borda-forte bg-fundo-poco/60 hover:border-tinta-suave"
          : arrastando
          ? "border-acento bg-acento/10"
          : arquivo
            ? "border-limite-ok/50 bg-limite-ok/[0.06]"
            : "border-borda-forte bg-veu/[0.02] hover:border-acento/50 hover:bg-acento/[0.05]"
      }`}
    >
      <input
        type="file"
        accept={ACEITOS}
        className="sr-only"
        disabled={desabilitado}
        onChange={(e) => onEscolher(e.target.files?.[0] || null)}
        required
      />
      {arquivo ? (
        <>
          {visualNovo ? (
            <IconeArquivo pronto />
          ) : (
            <div className="text-4xl" aria-hidden="true">
              {ICONES[extensao] ?? "📎"}
            </div>
          )}
          <div className="font-semibold text-tinta-forte">{arquivo.name}</div>
          <div className="text-xs text-tinta-suave">
            {visualNovo
              ? `${extensao.toUpperCase()}, ${tamanho(arquivo.size)}. Clique ou arraste outro arquivo para trocar.`
              : `${extensao.toUpperCase()} · ${tamanho(arquivo.size)} · clique ou arraste outro para trocar`}
          </div>
        </>
      ) : (
        <>
          {visualNovo ? (
            <IconeArquivo />
          ) : (
            <div className="grid h-14 w-14 place-items-center rounded-2xl bg-acento/15 text-2xl" aria-hidden="true">
              ⬆
            </div>
          )}
          <div className="font-semibold text-tinta-forte">
            {arrastando ? "Solte o arquivo aqui" : "Arraste a nota fiscal ou clique para escolher"}
          </div>
          <div className={visualNovo ? "text-sm text-tinta-suave" : "text-xs text-tinta-suave"}>
            {visualNovo
              ? "Aceita PDF, foto (PNG ou JPG) ou texto: DANFE, nota de serviço ou cupom."
              : "PDF, PNG, JPG ou TXT — DANFE, DANFSe, cupom ou foto"}
          </div>
        </>
      )}
    </label>
      {/* issue 100: no celular, abre direto a câmera traseira. No computador, o
          mesmo controle cai no seletor de arquivos. */}
      <label
        className={`mb-0 mt-3 inline-flex w-full cursor-pointer items-center justify-center gap-2 font-semibold sm:w-auto ${
          visualNovo ? "botao botao-secundario" : "rounded-campo border border-borda-forte px-4 py-3 text-tinta"
        } ${desabilitado ? "pointer-events-none opacity-60" : ""}`}
      >
        <input
          type="file"
          accept="image/*"
          capture="environment"
          className="sr-only"
          disabled={desabilitado}
          aria-label="Tirar foto da nota"
          onChange={(e) => onEscolher(e.target.files?.[0] || null)}
        />
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5" aria-hidden="true">
          <path d="M4 8h3l2-3h6l2 3h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1Z" />
          <circle cx="12" cy="13" r="3.5" />
        </svg>
        Tirar foto da nota
      </label>
    </div>
  );
}

function IconeArquivo({ pronto }: { pronto?: boolean }) {
  return (
    <div
      className={`grid h-14 w-14 place-items-center rounded-full ${pronto ? "bg-limite-ok text-sobre-acento" : "bg-veu/[0.07] text-tinta-leve"}`}
      aria-hidden="true"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-6 w-6">
        {pronto ? (
          <path d="m5 12.5 4.5 4.5L19 7.5" />
        ) : (
          <>
            <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z" />
            <path d="M14 3v5h5M12 18v-6M9.5 14.5 12 12l2.5 2.5" />
          </>
        )}
      </svg>
    </div>
  );
}
