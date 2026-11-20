import { describe, expect, it } from "vitest";

import {
  formatBRL,
  formatBRLInteiro,
  formatDataHoraBr,
  formatIsoDateBr,
  formatNumeroBr,
  formatPercentual,
  todayIso,
} from "./format";

// O Intl insere um espaço não separável (U+00A0) entre "R$" e o número.
// Comparar com um espaço comum falha, e o erro resultante é confuso porque as
// duas strings parecem idênticas no relatório.
const NBSP = " ";

describe("formatBRL", () => {
  it("formata no padrão brasileiro", () => {
    expect(formatBRL(47304.5)).toBe(`R$${NBSP}47.304,50`);
  });

  it("sempre mostra duas casas decimais", () => {
    // Este era o defeito: o limite anual renderizava como "81.000" enquanto
    // os demais valores da mesma tela mostravam centavos.
    expect(formatBRL(81000)).toBe(`R$${NBSP}81.000,00`);
  });

  it.each([
    [0, `R$${NBSP}0,00`],
    [0.05, `R$${NBSP}0,05`],
    [1234.56, `R$${NBSP}1.234,56`],
    [1000000, `R$${NBSP}1.000.000,00`],
  ])("formata %s como %s", (entrada, esperado) => {
    expect(formatBRL(entrada)).toBe(esperado);
  });

  it("formata valor negativo, que acontece quando as compras superam as vendas", () => {
    expect(formatBRL(-15000)).toBe(`-R$${NBSP}15.000,00`);
  });

  it("arredonda para duas casas, meio para cima", () => {
    expect(formatBRL(1.004)).toBe(`R$${NBSP}1,00`);
    expect(formatBRL(1.006)).toBe(`R$${NBSP}1,01`);
  });

  it("arredonda 1,005 para cima, apesar do float", () => {
    // Vale registrar: 1.005 em float64 é 1.00499999999999989, então o
    // arredondamento matematicamente correto seria 1,00. O Intl arredonda pela
    // representação decimal curta e devolve 1,01 — que coincide com o que o
    // backend produz, porque lá o valor é Decimal("1.005") com ROUND_HALF_UP.
    //
    // Os dois concordam aqui, mas por caminhos diferentes. É a razão de a
    // formatação ser só exibição: o valor que vale é sempre o que o serviço
    // de limites calculou, nunca o que o navegador arredondou.
    expect(formatBRL(1.005)).toBe(`R$${NBSP}1,01`);
  });

  it.each([NaN, Infinity, -Infinity])("devolve travessão para %s", (entrada) => {
    expect(formatBRL(entrada)).toBe("—");
  });
});

describe("formatBRLInteiro", () => {
  it("arredonda para reais inteiros", () => {
    expect(formatBRLInteiro(42310.7)).toBe("R$ 42.311");
  });

  it("devolve travessão para valor não finito", () => {
    expect(formatBRLInteiro(Number.NaN)).toBe("—");
  });
});

describe("formatNumeroBr", () => {
  it("formata sem símbolo de moeda", () => {
    expect(formatNumeroBr(47304.5)).toBe("47.304,50");
  });

  it("devolve travessão para valor não finito", () => {
    expect(formatNumeroBr(NaN)).toBe("—");
  });
});

describe("formatPercentual", () => {
  it("usa vírgula como separador decimal", () => {
    expect(formatPercentual(58.4)).toBe("58,4%");
  });

  it("aceita número de casas configurável", () => {
    expect(formatPercentual(6.172839, 2)).toBe("6,17%");
    expect(formatPercentual(6.172839, 0)).toBe("6%");
  });

  it("devolve travessão para valor não finito", () => {
    expect(formatPercentual(NaN)).toBe("—");
  });
});

describe("formatIsoDateBr", () => {
  it("converte ISO para o formato brasileiro", () => {
    expect(formatIsoDateBr("2026-08-25")).toBe("25/08/2026");
  });

  it("não desloca a data por causa de fuso horário", () => {
    // Passar "2026-01-01" para new Date() assume UTC. Num fuso negativo como
    // o do Brasil, o resultado seria 31/12/2025 — o que moveria uma nota
    // fiscal de um ano para outro no cálculo do limite anual.
    expect(formatIsoDateBr("2026-01-01")).toBe("01/01/2026");
    expect(formatIsoDateBr("2026-12-31")).toBe("31/12/2026");
  });
});

describe("formatDataHoraBr", () => {
  it("mostra data e hora com dois dígitos", () => {
    // Constrói a partir de componentes locais para o teste não depender do
    // fuso do runner da CI. O separador entre data e hora varia com a versão
    // do ICU (", " ou " "), então a asserção olha os campos, não o literal.
    const iso = new Date(2026, 7, 25, 16, 4).toISOString();
    expect(formatDataHoraBr(iso)).toMatch(/^25\/08\/2026[, ]+16:04$/);
  });

  it("devolve travessão para data inválida", () => {
    expect(formatDataHoraBr("não é data")).toBe("—");
    expect(formatDataHoraBr("")).toBe("—");
  });
});

describe("todayIso", () => {
  it("devolve o formato AAAA-MM-DD", () => {
    expect(todayIso()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("usa o fuso local, não UTC", () => {
    const hoje = new Date();
    const esperado = [
      hoje.getFullYear(),
      String(hoje.getMonth() + 1).padStart(2, "0"),
      String(hoje.getDate()).padStart(2, "0"),
    ].join("-");

    expect(todayIso()).toBe(esperado);
  });
});
