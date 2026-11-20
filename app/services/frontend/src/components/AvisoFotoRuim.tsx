import { useEffect, useRef, useState } from "react";
import { Botao } from "./Botao";

export type FotoRuim = { mensagem: string; dica: string; arquivo: File | null };

/**
 * A foto não dá para ler (issue 100): diz o que está errado e como corrigir, antes
 * de gastar a leitura. "Enviar mesmo assim" existe porque a checagem pode
 * errar, e quem decide é o usuário.
 */
export function AvisoFotoRuim({
  foto,
  visualNovo,
  onTirarOutra,
  onEnviarMesmoAssim,
}: {
  foto: FotoRuim;
  visualNovo: boolean;
  onTirarOutra: () => void;
  onEnviarMesmoAssim: () => void;
}) {
  const titulo = useRef<HTMLHeadingElement>(null);
  useEffect(() => titulo.current?.focus(), []);

  // Prévia da própria foto: ver o borrão convence mais que a mensagem.
  const [previa, setPrevia] = useState<string | null>(null);
  useEffect(() => {
    if (!foto.arquivo || typeof URL.createObjectURL !== "function") return;
    const url = URL.createObjectURL(foto.arquivo);
    setPrevia(url);
    return () => URL.revokeObjectURL(url);
  }, [foto.arquivo]);

  return (
    <section
      className={visualNovo ? "painel mt-6 border-limite-atencao/50" : "card"}
      style={visualNovo ? undefined : { marginTop: 16 }}
      role="alertdialog"
      aria-labelledby="titulo-foto-ruim"
      aria-describedby="texto-foto-ruim"
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
        {previa && (
          <img
            src={previa}
            alt="Foto enviada"
            className="h-32 w-24 shrink-0 rounded-campo border border-borda object-cover"
          />
        )}
        <div className="min-w-0">
          <h2
            id="titulo-foto-ruim"
            ref={titulo}
            tabIndex={-1}
            className="m-0 text-lg font-semibold text-limite-atencao outline-none"
          >
            Essa foto não vai dar para ler
          </h2>
          <div id="texto-foto-ruim">
            <p className="mb-0 mt-1 text-tinta-leve">{foto.mensagem}</p>
            <p className="mb-0 mt-2 text-tinta-leve">
              <strong className="text-tinta-forte">Como resolver:</strong> {foto.dica}
            </p>
            <p className="mb-0 mt-2 text-sm text-tinta-suave">
              A foto não foi enviada para leitura, então nada foi gasto.
            </p>
          </div>
        </div>
      </div>
      <div className="mt-5 flex flex-wrap gap-2.5">
        <Botao onClick={onTirarOutra}>Tirar outra foto</Botao>
        <Botao variante="secundario" onClick={onEnviarMesmoAssim}>
          Enviar mesmo assim
        </Botao>
      </div>
    </section>
  );
}
