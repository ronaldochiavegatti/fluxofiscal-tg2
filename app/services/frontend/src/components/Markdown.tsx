import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Resposta do agente renderizada como Markdown (o Gemini responde com
 * títulos, listas, negrito e tabelas). Sem `rehype-raw`: HTML vindo do modelo
 * é exibido como texto, nunca interpretado — a resposta não pode injetar
 * marcação na página.
 */
const COMPONENTES: Components = {
  h1: ({ children }) => <h4 className="mb-2 mt-3 text-base font-bold first:mt-0">{children}</h4>,
  h2: ({ children }) => <h4 className="mb-2 mt-3 text-base font-bold first:mt-0">{children}</h4>,
  h3: ({ children }) => <h5 className="mb-1.5 mt-3 text-[15px] font-bold first:mt-0">{children}</h5>,
  h4: ({ children }) => <h6 className="mb-1 mt-2 text-sm font-bold first:mt-0">{children}</h6>,
  p: ({ children }) => <p className="my-2 leading-relaxed first:mt-0 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5 marker:text-acento">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5 marker:text-acento">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-tinta-forte">{children}</strong>,
  em: ({ children }) => <em className="text-tinta-leve">{children}</em>,
  hr: () => <hr className="my-3 border-0 border-t border-borda" />,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer" className="text-acento-claro underline">
      {children}
    </a>
  ),
  code: ({ children }) => (
    <code className="rounded bg-veu/[0.08] px-1.5 py-0.5 text-[13px]">{children}</code>
  ),
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-2 border-acento/60 pl-3 text-tinta-leve">{children}</blockquote>
  ),
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto">
      <div className="tabela-rolavel">
        <table className="table mt-0">{children}</table>
      </div>
    </div>
  ),
};

export function Markdown({ texto }: { texto: string }) {
  return (
    <div className="text-[14.5px] text-tinta">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={COMPONENTES}>
        {texto}
      </ReactMarkdown>
    </div>
  );
}
