import { useEffect, useRef } from "react";
import { formatBRL, formatIsoDateBr } from "../format";
import type { Repeticao } from "../types";
import { Botao } from "./Botao";

type Props = {
  repeticoes: Repeticao[];
  visualNovo: boolean;
  onContinuar: () => void;
  onCancelar: () => void;
};

function descrever(r: Repeticao): string {
  const partes = [r.nome_original];
  if (r.valor != null && r.data) {
    const tipo = r.tx_type === "compra" ? "compra" : r.tx_type === "venda" ? "venda" : "nota";
    partes.push(`${tipo} de ${formatBRL(r.valor)} em ${formatIsoDateBr(r.data)}`);
  }
  partes.push(`enviada em ${formatIsoDateBr(r.enviado_em.slice(0, 10))}`);
  return partes.join(" · ");
}

/**
 * Pergunta antes de abrir a conferência quando a nota parece já ter sido
 * salva (#93): salvar de novo lançaria o mesmo valor duas vezes no
 * faturamento. O usuário decide — duas vendas iguais no mesmo dia existem.
 */
export function AvisoNotaRepetida({ repeticoes, visualNovo, onContinuar, onCancelar }: Props) {
  const titulo = useRef<HTMLHeadingElement>(null);
  useEffect(() => titulo.current?.focus(), []);

  const mesmoArquivo = repeticoes.some((r) => r.mesmo_arquivo);
  const cabecalho = mesmoArquivo ? "Este arquivo já foi salvo" : "Esta nota parece já ter sido salva";
  const explicacao = mesmoArquivo
    ? "Você já enviou e salvou este mesmo arquivo:"
    : "Você já salvou uma nota com o mesmo valor, data e CNPJ de quem emitiu:";

  return (
    <section
      className={visualNovo ? "painel mt-6 border-limite-atencao/50" : "card"}
      style={visualNovo ? undefined : { marginTop: 16 }}
      aria-labelledby="titulo-repeticao"
      role="alertdialog"
      aria-describedby="texto-repeticao"
    >
      <h2
        id="titulo-repeticao"
        ref={titulo}
        tabIndex={-1}
        className="m-0 text-lg font-semibold text-limite-atencao outline-none"
      >
        {cabecalho}
      </h2>
      <div id="texto-repeticao">
        <p className="mb-0 mt-1 text-tinta-leve">{explicacao}</p>
        <ul className="mb-0 mt-2 pl-5 text-tinta-leve">
          {repeticoes.map((r) => (
            <li key={r.documento_id}>{descrever(r)}</li>
          ))}
        </ul>
        <p className="mb-0 mt-3 text-tinta-suave">
          Se salvar de novo, o valor entra mais uma vez no seu faturamento. Quer continuar mesmo assim?
        </p>
      </div>
      <div className="mt-5 flex flex-wrap gap-2.5">
        <Botao onClick={onContinuar}>Continuar mesmo assim</Botao>
        <Botao variante="secundario" onClick={onCancelar}>
          Cancelar envio
        </Botao>
      </div>
    </section>
  );
}
