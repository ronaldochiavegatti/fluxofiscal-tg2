"""Rotas do Insights (US-21, US-23).

Leitura da projeção, status do consumo e os comandos internos da US-23:
reconstrução a partir do Limits e conciliação sob demanda.
"""

import uuid
from datetime import UTC, datetime

from app import main, projecao
from app.acl_limits import ResumoLimits, TransacaoLimits
from tests.conftest import EMAIL


def _semear(motor):
    with main.SessionLocal() as db:
        db.add(
            projecao.ResumoInsights(
                usuario_email=EMAIL,
                ano=2026,
                total_vendas=4700.0,
                total_compras=300.0,
                qtd_transacoes=5,
            )
        )
        db.add(projecao.EventoProcessado(evento_id="e1", tipo="transacao.criada"))
        db.commit()


class TestResumo:
    def test_projecao_do_usuario(self, cliente, motor):
        _semear(motor)
        corpo = cliente.get(f"/resumo/{EMAIL}", params={"ano": 2026}).json()
        assert corpo["total_vendas"] == 4700.0
        assert corpo["total_compras"] == 300.0
        assert corpo["qtd_transacoes"] == 5

    def test_usuario_sem_projecao_devolve_zeros(self, cliente, motor):
        corpo = cliente.get("/resumo/ninguem@mei.com.br").json()
        assert corpo["total_vendas"] == 0.0
        assert corpo["qtd_transacoes"] == 0
        assert corpo["atualizado_em"] is None

    def test_expoe_o_horario_do_ultimo_recalculo(self, cliente, motor):
        """Cenário Gherkin US-23: "o dashboard exibe o horário do último
        recálculo". Aplicar um evento move o `atualizado_em`."""
        antes = datetime.now(UTC)
        _aplicar({"email": EMAIL, "valor": 1000.0, "tx_type": "venda", "tx_date": "2026-03-10"})
        corpo = cliente.get(f"/resumo/{EMAIL}", params={"ano": 2026}).json()
        assert corpo["atualizado_em"] is not None
        assert datetime.fromisoformat(corpo["atualizado_em"]) >= antes.replace(tzinfo=None)


class TestStatus:
    def test_conta_eventos_processados(self, cliente, motor):
        _semear(motor)
        corpo = cliente.get("/_interno/status").json()
        assert corpo["eventos_processados"] == 1
        assert corpo["eventos_pendentes"] == 0


def _aplicar(dados: dict, tipo: str = "transacao.criada") -> None:
    projecao.aplicar_evento(
        main.SessionLocal,
        {
            "evento_id": str(uuid.uuid4()),
            "tipo": tipo,
            "versao": 1,
            "ocorrido_em": datetime.now(UTC).isoformat(),
            "produtor": "limits",
            "chave_particao": dados["email"],
            "dados": dados,
        },
    )


class ClienteLimitsFake:
    """Duplo de `acl_limits.ClienteLimits` para as rotas internas — context
    manager, com transações e resumo canned."""

    transacoes_por_email: dict[str, list[TransacaoLimits]] = {}
    resumo_por_email: dict[str, ResumoLimits] = {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def transacoes(self, email: str, ano: int) -> list[TransacaoLimits]:
        return list(self.transacoes_por_email.get(email, []))

    def resumo(self, email: str, ano: int) -> ResumoLimits:
        return self.resumo_por_email[email]


class TestReconstruir:
    def test_refaz_a_projecao_a_partir_do_limits(self, cliente, motor, monkeypatch):
        _semear(motor)  # projeção "errada": 4700 / 300 / 5
        ClienteLimitsFake.transacoes_por_email = {
            EMAIL: [
                TransacaoLimits(valor=1000.0, tipo="venda", data="2026-01-05"),
                TransacaoLimits(valor=500.0, tipo="venda", data="2026-02-05"),
            ]
        }
        monkeypatch.setattr(main.acl_limits, "ClienteLimits", ClienteLimitsFake)

        corpo = cliente.post("/_interno/reconstruir", json={"email": EMAIL, "ano": 2026}).json()

        assert corpo["quantidade"] == 1
        assert corpo["reconstruidos"][0]["total_vendas"] == 1500.0
        assert corpo["reconstruidos"][0]["qtd_transacoes"] == 2
        depois = cliente.get(f"/resumo/{EMAIL}", params={"ano": 2026}).json()
        assert depois["total_vendas"] == 1500.0
        assert depois["total_compras"] == 0.0


class TestConciliar:
    def test_reporta_divergencia(self, cliente, motor, monkeypatch):
        _semear(motor)  # projeção 4700 / 300
        ClienteLimitsFake.resumo_por_email = {
            EMAIL: ResumoLimits(total_vendas=4700.0, total_compras=999.0)
        }
        monkeypatch.setattr(main.acl_limits, "ClienteLimits", ClienteLimitsFake)

        corpo = cliente.post("/_interno/conciliar", json={"ano": 2026}).json()

        assert corpo["ok"] is False
        assert corpo["quantidade"] == 1
        assert corpo["divergencias"][0]["campo"] == "total_compras"

    def test_sem_divergencia_responde_ok(self, cliente, motor, monkeypatch):
        _semear(motor)
        ClienteLimitsFake.resumo_por_email = {
            EMAIL: ResumoLimits(total_vendas=4700.0, total_compras=300.0)
        }
        monkeypatch.setattr(main.acl_limits, "ClienteLimits", ClienteLimitsFake)

        corpo = cliente.post("/_interno/conciliar", json={"ano": 2026}).json()

        assert corpo == {"divergencias": [], "quantidade": 0, "ok": True}


def test_health(cliente):
    assert cliente.get("/health").json() == {"status": "ok", "service": "insights"}
