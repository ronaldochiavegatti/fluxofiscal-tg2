// US-14 — Teste de estresse: encontrar o ponto de saturação.
//
// Critério de aceite:
//   Dado o cenário de estresse com carga crescente
//   Então o relatório indica em qual carga o SLO passa a ser violado
//
// A carga sobe em degraus. Cada requisição de leitura leva a tag `degrau`
// com o alvo de VUs vigente; cada degrau tem um threshold próprio
// (`abortOnFail: false`, para não parar no primeiro que falha). O
// `handleSummary` varre os degraus e reporta o primeiro em que o p95 de
// /limits/summary cruza 300 ms — o ponto de saturação.
//
// Parametrizável: PICO define o topo (padrão 200 VUs). Na CI do PR roda um
// recorte curto (PICO=40, PASSO=20s) só para exercitar o caminho.

import exec from "k6/execution";
import http from "k6/http";
import { check, sleep } from "k6";
import { textSummary } from "https://jslib.k6.io/k6-summary/0.1.0/index.js";
import { BASE, emailDoVU, lancarVenda } from "./lib/comum.js";

const PICO = Number(__ENV.PICO || 200);
const PASSO = __ENV.PASSO || "1m";
const SLO_P95_MS = 300;

// Degraus de 10% do pico até 100%.
const NIVEIS = [];
for (let i = 1; i <= 10; i++) {
  NIVEIS.push(Math.max(1, Math.round((PICO * i) / 10)));
}

const stages = [];
for (const vus of NIVEIS) {
  stages.push({ duration: "10s", target: vus });
  stages.push({ duration: PASSO, target: vus });
}

const thresholds = { http_req_failed: ["rate<0.05"] };
for (const vus of NIVEIS) {
  thresholds[`http_req_duration{degrau:${vus}}`] = [
    { threshold: `p(95)<${SLO_P95_MS}`, abortOnFail: false },
  ];
}

export const options = {
  scenarios: {
    estresse: { executor: "ramping-vus", startVUs: 1, stages, gracefulStop: "10s" },
  },
  thresholds,
};

function degrauAtual() {
  const ativos = exec.instance.vusActive;
  return NIVEIS.reduce((a, b) => (Math.abs(b - ativos) <= Math.abs(a - ativos) ? b : a));
}

export default function () {
  const email = emailDoVU();
  if (Math.random() < 0.15) lancarVenda(email);

  const r = http.get(`${BASE}/limits/summary/${email}`, {
    tags: { name: "summary", degrau: String(degrauAtual()) },
  });
  check(r, { "resumo 200": (res) => res.status === 200 });

  sleep(1);
}

export function handleSummary(data) {
  const degraus = NIVEIS.map((vus) => {
    const m = data.metrics[`http_req_duration{degrau:${vus}}`];
    const p95 = m ? m.values["p(95)"] : null;
    return { vus, p95_ms: p95, violou_slo: p95 === null ? null : p95 >= SLO_P95_MS };
  });
  const saturacao = degraus.find((d) => d.violou_slo === true);
  const resultado = {
    cenario: "estresse",
    pico_vus: PICO,
    slo_p95_ms: SLO_P95_MS,
    degraus,
    ponto_de_saturacao_vus: saturacao ? saturacao.vus : null,
    observacao: saturacao
      ? `p95 de /limits/summary cruzou ${SLO_P95_MS} ms a partir de ${saturacao.vus} VUs`
      : `SLO mantido até o pico de ${PICO} VUs`,
  };
  return {
    stdout: textSummary(data, { indent: " ", enableColors: false }),
    "resultados/estresse.json": JSON.stringify(resultado, null, 2),
  };
}
