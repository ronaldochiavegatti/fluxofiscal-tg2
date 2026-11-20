"""Motor de ritmo de vendas do MEI: projeção anual, ritmo de vendas e o limite
proporcional para quem abriu o MEI durante o ano.

As fórmulas e os limiares abaixo são normativos — vêm de
`docs/dashboard-v2.md` §2, e são eles que a suíte de testes verifica. Estar em
40% do limite é tranquilo em outubro e é alarmante em março; o percentual
acumulado sozinho (`dominio/limites.py`) não distingue os dois casos. Este
módulo distingue, comparando o ritmo realizado com o ritmo necessário para
encostar no teto em 31 de dezembro.

A US-25 consome este módulo através de `GET /ritmo/{email}` — `data_abertura`
do MEI ainda não existe em nenhum modelo (chega com a US-34, Perfil do MEI,
Onda 5), então a rota aceita um valor por parâmetro, com default seguro
(limite cheio) até lá. A US-26 consome `GET /ritmo/{email}/serie` (a curva do
acumulado) e as taxas de 30/90 dias daqui, para montar o cone de projeção do
gráfico de corrida contra o limite.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from .limites import CENTAVO

# Os limiares da projeção (`docs/dashboard-v2.md` §2) moram em `parametros.py`,
# configuráveis por usuário (#91). Reexportados aqui porque é onde o resto do
# código sempre os buscou.
from .parametros import (
    DIAS_ABERTURA_RECENTE,
    DIAS_MINIMOS_PARA_PROJETAR,
    LIMIAR_ATENCAO_RITMO_REALIZADO,
    LIMIAR_LANCAMENTO_ATIPICO,
    LIMITE_ANUAL_MEI,
    PARAMETROS_PADRAO,
    TRANSACOES_MINIMAS_PARA_PROJETAR,
    ParametrosFiscais,
)


class NivelRitmo(StrEnum):
    """Os seis níveis de `docs/dashboard-v2.md` §2.4. Combinam o **realizado**
    (o que já aconteceu) com o **projetado** (para onde aponta) — por isso é
    um enum próprio, e não `dominio.limites.NivelAlerta`, que só olha o
    realizado."""

    OK = "ok"
    ATENCAO_RITMO = "atencao_ritmo"
    ATENCAO = "atencao"
    RISCO = "risco"
    ESTOURADO = "estourado"
    DESENQUADRAMENTO = "desenquadramento"


class Tendencia(StrEnum):
    """Direção do ritmo recente frente ao ritmo do ano — `AC = td30 / td`
    (`docs/dashboard-v2.md` §2.2). Sem faturamento (`AC` indefinida), o painel
    não tem base para apontar direção: `ESTAVEL` é o padrão seguro."""

    ACELERANDO = "acelerando"
    ESTAVEL = "estavel"
    DESACELERANDO = "desacelerando"


@dataclass(frozen=True, slots=True)
class LimiteAplicavel:
    """O teto do ano — cheio, ou proporcional aos meses de atividade."""

    valor: Decimal
    meses_de_atividade: int | None
    """`None` quando o limite é o cheio (MEI aberto antes do ano corrente).
    Quando não é `None`, é o número de meses que a interface cita na
    explicação ("proporcional a 6 meses")."""

    @property
    def proporcional(self) -> bool:
        return self.meses_de_atividade is not None


@dataclass(frozen=True, slots=True)
class Projecao:
    """Retrato de ritmo do ano para um MEI. Resultado de cálculo, imutável."""

    limite_aplicavel: Decimal
    meses_de_atividade: int | None

    dias_decorridos: int
    """`D`. Desde 1º de janeiro, salvo abertura recente (usa desde a
    abertura — ver `DIAS_ABERTURA_RECENTE`)."""

    total_dias_ano: int
    """`A`. Dias corridos do ano civil (365 ou 366)."""

    taxa_diaria: Decimal
    """`td = F / D`."""

    taxa_diaria_referencia: Decimal
    """`tr = L / A` — o ritmo que encostaria no teto em 31/12."""

    taxa_diaria_recente: Decimal
    """`td30` — média dos últimos 30 dias. O ritmo "pessimista" do cone de
    projeção da US-26 — o mais lento entre os três, tipicamente."""

    taxa_diaria_90d: Decimal
    """`td90` — média dos últimos 90 dias. O ritmo "otimista" do cone de
    projeção da US-26 (`docs/dashboard-v2.md` §3.1): uma janela mais larga
    que `td30`, menos sensível a um mês fraco isolado."""

    projecao_disponivel: bool
    """`False` quando as guardas de dado insuficiente disparam — `D` ou a
    quantidade de transações abaixo do mínimo. Nesse caso `projecao_anual`,
    `indice_ritmo`, `aceleracao`, `dias_ate_estouro` e `data_prevista_estouro`
    vêm `None`, e `motivo_indisponivel` explica por quê."""

    motivo_indisponivel: str | None

    projecao_anual: Decimal | None
    """`P = td x A` — onde o ano termina, se nada mudar."""

    indice_ritmo: Decimal | None
    """`IR = td / tr`. `1,0` = no ritmo exato do teto; `1,3` = 30% acima."""

    aceleracao: Decimal | None
    """`AC = td30 / td`. `None` sem faturamento (`td = 0`), que tornaria a
    razão indefinida."""

    dias_ate_estouro: int | None
    """`DT`, arredondado para cima — o dia em curso já conta. `None` sem
    faturamento (`td = 0`, estouro nunca chega nesse ritmo) ou sem projeção
    disponível."""

    data_prevista_estouro: date | None

    faturamento_seguro_mes: Decimal
    """`FS = (L - F) / meses_restantes` — teto mensal para pousar exatamente
    no limite. Não depende de projeção: é sempre calculado, e nunca negativo
    (zero quando o limite já foi ultrapassado)."""

    influenciada_por_lancamento_atipico: bool
    """Uma única transação responde por mais de `LIMIAR_LANCAMENTO_ATIPICO`
    do faturamento do ano. A projeção continua calculada; isto é uma
    anotação, não uma guarda."""

    nivel: NivelRitmo
    tendencia: Tendencia


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------


def _arredondar(valor: Decimal) -> Decimal:
    """Arredonda para centavos usando meio-para-cima, a convenção contábil.

    Cópia local e deliberada de `limites._arredondar`: é a mesma regra de
    exibição, não uma regra fiscal — duplicá-la não viola a proibição do
    CLAUDE.md contra duplicar regra fiscal fora de `dominio/`, e importar um
    nome privado de outro módulo seria pior acoplamento que duas linhas.
    """
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _total_dias_ano(ano: int) -> int:
    return (date(ano + 1, 1, 1) - date(ano, 1, 1)).days


def _dias_decorridos_desde(inicio: date, hoje: date) -> int:
    """Dias decorridos, contando o dia de hoje como decorrido — por isso
    `+ 1`: no primeiro dia (`hoje == inicio`) já decorreu 1 dia, não 0."""
    return (hoje - inicio).days + 1


# ---------------------------------------------------------------------------
# Regras
# ---------------------------------------------------------------------------


def calcular_limite_aplicavel(
    data_abertura: date,
    ano: int,
    limite_cheio: Decimal = LIMITE_ANUAL_MEI,
    proporcional: bool = True,
) -> LimiteAplicavel:
    """O teto não é sempre R$ 81.000,00: para quem abriu o MEI durante o ano,
    é proporcional aos meses de atividade (`docs/dashboard-v2.md` §2.1).

    Um MEI aberto em julho tem limite de R$ 40.500,00 naquele ano. Aplicar
    R$ 81.000,00 a ele diria que está seguro quando pode já ter estourado o
    teto proporcional — é a lacuna que esta função fecha.

    `proporcional=False` (configuração do usuário, #91) aplica o teto cheio
    mesmo no ano de abertura.
    """
    if data_abertura.year > ano:
        raise ValueError(
            f"data de abertura ({data_abertura}) não pode ser depois do ano de referência ({ano})"
        )

    if data_abertura.year < ano or not proporcional:
        return LimiteAplicavel(valor=_arredondar(limite_cheio), meses_de_atividade=None)

    meses_de_atividade = 12 - data_abertura.month + 1
    valor = _arredondar((limite_cheio / 12) * meses_de_atividade)
    return LimiteAplicavel(valor=valor, meses_de_atividade=meses_de_atividade)


def _classificar_nivel(
    faturamento: Decimal,
    limite: Decimal,
    projecao: Decimal | None,
    parametros: ParametrosFiscais = PARAMETROS_PADRAO,
) -> NivelRitmo:
    """Do mais severo ao mais brando — o primeiro que casar vence. Por isso
    "risco" e "atenção" já podem assumir `faturamento < limite`: os níveis
    mais severos (que cobrem `faturamento >= limite`) já teriam retornado."""
    if faturamento > limite * parametros.margem_desenquadramento:
        return NivelRitmo.DESENQUADRAMENTO
    if faturamento >= limite:
        return NivelRitmo.ESTOURADO
    if projecao is not None and projecao > limite:
        return NivelRitmo.RISCO
    if faturamento >= limite * parametros.limiar_alerta:
        return NivelRitmo.ATENCAO
    if (
        projecao is not None
        and projecao >= limite * parametros.limiar_alerta
        and faturamento < limite * parametros.limiar_atencao_ritmo_realizado
    ):
        return NivelRitmo.ATENCAO_RITMO
    return NivelRitmo.OK


def _classificar_tendencia(aceleracao: Decimal | None) -> Tendencia:
    if aceleracao is None:
        return Tendencia.ESTAVEL
    if aceleracao > 1:
        return Tendencia.ACELERANDO
    if aceleracao < 1:
        return Tendencia.DESACELERANDO
    return Tendencia.ESTAVEL


def calcular_projecao(
    *,
    faturamento_acumulado: Decimal,
    faturamento_ultimos_30_dias: Decimal,
    faturamento_ultimos_90_dias: Decimal,
    qtd_transacoes_ano: int,
    maior_transacao_ano: Decimal,
    data_abertura: date,
    hoje: date,
    parametros: ParametrosFiscais = PARAMETROS_PADRAO,
) -> Projecao:
    """Calcula o retrato de ritmo do ano de `hoje`, aplicando o limite
    proporcional e as guardas de `docs/dashboard-v2.md` §2.3.

    Recebe totais já agregados — a soma das últimas transações e o
    faturamento acumulado —, no mesmo espírito de `calcular_resumo`: a
    agregação é responsabilidade de quem lê o banco, o domínio só decide.
    """
    if faturamento_acumulado < 0:
        raise ValueError(
            f"faturamento_acumulado não pode ser negativo, recebido {faturamento_acumulado}"
        )
    if qtd_transacoes_ano < 0:
        raise ValueError(f"qtd_transacoes_ano não pode ser negativo, recebido {qtd_transacoes_ano}")
    if data_abertura > hoje:
        raise ValueError(f"data_abertura ({data_abertura}) não pode ser depois de hoje ({hoje})")

    ano = hoje.year
    limite_info = calcular_limite_aplicavel(
        data_abertura,
        ano,
        limite_cheio=parametros.limite_anual,
        proporcional=parametros.limite_proporcional,
    )
    limite = limite_info.valor
    total_dias_ano = _total_dias_ano(ano)

    dias_desde_abertura = _dias_decorridos_desde(data_abertura, hoje)
    aberta_recentemente = dias_desde_abertura < parametros.dias_abertura_recente
    dias_decorridos = (
        dias_desde_abertura
        if aberta_recentemente
        else _dias_decorridos_desde(date(ano, 1, 1), hoje)
    )

    # Precisão total até o fim da conta — só o valor exibido é arredondado.
    # Arredondar `td` cedo e multiplicar por 365 acumula erro (testado: a
    # diferença já aparece na segunda casa decimal do cenário de referência).
    faturamento = faturamento_acumulado
    taxa_diaria_exata = faturamento / dias_decorridos
    taxa_diaria_referencia_exata = limite / total_dias_ano
    taxa_diaria_recente_exata = faturamento_ultimos_30_dias / 30
    taxa_diaria_90d_exata = faturamento_ultimos_90_dias / 90

    disponivel = (
        dias_decorridos >= parametros.dias_minimos_para_projetar
        and qtd_transacoes_ano >= parametros.transacoes_minimas_para_projetar
    )
    motivo_indisponivel = None if disponivel else "dados insuficientes para projeção"

    projecao_anual_exata: Decimal | None = (
        taxa_diaria_exata * total_dias_ano if disponivel else None
    )

    indice_ritmo: Decimal | None = None
    if disponivel:
        indice_ritmo = _arredondar(taxa_diaria_exata / taxa_diaria_referencia_exata)

    aceleracao: Decimal | None = None
    if disponivel and taxa_diaria_exata > 0:
        aceleracao = _arredondar(taxa_diaria_recente_exata / taxa_diaria_exata)

    dias_ate_estouro: int | None = None
    data_prevista_estouro: date | None = None
    if disponivel and taxa_diaria_exata > 0:
        dt_exata = max(Decimal(0), (limite - faturamento)) / taxa_diaria_exata
        dias_ate_estouro = math.ceil(dt_exata)
        data_prevista_estouro = hoje + timedelta(days=dias_ate_estouro)
    elif disponivel:
        motivo_indisponivel = "sem faturamento registrado"

    meses_restantes = 12 - hoje.month + 1
    faturamento_seguro_mes = _arredondar(max(Decimal(0), limite - faturamento) / meses_restantes)

    influenciada_por_atipico = (
        faturamento > 0
        and (maior_transacao_ano / faturamento) > parametros.limiar_lancamento_atipico
    )

    nivel = _classificar_nivel(faturamento, limite, projecao_anual_exata, parametros)

    return Projecao(
        limite_aplicavel=limite,
        meses_de_atividade=limite_info.meses_de_atividade,
        dias_decorridos=dias_decorridos,
        total_dias_ano=total_dias_ano,
        taxa_diaria=_arredondar(taxa_diaria_exata),
        taxa_diaria_referencia=_arredondar(taxa_diaria_referencia_exata),
        taxa_diaria_recente=_arredondar(taxa_diaria_recente_exata),
        taxa_diaria_90d=_arredondar(taxa_diaria_90d_exata),
        projecao_disponivel=disponivel,
        motivo_indisponivel=motivo_indisponivel,
        projecao_anual=_arredondar(projecao_anual_exata)
        if projecao_anual_exata is not None
        else None,
        indice_ritmo=indice_ritmo,
        aceleracao=aceleracao,
        dias_ate_estouro=dias_ate_estouro,
        data_prevista_estouro=data_prevista_estouro,
        faturamento_seguro_mes=faturamento_seguro_mes,
        influenciada_por_lancamento_atipico=influenciada_por_atipico,
        nivel=nivel,
        tendencia=_classificar_tendencia(aceleracao),
    )


__all__ = [
    "DIAS_ABERTURA_RECENTE",
    "DIAS_MINIMOS_PARA_PROJETAR",
    "LIMIAR_ATENCAO_RITMO_REALIZADO",
    "LIMIAR_LANCAMENTO_ATIPICO",
    "TRANSACOES_MINIMAS_PARA_PROJETAR",
    "LimiteAplicavel",
    "NivelRitmo",
    "Projecao",
    "Tendencia",
    "calcular_limite_aplicavel",
    "calcular_projecao",
]
