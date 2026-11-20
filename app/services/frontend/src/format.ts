/**
 * Formatação para o padrão brasileiro.
 *
 * Estas funções existem para que a formatação tenha uma definição só. Antes
 * delas, `toLocaleString("pt-BR", ...)` aparecia em treze lugares — e em um
 * deles sem `minimumFractionDigits`, o que fazia o limite anual renderizar
 * como "81.000" enquanto todo o resto mostrava "81.000,00".
 */

const MOEDA = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const NUMERO = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/**
 * Formata um valor monetário em reais: `47304.5` vira `"R$ 47.304,50"`.
 *
 * O espaço entre o símbolo e o número é um espaço não separável (U+00A0),
 * inserido pelo próprio `Intl`. Isso importa nos testes: comparar com um
 * espaço comum falha.
 */
export function formatBRL(valor: number): string {
  if (!Number.isFinite(valor)) return "—";
  return MOEDA.format(valor);
}

const MOEDA_INTEIRA = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 0,
});

/**
 * Valor em reais sem centavos, para frases e destaques: `42310.7` vira
 * `"R$ 42.311"`. Tabelas e extratos continuam com `formatBRL`.
 */
export function formatBRLInteiro(valor: number): string {
  if (!Number.isFinite(valor)) return "—";
  return MOEDA_INTEIRA.format(valor);
}

/** Formata um número com duas casas decimais, sem o símbolo da moeda. */
export function formatNumeroBr(valor: number): string {
  if (!Number.isFinite(valor)) return "—";
  return NUMERO.format(valor);
}

/** Formata um percentual: `58.4` vira `"58,4%"`. */
export function formatPercentual(valor: number, casas = 1): string {
  if (!Number.isFinite(valor)) return "—";
  return `${valor.toFixed(casas).replace(".", ",")}%`;
}

/**
 * Converte uma data ISO (`"2026-08-25"`) para o formato brasileiro
 * (`"25/08/2026"`).
 *
 * Faz isso por manipulação de string, de propósito. Passar `"YYYY-MM-DD"` para
 * `new Date()` assume UTC, e num fuso negativo como o do Brasil o resultado é
 * o dia anterior. Numa aplicação fiscal isso moveria uma nota de um mês para
 * outro — e potencialmente de um ano para outro, no dia 1º de janeiro.
 */
export function formatIsoDateBr(iso: string): string {
  const [yyyy, mm, dd] = iso.split("-");
  return `${dd}/${mm}/${yyyy}`;
}

/** Formata data e hora para exibição: `"25/08/2026 16:04"`. */
export function formatDataHoraBr(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Data de hoje no formato ISO, no fuso local do navegador. */
export function todayIso(): string {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}
