import { type DemoUser } from "../types";
import { useAparencia } from "../aparencia/AparenciaContext";
import { SeletorTema } from "../aparencia/SeletorTema";
import { Botao } from "../components/Botao";

type Props = {
  onEnter: (user: DemoUser) => void;
};

const STEPS = [
  {
    icon: "📄",
    title: "Envie uma nota fiscal",
    text: "PDF, imagem ou texto: OCR e IA extraem valor, data e CNPJ automaticamente.",
  },
  {
    icon: "✅",
    title: "Revise os dados",
    text: "Confira e corrija a extração antes de qualquer lançamento no seu limite.",
  },
  {
    icon: "📊",
    title: "Acompanhe o limite",
    text: "Gauge, projeção do ano e mês a mês mostram quanto ainda pode faturar.",
  },
  {
    icon: "💬",
    title: "Converse com o agente",
    text: "Tire dúvidas do MEI com respostas embasadas nas regras e nos seus dados.",
  },
];

// O caminho de quem usa é uma sequência de verdade, então a numeração conta.
const PASSOS_NOVO = [
  { titulo: "Envie a nota", texto: "PDF, foto ou texto. O sistema lê valor, data e CNPJ." },
  { titulo: "Confira os dados", texto: "Nada entra no seu limite antes de você confirmar." },
  { titulo: "Veja quanto ainda cabe", texto: "O painel mostra o que falta até os R$ 81 mil e o seu ritmo no ano." },
];

function LoginNovo({ onEntrar }: { onEntrar: () => void }) {
  return (
    <div className="min-h-screen bg-fundo px-4 py-8 md:px-10">
      <header className="mx-auto flex max-w-6xl items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="marca-logo" aria-hidden="true">
            F
          </div>
          <span className="text-lg font-semibold text-tinta-forte">FluxoFiscal</span>
        </div>
        <SeletorTema />
      </header>

      <main className="mx-auto mt-16 grid max-w-6xl items-start gap-14 md:mt-24 md:grid-cols-[1.25fr_1fr]">
        <div>
          <h1 className="m-0 max-w-[16ch] font-semibold leading-[1.02] text-tinta-forte [font-size:clamp(40px,6vw,76px)] [font-stretch:85%]">
            Saiba quanto ainda pode faturar como MEI.
          </h1>
          <p className="mt-6 max-w-[52ch] text-lg leading-relaxed text-tinta-leve">
            Envie suas notas, acompanhe o limite anual e tire dúvidas sobre o MEI em português
            simples, com base nos seus próprios números.
          </p>
          <Botao className="mt-8 min-h-[52px] px-6 text-base" onClick={onEntrar}>
            Entrar na demonstração
          </Botao>
          <p className="mt-3 text-sm text-tinta-suave">
            Sem senha. A demonstração usa a conta demo@mei.com.
          </p>
        </div>

        <ol className="m-0 list-none rounded-card border border-borda bg-fundo-elevado p-0">
          {PASSOS_NOVO.map((passo, i) => (
            <li key={passo.titulo} className="flex gap-4 border-b border-borda p-6 last:border-b-0">
              <span className="valor text-2xl leading-none text-tinta-suave">{i + 1}</span>
              <div>
                <div className="font-semibold text-tinta-forte">{passo.titulo}</div>
                <div className="mt-1 text-[15px] text-tinta-suave">{passo.texto}</div>
              </div>
            </li>
          ))}
        </ol>
      </main>
    </div>
  );
}

export function LoginPage({ onEnter }: Props) {
  const { visualNovo } = useAparencia();
  const handleEnter = () => {
    onEnter({ name: "Demo User", email: "demo@mei.com" });
  };

  if (visualNovo) return <LoginNovo onEntrar={handleEnter} />;

  return (
    <div className="grid min-h-screen place-items-center bg-fundo-poco bg-login-brilho px-4 py-10">
      <div className="grid w-full max-w-5xl items-center gap-10 md:grid-cols-[1.1fr_1fr]">
        <div>
          <div className="mb-6 flex items-center gap-3">
            <div className="marca-logo" aria-hidden="true">
              F
            </div>
            <span className="font-display text-lg font-bold text-tinta-forte">FluxoFiscal</span>
          </div>
          <div className="pill mb-4">Prova de conceito · TG II</div>
          <h1 className="m-0 text-4xl leading-tight md:text-5xl">
            Seu limite do MEI,{" "}
            <span className="bg-marca bg-clip-text text-transparent">sob controle.</span>
          </h1>
          <p className="muted mt-4 max-w-md text-base">
            Assistente fiscal com IA: lê suas notas, acompanha o faturamento anual e responde suas
            dúvidas em linguagem simples.
          </p>
          <button className="cta mt-7 w-full px-6 py-3.5 text-base md:w-auto" onClick={handleEnter}>
            Entrar na demonstração →
          </button>
          <div className="muted mt-3 text-xs">
            Sem senha. Usamos o e-mail <strong className="text-tinta-leve">demo@mei.com</strong> para
            limites, uploads e chat.
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          {STEPS.map((step) => (
            <div key={step.title} className="card">
              <div className="mb-3 grid h-10 w-10 place-items-center rounded-xl bg-acento/15 text-xl">
                {step.icon}
              </div>
              <div className="mb-1 font-semibold text-tinta-forte">{step.title}</div>
              <div className="muted text-[13px]">{step.text}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
