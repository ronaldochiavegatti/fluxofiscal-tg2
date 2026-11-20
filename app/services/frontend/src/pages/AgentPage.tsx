import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import { chatAgent } from "../api";
import { Markdown } from "../components/Markdown";
import { useLocalStorage } from "../hooks/useLocalStorage";
import { useTokens } from "../TokensContext";
import type { ChatMessage, DemoUser } from "../types";
import { useAparencia } from "../aparencia/AparenciaContext";
import { Botao } from "../components/Botao";
import { CabecalhoPagina, formatarDuracao, useSegundos } from "../components/interacao";

type Props = {
  user: DemoUser;
};

/** Chave do histórico no navegador — o reset de dados de teste também a apaga. */
export const CHAVE_HISTORICO_CHAT = "chat-historico";

const BOAS_VINDAS: ChatMessage = {
  from: "agent",
  text:
    "Olá! Sou seu **agente contábil**. Respondo com base nas regras do MEI e nos seus " +
    "lançamentos — pergunte sobre limite anual, DAS, declaração ou suas notas.",
  at: "",
};

const SUGESTOES = [
  "Quanto ainda posso faturar este ano?",
  "Compras entram no limite do MEI?",
  "O que acontece se eu passar do teto?",
  "Para que serve o DAS?",
];

function hora(iso: string) {
  return iso ? new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : "";
}

export function AgentPage({ user }: Props) {
  const [messages, setMessages] = useLocalStorage<ChatMessage[]>(CHAVE_HISTORICO_CHAT, [BOAS_VINDAS]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const { balance, ilimitado, costs, consume } = useTokens();
  const messageCost = costs.chat_message ?? 5;
  const insufficientBalance = !ilimitado && balance !== null && balance < messageCost;
  const fimRef = useRef<HTMLDivElement>(null);
  const { visualNovo } = useAparencia();
  const segundos = useSegundos(loading);
  // Pergunta que falhou, para oferecer "Tentar de novo" sem redigitar.
  const [perguntaComFalha, setPerguntaComFalha] = useState<string | null>(null);

  useEffect(() => {
    fimRef.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [messages, loading]);

  const enviar = async (texto: string) => {
    const pergunta = texto.trim();
    if (!pergunta || loading || insufficientBalance) return;
    setMessages((prev) => [...prev, { from: "user", text: pergunta, at: new Date().toISOString() }]);
    setInput("");
    setPerguntaComFalha(null);
    setLoading(true);
    try {
      const { reply, sources } = await chatAgent(user.email, pergunta);
      setMessages((prev) => [
        ...prev,
        {
          from: "agent",
          text: reply || "Recebi sua pergunta, mas não consegui gerar resposta agora.",
          at: new Date().toISOString(),
          sources,
        },
      ]);
      await consume("chat_message");
    } catch (err) {
      setPerguntaComFalha(pergunta);
      setMessages((prev) => [
        ...prev,
        {
          from: "agent",
          text: visualNovo
            ? `Não consegui responder agora (${(err as Error).message}). Sua pergunta não foi cobrada.`
            : `Erro ao chamar a IA: ${(err as Error).message}`,
          at: new Date().toISOString(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    enviar(input);
  };

  // Enter envia; Shift+Enter quebra a linha.
  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      enviar(input);
    }
  };

  const conversaVazia = messages.length <= 1;

  return (
    <div
      className={
        visualNovo
          ? // Altura da janela menos o espaço do conteúdo (e da barra do topo
            // abaixo de 1024 px), para a caixa de mensagem ficar sempre à vista.
            "flex h-[calc(100dvh-6rem)] min-h-[440px] flex-col max-lg:h-[calc(100dvh-9rem)] max-sm:h-[calc(100dvh-8rem)]"
          : "flex h-[calc(100vh-80px)] min-h-[520px] flex-col"
      }
    >
      {visualNovo ? (
        <CabecalhoPagina
          titulo="Perguntar ao agente"
          descricao="Respostas com base nas regras do MEI e nos seus lançamentos. Confira decisões importantes com um contador."
          acoes={
            !conversaVazia && (
              <Botao variante="secundario" tamanho="sm" onClick={() => setMessages([BOAS_VINDAS])} disabled={loading}>
                Nova conversa
              </Botao>
            )
          }
        />
      ) : (
      <div className="page-header">
        <div>
          <div className="pill">Agente contábil · Gemini + RAG</div>
          <h2 className="title mt-1.5">Converse com a IA</h2>
          <div className="muted">Respostas baseadas nas regras do MEI e nos seus lançamentos.</div>
        </div>
        {!conversaVazia && (
          <button
            type="button"
            className="pill cursor-pointer hover:border-borda-forte"
            onClick={() => setMessages([BOAS_VINDAS])}
            disabled={loading}
          >
            Nova conversa
          </button>
        )}
      </div>
      )}

      <div className={`${visualNovo ? "painel painel-lista mt-6" : "card mt-4 p-0"} flex min-h-0 flex-1 flex-col`}>
        <div className="flex-1 space-y-5 overflow-y-auto p-5" aria-live="polite">
          {messages.map((msg, idx) =>
            msg.from === "user" ? (
              <div key={idx} className="flex justify-end">
                <div className="chat-bubble me">
                  <div className="whitespace-pre-wrap">{msg.text}</div>
                  <div className="mt-1 text-right text-[11px] text-tinta-suave">{hora(msg.at)}</div>
                </div>
              </div>
            ) : (
              <div key={idx} className="flex items-start gap-3">
                <div className="marca-logo h-8 w-8 shrink-0 text-sm" aria-hidden="true">
                  F
                </div>
                <div className="min-w-0 max-w-[720px] flex-1">
                  <div className="mb-1 flex items-baseline gap-2 text-xs text-tinta-suave">
                    <span className="font-semibold text-tinta-leve">Agente</span>
                    {hora(msg.at)}
                  </div>
                  <div className="chat-bubble max-w-none">
                    <Markdown texto={msg.text} />
                  </div>
                  {msg.sources && msg.sources.length > 0 && (
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      <span className="text-[11px] font-semibold uppercase tracking-wider text-tinta-suave">
                        Fontes
                      </span>
                      {msg.sources.map((fonte) => (
                        <span key={fonte} className="badge" title={fonte}>
                          {!visualNovo && "📚 "}
                          {fonte}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ),
          )}

          {perguntaComFalha && !loading && visualNovo && (
            <div className="pl-11">
              <Botao variante="secundario" tamanho="sm" onClick={() => enviar(perguntaComFalha)}>
                Tentar de novo
              </Botao>
            </div>
          )}

          {loading && visualNovo && (
            <div className="flex items-center gap-3" role="status">
              <div className="marca-logo h-8 w-8 shrink-0 text-sm" aria-hidden="true">
                F
              </div>
              <div className="chat-bubble flex items-center gap-3 py-3">
                <span className="digitando flex gap-1" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                </span>
                <span className="text-sm text-tinta-suave">
                  {segundos < 8 ? "Pensando" : "Consultando seus números e as regras"}
                  <span className="tabular-nums"> · {formatarDuracao(segundos)}</span>
                </span>
              </div>
            </div>
          )}

          {loading && !visualNovo && (
            <div className="flex items-center gap-3" role="status" aria-label="Agente digitando">
              <div className="marca-logo h-8 w-8 shrink-0 text-sm" aria-hidden="true">
                F
              </div>
              <div className="chat-bubble flex gap-1.5 py-4">
                {[0, 150, 300].map((atraso) => (
                  <span
                    key={atraso}
                    className="h-2 w-2 animate-bounce rounded-full bg-acento"
                    style={{ animationDelay: `${atraso}ms` }}
                  />
                ))}
              </div>
            </div>
          )}

          {conversaVazia && !loading && (
            <div className="flex flex-wrap gap-2 pl-11">
              {visualNovo && <p className="m-0 w-full text-sm text-tinta-suave">Comece por uma destas:</p>}
              {SUGESTOES.map((sugestao) =>
                visualNovo ? (
                  <Botao key={sugestao} variante="secundario" tamanho="sm" onClick={() => enviar(sugestao)}>
                    {sugestao}
                  </Botao>
                ) : (
                <button
                  key={sugestao}
                  type="button"
                  className="pill cursor-pointer transition-colors hover:border-acento/50 hover:bg-acento/10"
                  onClick={() => enviar(sugestao)}
                >
                  {sugestao}
                </button>
                )
              )}
            </div>
          )}
          <div ref={fimRef} />
        </div>

        <form onSubmit={handleSubmit} className="border-t border-borda p-4">
          <div className="flex items-end gap-2.5">
            <textarea
              rows={1}
              aria-label="Sua mensagem"
              className="max-h-40 min-h-[48px] resize-none"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                visualNovo
                  ? "Escreva sua pergunta. Enter envia, Shift+Enter quebra a linha."
                  : "Pergunte algo ao agente... (Enter envia, Shift+Enter quebra linha)"
              }
            />
            {visualNovo ? (
              <Botao type="submit" className="h-12 shrink-0" carregando={loading} disabled={insufficientBalance || !input.trim()}>
                Enviar
              </Botao>
            ) : (
            <button className="cta h-12 shrink-0" disabled={loading || insufficientBalance || !input.trim()}>
              {loading ? "Pensando..." : "Enviar ↵"}
            </button>
            )}
          </div>
          <div className="mt-1.5 text-xs text-tinta-suave">
            {visualNovo
              ? ilimitado
                ? "Perguntar não gasta créditos na demonstração."
                : `Cada pergunta usa ${messageCost} créditos (saldo ${balance ?? "—"}).`
              : ilimitado
                ? "Demo: tokens ilimitados."
                : `Cada mensagem consome ${messageCost} tokens (saldo: ${balance ?? "—"}).`}
            {insufficientBalance && <span className="text-limite-estourado"> Saldo insuficiente.</span>}
          </div>
        </form>
      </div>
    </div>
  );
}
