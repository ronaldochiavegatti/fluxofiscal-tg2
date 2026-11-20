// Helpers compartilhados pelos cenários k6 (US-14).

import http from "k6/http";
import { check } from "k6";

// A URL do gateway. Na CI e no Compose local é http://localhost:8000.
export const BASE = __ENV.BASE_URL || "http://localhost:8000";

// Ano corrente — o resumo anual do MEI é sempre sobre o ano em curso.
export const ANO = new Date().getFullYear();

// Um e-mail por VU, estável entre iterações: o mesmo MEI acumulando
// transações ao longo do teste, como no uso real.
export function emailDoVU() {
  return `carga-vu${__VU}@mei.example`;
}

// Valor de venda plausível para um MEI (R$ 50 a R$ 1.550).
export function valorVenda() {
  return Math.round((50 + Math.random() * 1500) * 100) / 100;
}

export function dataNoAno() {
  const mes = String(1 + Math.floor(Math.random() * 12)).padStart(2, "0");
  const dia = String(1 + Math.floor(Math.random() * 28)).padStart(2, "0");
  return `${ANO}-${mes}-${dia}`;
}

export function lancarVenda(email) {
  const r = http.post(
    `${BASE}/limits/transactions`,
    JSON.stringify({
      email,
      amount: valorVenda(),
      tx_date: dataNoAno(),
      tx_type: "venda",
      source: "carga",
    }),
    { headers: { "Content-Type": "application/json" }, tags: { name: "transactions" } },
  );
  check(r, { "transação criada": (res) => res.status === 200 });
  return r;
}

// A rota mais chamada da plataforma e a do SLO de latência mais rígido.
export function lerResumo(email) {
  const r = http.get(`${BASE}/limits/summary/${email}`, {
    tags: { name: "summary" },
  });
  check(r, {
    "resumo 200": (res) => res.status === 200,
    "resumo tem faturamento": (res) =>
      res.status === 200 && res.body != null && res.json("total_revenue") !== undefined,
  });
  return r;
}

export function listarTransacoes(email) {
  const r = http.get(`${BASE}/limits/transactions?email=${email}&year=${ANO}`, {
    tags: { name: "list" },
  });
  check(r, { "lista 200": (res) => res.status === 200 });
  return r;
}
