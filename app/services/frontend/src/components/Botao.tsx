import type { ButtonHTMLAttributes, ReactNode } from "react";

export type VarianteBotao = "primario" | "secundario" | "discreto" | "perigo";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variante?: VarianteBotao;
  /** Mostra o indicador e bloqueia novo clique; o texto deve dizer o que está acontecendo. */
  carregando?: boolean;
  icone?: ReactNode;
  tamanho?: "md" | "sm";
};

// Nomes de classe por extenso: o Tailwind só mantém no CSS final as classes
// que encontra escritas no código, e `botao-${variante}` seria descartada.
const CLASSE_VARIANTE: Record<VarianteBotao, string> = {
  primario: "botao-primario",
  secundario: "botao-secundario",
  discreto: "botao-discreto",
  perigo: "botao-perigo",
};

/** Classes do botão, para quando o elemento precisa ser um `<Link>` ou `<a>`. */
export function classesBotao(variante: VarianteBotao = "primario", tamanho: "md" | "sm" = "md") {
  return `botao ${CLASSE_VARIANTE[variante]}${tamanho === "sm" ? " botao-sm" : ""}`;
}

/**
 * Botão padrão do sistema: quatro variantes, um tamanho de toque mínimo e os
 * mesmos estados em todas (hover, foco visível, pressionado, desabilitado,
 * carregando). O visual mora em `index.css` (`.botao*`).
 */
export function Botao({
  variante = "primario",
  carregando = false,
  icone,
  tamanho = "md",
  className = "",
  disabled,
  children,
  type = "button",
  ...resto
}: Props) {
  return (
    <button
      type={type}
      className={`${classesBotao(variante, tamanho)} ${className}`.trim()}
      disabled={disabled || carregando}
      aria-busy={carregando || undefined}
      {...resto}
    >
      {carregando ? <span className="botao-giro" aria-hidden="true" /> : icone}
      {children}
    </button>
  );
}
