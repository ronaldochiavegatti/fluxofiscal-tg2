import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { ErroConfiguracao, getConfiguracao, restaurarConfiguracao, salvarConfiguracao } from "../api";
import { useAvisos } from "../components/Avisos";
import { Botao } from "../components/Botao";
import { CabecalhoPagina } from "../components/interacao";
import { formatBRL } from "../format";
import type { AtualizacaoConfiguracao, ConfiguracaoFiscal, DemoUser, NomeParametro, ParametrosFiscais } from "../types";

/**
 * Configurações das regras e metas do painel (#91). A tela só edita e exibe:
 * a validação e o uso dos valores são do serviço `limits` (domínio fiscal),
 * que devolve a mensagem de erro de cada campo.
 */

type Unidade = "reais" | "percentual" | "acima_do_limite" | "dias" | "quantidade";
type Grupo = "regras" | "metas" | "projecao";
type CampoNumerico = Exclude<NomeParametro, "limite_proporcional">;

type Campo = {
  nome: CampoNumerico;
  grupo: Grupo;
  rotulo: string;
  ajuda: string;
  unidade: Unidade;
  /** Pode ficar em branco (usa o cálculo automático). */
  opcional?: string;
};

const CAMPOS: Campo[] = [
  {
    nome: "limite_anual",
    grupo: "regras",
    rotulo: "Limite anual de faturamento",
    unidade: "reais",
    ajuda: "Teto de vendas do MEI no ano. Atualize quando a lei mudar.",
  },
  {
    nome: "margem_desenquadramento",
    grupo: "regras",
    rotulo: "Tolerância antes do desenquadramento retroativo",
    unidade: "acima_do_limite",
    ajuda: "Até quanto acima do limite o desenquadramento vale só a partir do ano seguinte.",
  },
  {
    nome: "limiar_alerta",
    grupo: "metas",
    rotulo: "Avisar a partir de",
    unidade: "percentual",
    ajuda: "Parte do limite em que o painel e o agente começam a alertar.",
  },
  {
    nome: "meta_mensal",
    grupo: "metas",
    rotulo: "Meta de vendas por mês",
    unidade: "reais",
    opcional: "Em branco: o limite do ano dividido por 12.",
    ajuda: "Linha de meta do gráfico mês a mês.",
  },
  {
    nome: "limiar_concentracao_cliente",
    grupo: "metas",
    rotulo: "Alertar quando um só cliente passar de",
    unidade: "percentual",
    ajuda: "Parte das suas vendas vinda de um mesmo CNPJ.",
  },
  {
    nome: "dias_minimos_para_projetar",
    grupo: "projecao",
    rotulo: "Dias mínimos para projetar o ano",
    unidade: "dias",
    ajuda: "Antes disso, o painel não estima onde o ano vai terminar.",
  },
  {
    nome: "transacoes_minimas_para_projetar",
    grupo: "projecao",
    rotulo: "Vendas mínimas para projetar o ano",
    unidade: "quantidade",
    ajuda: "Com menos vendas que isso, a projeção não aparece.",
  },
  {
    nome: "dias_abertura_recente",
    grupo: "projecao",
    rotulo: "MEI aberto há menos de",
    unidade: "dias",
    ajuda: "Nesse período, o ritmo conta os dias desde a abertura, não desde 1º de janeiro.",
  },
  {
    nome: "limiar_lancamento_atipico",
    grupo: "projecao",
    rotulo: "Venda atípica acima de",
    unidade: "percentual",
    ajuda: "Uma venda que sozinha passa disso do faturamento do ano é sinalizada na projeção.",
  },
  {
    nome: "limiar_atencao_ritmo_realizado",
    grupo: "projecao",
    rotulo: "Atenção por ritmo só com faturamento abaixo de",
    unidade: "percentual",
    ajuda: "Ritmo alto com pouco faturado gera um aviso mais brando, abaixo desta parte do limite.",
  },
];

const SUFIXO: Record<Unidade, string> = {
  reais: "R$",
  percentual: "%",
  acima_do_limite: "% acima",
  dias: "dias",
  quantidade: "vendas",
};

/** Valor da API -> texto do campo (frações viram percentual). */
function paraTela(unidade: Unidade, valor: number | null): string {
  if (valor === null) return "";
  if (unidade === "percentual") return String(Number((valor * 100).toFixed(2)));
  if (unidade === "acima_do_limite") return String(Number(((valor - 1) * 100).toFixed(2)));
  return String(valor);
}

/** Texto do campo -> valor da API. `null` = campo opcional em branco. */
function paraApi(unidade: Unidade, texto: string): number | null {
  if (texto.trim() === "") return null;
  const numero = Number(texto.replace(",", "."));
  if (unidade === "percentual") return Number((numero / 100).toFixed(4));
  if (unidade === "acima_do_limite") return Number((1 + numero / 100).toFixed(4));
  return numero;
}

function textoPadrao(campo: Campo, padrao: ParametrosFiscais): string {
  const valor = padrao[campo.nome];
  if (valor === null) return campo.opcional ? "automático" : "—";
  if (campo.unidade === "reais") return formatBRL(valor);
  return `${paraTela(campo.unidade, valor)} ${SUFIXO[campo.unidade]}`;
}

type Rascunho = {
  campos: Record<CampoNumerico, string>;
  proporcional: boolean;
  dataAbertura: string;
};

function rascunhoDe(config: ConfiguracaoFiscal): Rascunho {
  const campos = {} as Record<CampoNumerico, string>;
  for (const campo of CAMPOS) campos[campo.nome] = paraTela(campo.unidade, config.parametros[campo.nome]);
  return {
    campos,
    proporcional: config.parametros.limite_proporcional,
    dataAbertura: config.data_abertura ?? "",
  };
}

/** Campo citado na mensagem de erro do domínio ("limiar_alerta deve estar entre..."). */
function campoDoErro(mensagem: string): CampoNumerico | null {
  return CAMPOS.find((campo) => mensagem.includes(campo.nome))?.nome ?? null;
}

export function ConfiguracoesPage({ user }: { user: DemoUser }) {
  const avisar = useAvisos();
  const [config, setConfig] = useState<ConfiguracaoFiscal | null>(null);
  const [rascunho, setRascunho] = useState<Rascunho | null>(null);
  const [erroCarga, setErroCarga] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [restaurando, setRestaurando] = useState(false);
  const [confirmarRestaurar, setConfirmarRestaurar] = useState(false);
  const [erroCampo, setErroCampo] = useState<{ campo: CampoNumerico | null; mensagem: string } | null>(null);

  const carregar = useCallback(async () => {
    setErroCarga(null);
    try {
      const atual = await getConfiguracao(user.email);
      setConfig(atual);
      setRascunho(rascunhoDe(atual));
    } catch (erro) {
      setErroCarga((erro as Error).message);
    }
  }, [user.email]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  const original = useMemo(() => (config ? rascunhoDe(config) : null), [config]);

  const mudancas = useMemo((): AtualizacaoConfiguracao | null => {
    if (!rascunho || !original) return null;
    const parametros: AtualizacaoConfiguracao["parametros"] = {};
    for (const campo of CAMPOS) {
      if (rascunho.campos[campo.nome] !== original.campos[campo.nome]) {
        parametros[campo.nome] = paraApi(campo.unidade, rascunho.campos[campo.nome]);
      }
    }
    if (rascunho.proporcional !== original.proporcional) parametros.limite_proporcional = rascunho.proporcional;
    const corpo: AtualizacaoConfiguracao = { parametros };
    if (rascunho.dataAbertura !== original.dataAbertura) corpo.data_abertura = rascunho.dataAbertura || null;
    const vazio = Object.keys(parametros).length === 0 && !("data_abertura" in corpo);
    return vazio ? null : corpo;
  }, [rascunho, original]);

  const salvar = async () => {
    if (!mudancas) return;
    // Campo obrigatório em branco não vai ao servidor: o erro aparece no próprio campo.
    const vazio = CAMPOS.find((campo) => !campo.opcional && rascunho?.campos[campo.nome].trim() === "");
    if (vazio) {
      setErroCampo({ campo: vazio.nome, mensagem: "Preencha este campo ou volte ao padrão." });
      return;
    }
    setSalvando(true);
    setErroCampo(null);
    try {
      const atual = await salvarConfiguracao(user.email, mudancas);
      setConfig(atual);
      setRascunho(rascunhoDe(atual));
      avisar("sucesso", "Configurações salvas. O painel já usa os novos valores.");
    } catch (erro) {
      const mensagem = erro instanceof ErroConfiguracao ? erro.message : "Não foi possível salvar. Tente de novo.";
      setErroCampo({ campo: campoDoErro(mensagem), mensagem });
    } finally {
      setSalvando(false);
    }
  };

  const restaurarTudo = async () => {
    setRestaurando(true);
    setErroCampo(null);
    try {
      const atual = await restaurarConfiguracao(user.email);
      setConfig(atual);
      setRascunho(rascunhoDe(atual));
      setConfirmarRestaurar(false);
      avisar("sucesso", "Tudo voltou aos valores padrão.");
    } catch {
      setErroCampo({ campo: null, mensagem: "Não foi possível restaurar agora. Tente de novo." });
    } finally {
      setRestaurando(false);
    }
  };

  const mudarCampo = (nome: CampoNumerico, valor: string) => {
    setRascunho((atual) => (atual ? { ...atual, campos: { ...atual.campos, [nome]: valor } } : atual));
    if (erroCampo?.campo === nome) setErroCampo(null);
  };

  if (erroCarga) {
    return (
      <div>
        <CabecalhoPagina titulo="Configurações" />
        <div className="painel mt-6" role="alert">
          <p className="m-0 text-limite-estourado">Não foi possível carregar suas configurações: {erroCarga}</p>
          <Botao variante="secundario" className="mt-4" onClick={() => void carregar()}>
            Tentar de novo
          </Botao>
        </div>
      </div>
    );
  }

  if (!config || !rascunho) {
    return (
      <div aria-busy="true">
        <CabecalhoPagina titulo="Configurações" descricao="Carregando suas configurações…" />
        <div className="painel mt-6 space-y-4">
          {[0, 1, 2, 3].map((n) => (
            <div key={n} className="esqueleto h-14" />
          ))}
        </div>
      </div>
    );
  }

  const renderCampo = (campo: Campo) => {
    const valor = rascunho.campos[campo.nome];
    const padraoTela = paraTela(campo.unidade, config.padrao[campo.nome]);
    const difereDoPadrao = valor !== padraoTela;
    const erro = erroCampo?.campo === campo.nome ? erroCampo.mensagem : null;
    const idAjuda = `ajuda-${campo.nome}`;
    const idErro = `erro-${campo.nome}`;
    return (
      <div key={campo.nome} className="campo-config">
        <label htmlFor={`campo-${campo.nome}`}>
          {campo.rotulo}
          {difereDoPadrao && <span className="campo-origem campo-origem-falta">personalizado</span>}
        </label>
        <div className="campo-com-unidade">
          {campo.unidade === "reais" && <span className="campo-unidade campo-unidade-antes">R$</span>}
          <input
            id={`campo-${campo.nome}`}
            type="number"
            inputMode="decimal"
            step={campo.unidade === "reais" ? "0.01" : campo.unidade === "dias" || campo.unidade === "quantidade" ? "1" : "0.1"}
            min="0"
            value={valor}
            placeholder={campo.opcional ? "automático" : undefined}
            onChange={(e) => mudarCampo(campo.nome, e.target.value)}
            aria-invalid={erro ? true : undefined}
            aria-describedby={erro ? `${idErro} ${idAjuda}` : idAjuda}
          />
          {campo.unidade !== "reais" && <span className="campo-unidade">{SUFIXO[campo.unidade]}</span>}
        </div>
        {erro && (
          <p id={idErro} className="m-0 mt-1.5 text-sm text-limite-estourado" role="alert">
            {erro}
          </p>
        )}
        <p id={idAjuda} className="m-0 mt-1.5 text-sm text-tinta-suave">
          {campo.ajuda} {campo.opcional}
        </p>
        <p className="m-0 mt-1 flex flex-wrap items-center gap-x-2 text-sm text-tinta-suave">
          Padrão: {textoPadrao(campo, config.padrao)}
          {difereDoPadrao && (
            <Botao variante="discreto" tamanho="sm" className="-my-1" onClick={() => mudarCampo(campo.nome, padraoTela)}>
              Voltar ao padrão
            </Botao>
          )}
        </p>
      </div>
    );
  };

  const secao = (titulo: string, descricao: string, conteudo: ReactNode) => (
    <section className="painel mt-6" aria-labelledby={`secao-${titulo}`}>
      <h2 id={`secao-${titulo}`} className="m-0 text-lg font-semibold text-tinta-forte">
        {titulo}
      </h2>
      <p className="mb-0 mt-1 text-tinta-suave">{descricao}</p>
      <div className="mt-6 grid gap-x-8 gap-y-6 md:grid-cols-2">{conteudo}</div>
    </section>
  );

  return (
    <div className="pb-24">
      <CabecalhoPagina
        titulo="Configurações"
        descricao="Ajuste as regras do MEI e as suas metas. O painel, o relatório e o agente passam a usar estes valores."
      />

      {!config.ativa && (
        <p className="painel mt-6 border-limite-atencao-borda text-tinta-leve" role="status">
          As configurações são salvas, mas o servidor ainda está usando os valores padrão: a função de
          métricas configuráveis está desligada.
        </p>
      )}

      {secao(
        "Regras do MEI",
        "Valores definidos pela legislação. Mude quando a lei mudar; o sistema não atualiza sozinho.",
        <>
          {CAMPOS.filter((c) => c.grupo === "regras").map(renderCampo)}
          <div className="campo-config">
            <label htmlFor="campo-data-abertura">Data de abertura do MEI</label>
            <input
              id="campo-data-abertura"
              type="date"
              value={rascunho.dataAbertura}
              onChange={(e) => setRascunho({ ...rascunho, dataAbertura: e.target.value })}
              aria-describedby="ajuda-data-abertura"
            />
            <p id="ajuda-data-abertura" className="m-0 mt-1.5 text-sm text-tinta-suave">
              No ano em que o MEI foi aberto, o limite pode ser proporcional aos meses de atividade. Em branco:
              aberto antes deste ano.
            </p>
          </div>
          <div className="campo-config">
            <span className="mb-1.5 block font-semibold text-tinta-leve">Limite proporcional no ano de abertura</span>
            <label className="interruptor">
              <input
                type="checkbox"
                role="switch"
                checked={rascunho.proporcional}
                onChange={(e) => setRascunho({ ...rascunho, proporcional: e.target.checked })}
              />
              <span>{rascunho.proporcional ? "Ligado: limite ÷ 12 × meses de atividade" : "Desligado: limite cheio"}</span>
            </label>
            <p className="m-0 mt-1 text-sm text-tinta-suave">
              Padrão: {config.padrao.limite_proporcional ? "ligado" : "desligado"}
            </p>
          </div>
        </>
      )}

      {secao(
        "Metas e alertas",
        "Escolhas suas: a partir de quando avisar e quanto você quer vender.",
        CAMPOS.filter((c) => c.grupo === "metas").map(renderCampo)
      )}

      <details className="painel mt-6">
        <summary className="cursor-pointer text-lg font-semibold text-tinta-forte">Projeção do ritmo (avançado)</summary>
        <p className="mb-0 mt-1 text-tinta-suave">
          Quando o painel tem dados suficientes para estimar o ano e quando sinaliza algo fora do padrão.
        </p>
        <div className="mt-6 grid gap-x-8 gap-y-6 md:grid-cols-2">
          {CAMPOS.filter((c) => c.grupo === "projecao").map(renderCampo)}
        </div>
      </details>

      {erroCampo && erroCampo.campo === null && (
        <p className="mt-4 text-limite-estourado" role="alert">
          {erroCampo.mensagem}
        </p>
      )}

      <div className="barra-salvar">
        <span className="text-sm text-tinta-suave" aria-live="polite">
          {mudancas ? "Há mudanças não salvas." : "Tudo salvo."}
        </span>
        <div className="flex flex-wrap gap-2.5">
          {confirmarRestaurar ? (
            <>
              <Botao variante="perigo" onClick={() => void restaurarTudo()} carregando={restaurando}>
                {restaurando ? "Restaurando" : "Sim, voltar tudo ao padrão"}
              </Botao>
              <Botao variante="secundario" onClick={() => setConfirmarRestaurar(false)} disabled={restaurando}>
                Cancelar
              </Botao>
            </>
          ) : (
            <Botao variante="secundario" onClick={() => setConfirmarRestaurar(true)} disabled={salvando}>
              Restaurar padrões
            </Botao>
          )}
          <Botao onClick={() => void salvar()} carregando={salvando} disabled={!mudancas || restaurando}>
            {salvando ? "Salvando" : "Salvar configurações"}
          </Botao>
        </div>
      </div>
    </div>
  );
}
