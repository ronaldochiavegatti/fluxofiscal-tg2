// US-14 — Perfil realista de uso de MEI.
//
// Critério de aceite:
//   Dado 50 usuários simultâneos por 10 minutos
//   Então o p95 de /limits/summary fica abaixo de 300 ms
//   E a taxa de erro fica abaixo de 1%
//
// Os alvos vêm de docs/observabilidade/slos.yaml (resumo-anual-rapido,
// gateway-disponivel). As `thresholds` abaixo são a versão executável deles:
// se o cenário violar, o k6 sai com código != 0 e a CI reprova.
//
// Parametrizável por env para a CI rodar um smoke curto no PR:
//   VUS=10 DURACAO=60s   -> ~1 min, valida que o caminho funciona
//   (sem env)            -> 50 VUs, 10 min, o número que vai no artigo

import { sleep } from "k6";
import { Trend } from "k6/metrics";
import { textSummary } from "https://jslib.k6.io/k6-summary/0.1.0/index.js";
import { BASE, emailDoVU, lancarVenda, lerResumo, listarTransacoes } from "./lib/comum.js";

const VUS = Number(__ENV.VUS || 50);
const DURACAO = __ENV.DURACAO || "10m";

export const options = {
  scenarios: {
    mei: {
      executor: "constant-vus",
      vus: VUS,
      duration: DURACAO,
      gracefulStop: "10s",
    },
  },
  thresholds: {
    // SLO resumo-anual-rapido: p95 < 300 ms, p99 < 800 ms.
    "http_req_duration{name:summary}": ["p(95)<300", "p(99)<800"],
    // SLO gateway-disponivel: 99,5% -> taxa de erro < 0,5%. Margem para 1%
    // conforme o critério de aceite da US-14.
    http_req_failed: ["rate<0.01"],
    checks: ["rate>0.99"],
  },
  // p(99) precisa ser pedido explicitamente para aparecer no resumo.
  summaryTrendStats: ["avg", "min", "med", "max", "p(90)", "p(95)", "p(99)"],
};

const resumoTrend = new Trend("resumo_ms", true);

// Cada VU planta algumas transações antes do teste medir leitura, para o
// resumo não ser sempre sobre uma base vazia.
export function setup() {
  return { base: BASE };
}

export default function () {
  const email = emailDoVU();

  // Mistura realista: MEI lê o dashboard muito mais do que lança nota.
  const dado = Math.random();
  if (dado < 0.15) {
    lancarVenda(email);
  }

  const r = lerResumo(email);
  resumoTrend.add(r.timings.duration);

  if (dado > 0.7) {
    listarTransacoes(email);
  }

  sleep(1 + Math.random() * 2);
}

export function handleSummary(data) {
  const p95 = data.metrics["http_req_duration{name:summary}"]?.values["p(95)"] ?? null;
  const erro = data.metrics.http_req_failed?.values.rate ?? null;
  const resumo = {
    cenario: "perfil-mei",
    vus: VUS,
    duracao: DURACAO,
    summary_p95_ms: p95,
    summary_p99_ms: data.metrics["http_req_duration{name:summary}"]?.values["p(99)"] ?? null,
    taxa_erro: erro,
    iteracoes: data.metrics.iterations?.values.count ?? null,
    req_por_s: data.metrics.http_reqs?.values.rate ?? null,
    aprovado: p95 !== null && p95 < 300 && erro !== null && erro < 0.01,
  };
  return {
    stdout: textSummary(data, { indent: " ", enableColors: false }),
    "resultados/perfil-mei.json": JSON.stringify(resumo, null, 2),
  };
}
