"""Reconstrução da projeção a partir do Limits (US-23, ADR-0009).

O Insights é um modelo de leitura derivado: pode ser jogado fora e refeito. É
isso que torna seguro corrigir um erro de fórmula — em vez de migração de
dados, corrige-se o código e dispara-se o recálculo.

`reconstruir` zera a projeção do alvo e a refaz somando as transações que o
Limits (a fonte da verdade) reporta. O ledger de idempotência
(`eventos_processados`) não é tocado: os eventos já foram confirmados na stream
e não voltam; eventos novos, com `evento_id` novo, aplicam sobre a base refeita.
"""

from __future__ import annotations

import structlog

from . import projecao
from .acl_limits import ClienteLimits, LimitsIndisponivel
from .metrics import reconstrucoes_total

logger = structlog.get_logger("insights.reconstrucao")

ANO_PADRAO = projecao.ANO_PADRAO


def _ano_da_transacao(data_iso: str, padrao: int) -> int:
    return int(data_iso[:4]) if data_iso[:4].isdigit() else padrao


def reconstruir(
    session_factory,
    acl: ClienteLimits,
    *,
    email: str | None = None,
    ano: int | None = None,
) -> list[dict]:
    """Refaz a projeção. Sem `email`, refaz todos os que já têm projeção. Sem
    `ano`, usa o ano corrente. Devolve o retrato de cada projeção refeita."""
    ano = ano or ANO_PADRAO
    reconstrucoes_total.inc()

    with session_factory() as db:
        alvos = [email] if email else projecao.emails_com_projecao(db)

    refeitos: list[dict] = []
    for alvo in alvos:
        try:
            transacoes = acl.transacoes(alvo, ano)
        except LimitsIndisponivel:
            # Não zera o que não dá para refazer: a projeção antiga fica de pé.
            logger.warning("reconstrucao.limits_indisponivel", email=alvo, ano=ano)
            continue
        with session_factory() as db:
            projecao.zerar_usuario(db, alvo, ano)
            db.flush()
            linha = projecao.resumo_para(db, alvo, ano)
            for tx in transacoes:
                if _ano_da_transacao(tx.data, ano) == ano:
                    projecao.aplicar_transacao(linha, tx.valor, tx.tipo)
            db.commit()
            db.refresh(linha)
            refeitos.append(
                {
                    "email": alvo,
                    "ano": ano,
                    "total_vendas": float(linha.total_vendas),
                    "total_compras": float(linha.total_compras),
                    "qtd_transacoes": linha.qtd_transacoes,
                }
            )
        logger.info("reconstrucao.projecao_refeita", email=alvo, ano=ano, qtd=len(transacoes))

    return refeitos
