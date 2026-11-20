import { useEffect, useRef, useState } from "react";

/**
 * Largura do elemento referenciado, acompanhando redimensionamento.
 *
 * Substitui o `ResponsiveContainer` do Recharts, que exige `ResizeObserver`
 * sem fallback. No jsdom (testes) ele não existe, e o gráfico fica com a
 * largura `padrao` — o mesmo comportamento da largura fixa de antes.
 */
export function useLargura<T extends HTMLElement>(padrao: number) {
  const ref = useRef<T>(null);
  const [largura, setLargura] = useState(padrao);

  useEffect(() => {
    const elemento = ref.current;
    if (!elemento || typeof ResizeObserver === "undefined") return;
    const observador = new ResizeObserver(([entrada]) => {
      const medida = Math.floor(entrada.contentRect.width);
      if (medida > 0) setLargura(medida);
    });
    observador.observe(elemento);
    return () => observador.disconnect();
  }, []);

  return [ref, largura] as const;
}
