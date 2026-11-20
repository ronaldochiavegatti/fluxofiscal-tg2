import type { ReactNode } from "react";

type Props = {
  title: string;
  value: string;
  helper?: string;
  /** Classe de cor Tailwind para o texto de apoio (ex.: "text-limite-ok"). */
  accent?: string;
  /** Conteúdo extra abaixo do valor (ex.: barra de progresso). */
  children?: ReactNode;
};

export function StatCard({ title, value, helper, accent, children }: Props) {
  return (
    <div className="card">
      <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-tinta-suave">{title}</div>
      <div className="font-display text-[28px] font-bold leading-tight text-tinta-forte">{value}</div>
      {helper && (
        <div className={`mt-1.5 text-[13px] ${accent || "text-acento-claro"}`}>{helper}</div>
      )}
      {children && <div className="mt-3">{children}</div>}
    </div>
  );
}
