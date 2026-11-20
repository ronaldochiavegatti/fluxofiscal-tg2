import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach } from "vitest";
import { cleanup } from "@testing-library/react";

// Cada teste começa com o DOM e o localStorage limpos. Sem isso, o
// useLocalStorage de um teste vaza para o seguinte e a suíte passa a depender
// da ordem de execução — que é o defeito mais difícil de diagnosticar numa
// suíte de testes.
beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  localStorage.clear();
});
