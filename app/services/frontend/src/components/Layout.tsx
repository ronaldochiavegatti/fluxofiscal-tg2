import { Link, useLocation } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useTokens } from "../TokensContext";
import { useUserCnpj } from "../useUserCnpj";
import { useAparencia } from "../aparencia/AparenciaContext";
import { SeletorTema } from "../aparencia/SeletorTema";
import { useFeatureFlag } from "../flags/useFeatureFlag";

type LayoutProps = {
  children: ReactNode;
  userEmail?: string;
};

// Ícones em SVG inline com `currentColor`: herdam a cor do link (ativo/hover)
// sem depender de biblioteca de ícones nem de cor literal (ADR-0010).
const ICONES: Record<string, ReactNode> = {
  dashboard: <path d="M3 13h8V3H3v10Zm0 8h8v-6H3v6Zm10 0h8V11h-8v10Zm0-18v6h8V3h-8Z" />,
  upload: <path d="M12 3 7 8h3v6h4V8h3l-5-5ZM5 18v2h14v-2H5Z" />,
  documentos: (
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6Zm0 7V3.5L19.5 9H14ZM8 13h8v2H8v-2Zm0 4h5v2H8v-2Z" />
  ),
  configuracoes: (
    <path d="M19.4 13a7.6 7.6 0 0 0 0-2l2-1.6-2-3.4-2.4 1a7.5 7.5 0 0 0-1.7-1L15 3.5h-4L10.7 6a7.5 7.5 0 0 0-1.7 1l-2.4-1-2 3.4 2 1.6a7.6 7.6 0 0 0 0 2l-2 1.6 2 3.4 2.4-1a7.5 7.5 0 0 0 1.7 1l.3 2.5h4l.3-2.5a7.5 7.5 0 0 0 1.7-1l2.4 1 2-3.4-2-1.6ZM13 15.5a3.5 3.5 0 1 1 0-7 3.5 3.5 0 0 1 0 7Z" transform="translate(-1 0)" />
  ),
  agente: (
    <path d="M12 2a9 9 0 0 0-7.8 13.5L3 21l5.6-1.2A9 9 0 1 0 12 2Zm-4 10a1.25 1.25 0 1 1 0-2.5A1.25 1.25 0 0 1 8 12Zm4 0a1.25 1.25 0 1 1 0-2.5 1.25 1.25 0 0 1 0 2.5Zm4 0a1.25 1.25 0 1 1 0-2.5 1.25 1.25 0 0 1 0 2.5Z" />
  ),
};

const navItems = [
  { to: "/dashboard", label: "Dashboard", labelNovo: "Painel", icone: "dashboard" },
  { to: "/upload", label: "Enviar nota", labelNovo: "Enviar nota", icone: "upload" },
  { to: "/documents", label: "Documentos", labelNovo: "Documentos", icone: "documentos" },
  { to: "/chat", label: "Agente Contábil", labelNovo: "Perguntar ao agente", icone: "agente" },
];

/**
 * Abaixo de 1024 px (celular e tablet) o visual novo troca o menu lateral fixo
 * por uma barra no topo com botão de menu. Mesmo corte do `@media` em
 * index.css (`.app-shell-compacta`).
 */
const CONSULTA_COMPACTA = "(max-width: 1023px)";

function useCompacta() {
  const [compacta, setCompacta] = useState(
    () => typeof window !== "undefined" && !!window.matchMedia?.(CONSULTA_COMPACTA).matches
  );
  useEffect(() => {
    const mq = window.matchMedia?.(CONSULTA_COMPACTA);
    if (!mq) return;
    const aoMudar = (e: MediaQueryListEvent) => setCompacta(e.matches);
    mq.addEventListener("change", aoMudar);
    return () => mq.removeEventListener("change", aoMudar);
  }, []);
  return compacta;
}

function iniciais(email: string) {
  return email.slice(0, 2).toUpperCase();
}

function Marca() {
  return (
    <div className="marca">
      <div className="marca-logo" aria-hidden="true">
        F
      </div>
      <div>
        <div className="font-display text-[17px] font-bold text-tinta-forte">FluxoFiscal</div>
        <div className="text-xs text-tinta-suave">Assistente fiscal do MEI</div>
      </div>
    </div>
  );
}

export function Layout({ children, userEmail }: LayoutProps) {
  const { pathname } = useLocation();
  const { balance, ilimitado, loading } = useTokens();
  const [userCnpj, setUserCnpj] = useUserCnpj();
  const { visualNovo } = useAparencia();
  const metricasConfiguraveis = useFeatureFlag("metricas-configuraveis", false);
  const itensMenu = metricasConfiguraveis
    ? [...navItems, { to: "/configuracoes", label: "Configurações", labelNovo: "Configurações", icone: "configuracoes" }]
    : navItems;
  const compacta = useCompacta() && visualNovo;
  const [menuAberto, setMenuAberto] = useState(false);
  const botaoMenuRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLElement>(null);

  const saldo = loading ? "Carregando..." : ilimitado ? "Ilimitados" : `${balance ?? 0}`;

  // Trocar de tela fecha o menu; voltar para a largura de desktop também.
  useEffect(() => setMenuAberto(false), [pathname, compacta]);

  // Menu aberto: foco vai para o primeiro link, Esc fecha e devolve o foco ao
  // botão, e a página por trás não rola.
  useEffect(() => {
    if (!menuAberto) return;
    menuRef.current?.querySelector<HTMLElement>("a, button, input")?.focus();
    const aoTeclar = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMenuAberto(false);
        botaoMenuRef.current?.focus();
      }
    };
    document.addEventListener("keydown", aoTeclar);
    const overflowAnterior = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", aoTeclar);
      document.body.style.overflow = overflowAnterior;
    };
  }, [menuAberto]);

  const classeMenu = compacta ? `sidebar menu-gaveta${menuAberto ? " menu-aberto" : ""}` : "sidebar";

  return (
    <div className={compacta ? "app-shell app-shell-compacta" : "app-shell"}>
      {compacta && (
        <header className="barra-topo">
          <Marca />
          <button
            ref={botaoMenuRef}
            type="button"
            className="botao-menu"
            aria-expanded={menuAberto}
            aria-controls="menu-principal"
            onClick={() => setMenuAberto((aberto) => !aberto)}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              {menuAberto ? <path d="M6 6l12 12M18 6 6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
            </svg>
            <span className="sr-only">{menuAberto ? "Fechar menu" : "Abrir menu"}</span>
          </button>
        </header>
      )}

      {compacta && menuAberto && <div className="menu-fundo" aria-hidden="true" onClick={() => setMenuAberto(false)} />}

      <aside id="menu-principal" ref={menuRef} className={classeMenu} aria-label={compacta ? "Menu" : undefined}>
        {!compacta && <Marca />}

        {!visualNovo && <div className="nav-secao">Menu</div>}
        <nav aria-label="Principal">
          {itensMenu.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              className={`nav-link ${pathname.startsWith(item.to) ? "active" : ""}`}
              aria-current={pathname.startsWith(item.to) ? "page" : undefined}
            >
              <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                {ICONES[item.icone]}
              </svg>
              {visualNovo ? item.labelNovo : item.label}
            </Link>
          ))}
        </nav>

        <div className="mt-auto flex flex-col gap-3 pt-6">
          {visualNovo && (
            <div className="flex items-center justify-between gap-2 px-1">
              <span className="text-[13px] text-tinta-suave">Tema</span>
              <SeletorTema />
            </div>
          )}
          <div
            className={visualNovo ? "rounded-card border border-borda bg-fundo-poco p-3" : "rounded-2xl border border-acento/25 bg-acento/10 p-3"}
            title="Saldo de tokens disponível para consumo (upload confirmado e mensagens do agente)"
          >
            <div className={`text-[11px] font-semibold uppercase tracking-wider ${visualNovo ? "text-tinta-suave" : "text-acento-claro"}`}>
              {visualNovo ? `Créditos de IA${ilimitado ? " (demonstração)" : ""}` : <>Tokens {ilimitado && "· demo"}</>}
            </div>
            <div className="mt-0.5 flex items-baseline gap-1.5 font-display text-xl font-bold text-tinta-forte">
              {ilimitado && !loading && <span aria-hidden="true">∞</span>}
              {saldo}
            </div>
          </div>

          <div>
            <label htmlFor="meu-cnpj" className="text-xs">
              Meu CNPJ (venda x compra)
            </label>
            <input
              id="meu-cnpj"
              type="text"
              value={userCnpj}
              onChange={(e) => setUserCnpj(e.target.value)}
              className="p-2 text-[13px]"
              title="CNPJ usado para detectar automaticamente se um documento enviado é uma venda ou uma compra"
            />
          </div>

          {userEmail && (
            <div className="flex items-center gap-2.5 rounded-xl border border-borda-sutil bg-veu/[0.03] p-2.5">
              <div className="grid h-8 w-8 place-items-center rounded-full bg-marca text-xs font-bold text-sobre-acento">
                {iniciais(userEmail)}
              </div>
              <div className="min-w-0">
                <div className="truncate text-[13px] font-medium text-tinta-forte">{userEmail}</div>
                <div className="text-[11px] text-tinta-suave">Conta de demonstração</div>
              </div>
            </div>
          )}
        </div>
      </aside>
      <main className="content">{children}</main>
    </div>
  );
}
