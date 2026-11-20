"""Rotas de ritmo do Limits (US-25), sobre o motor de domínio da US-28.

O motor em si já é testado sem banco em `test_dominio_ritmo.py`. O que importa
aqui é a agregação: se a rota soma o que devia somar (só venda, só do ano, só
os últimos 30 dias) e traduz o resultado do domínio sem perder informação.
"""

from datetime import UTC, date, datetime, timedelta

from app.dominio import TRANSACOES_MINIMAS_PARA_PROJETAR

EMAIL = "marcia@mei.com.br"
ANO = 2026


def _hoje():
    return datetime.now(UTC).date()


class TestAgregacao:
    def test_soma_apenas_vendas_do_ano(self, cliente, registrar):
        registrar(EMAIL, 1000.00, f"{ANO}-03-10", "venda")
        registrar(EMAIL, 500.00, f"{ANO}-03-11", "compra")
        registrar(EMAIL, 2000.00, f"{ANO - 1}-12-31", "venda")

        corpo = cliente.get(f"/ritmo/{EMAIL}", params={"year": ANO}).json()

        assert corpo["total_vendas"] == 1000.00

    def test_restante_e_percentual_seguem_o_gauge_do_cenario_de_referencia(
        self, cliente, registrar
    ):
        """Cenário Gherkin: "O gauge mostra três informações" — 58,4%,
        acumulado e restante, sobre R$ 81.000,00 (sem abertura no ano)."""
        registrar(EMAIL, 47304.00, f"{ANO}-03-10", "venda")

        corpo = cliente.get(f"/ritmo/{EMAIL}", params={"year": ANO}).json()

        assert corpo["limite_aplicavel"] == 81000.00
        assert corpo["total_vendas"] == 47304.00
        assert corpo["restante"] == 33696.00
        assert corpo["percent_used"] == 58.4

    def test_dias_decorridos_e_total_dias_ano_vem_para_o_grafico_de_corrida(
        self, cliente, registrar
    ):
        """US-26 precisa saber onde "hoje" cai no eixo e até onde o ano vai —
        sem reimplementar a conta de dias decorridos no front."""
        registrar(EMAIL, 1000.00, f"{ANO}-03-10", "venda")

        corpo = cliente.get(f"/ritmo/{EMAIL}", params={"year": ANO}).json()

        assert corpo["total_dias_ano"] == 365  # 2026 não é bissexto
        assert corpo["dias_decorridos"] == (_hoje() - date(ANO, 1, 1)).days + 1

    def test_usuario_sem_transacoes_nao_quebra(self, cliente):
        corpo = cliente.get("/ritmo/ninguem@mei.com.br", params={"year": ANO}).json()

        assert corpo["total_vendas"] == 0.0
        assert corpo["projecao_disponivel"] is False
        assert corpo["motivo_indisponivel"] == "dados insuficientes para projeção"
        assert corpo["nivel"] == "ok"


class TestLimiteProporcional:
    """Cenário Gherkin: "Limite proporcional para abertura no ano"."""

    def test_data_abertura_no_meio_do_ano_reduz_o_limite(self, cliente, registrar):
        registrar(EMAIL, 1000.00, f"{ANO}-08-10", "venda")

        corpo = cliente.get(
            f"/ritmo/{EMAIL}", params={"year": ANO, "data_abertura": f"{ANO}-07-03"}
        ).json()

        assert corpo["limite_aplicavel"] == 40500.00
        assert corpo["meses_de_atividade"] == 6
        assert corpo["proporcional"] is True

    def test_sem_data_abertura_assume_limite_cheio(self, cliente, registrar):
        """Sem a US-34 (Perfil do MEI), não há onde guardar a abertura real —
        o padrão seguro é o comportamento de sempre: limite cheio."""
        registrar(EMAIL, 1000.00, f"{ANO}-03-10", "venda")

        corpo = cliente.get(f"/ritmo/{EMAIL}", params={"year": ANO}).json()

        assert corpo["limite_aplicavel"] == 81000.00
        assert corpo["proporcional"] is False
        assert corpo["meses_de_atividade"] is None


class TestProjecaoEUltimos30Dias:
    def test_projecao_indisponivel_com_poucas_transacoes(self, cliente, registrar):
        registrar(EMAIL, 1000.00, _hoje().isoformat(), "venda")

        corpo = cliente.get(f"/ritmo/{EMAIL}", params={"year": ANO}).json()

        assert corpo["projecao_disponivel"] is False
        assert corpo["projecao_anual"] is None
        assert corpo["indice_ritmo"] is None

    def test_projecao_disponivel_com_dado_suficiente(self, cliente, registrar):
        for i in range(TRANSACOES_MINIMAS_PARA_PROJETAR):
            registrar(EMAIL, 1000.00, (_hoje() - timedelta(days=i)).isoformat(), "venda")

        corpo = cliente.get(f"/ritmo/{EMAIL}", params={"year": ANO}).json()

        assert corpo["projecao_disponivel"] is True
        assert corpo["projecao_anual"] is not None
        assert corpo["motivo_indisponivel"] is None
        assert corpo["nivel"] in {
            "ok",
            "atencao_ritmo",
            "atencao",
            "risco",
            "estourado",
            "desenquadramento",
        }
        assert corpo["tendencia"] in {"acelerando", "estavel", "desacelerando"}

    def test_ultimos_30_dias_ignora_o_que_esta_fora_da_janela(self, cliente, registrar):
        registrar(EMAIL, 100.00, (_hoje() - timedelta(days=5)).isoformat(), "venda")
        registrar(EMAIL, 100.00, (_hoje() - timedelta(days=10)).isoformat(), "venda")
        registrar(EMAIL, 100.00, (_hoje() - timedelta(days=45)).isoformat(), "venda")

        corpo = cliente.get(f"/ritmo/{EMAIL}", params={"year": ANO}).json()

        assert corpo["taxa_diaria_recente"] == round(200 / 30, 2)

    def test_ultimos_90_dias_e_o_ritmo_otimista_do_cone(self, cliente, registrar):
        """`taxa_diaria_90d` — usado pela US-26 como o ritmo "otimista" do
        cone de projeção; a janela é mais larga que a de 30 dias."""
        registrar(EMAIL, 100.00, (_hoje() - timedelta(days=5)).isoformat(), "venda")
        registrar(EMAIL, 100.00, (_hoje() - timedelta(days=80)).isoformat(), "venda")
        registrar(EMAIL, 100.00, (_hoje() - timedelta(days=95)).isoformat(), "venda")  # fora

        corpo = cliente.get(f"/ritmo/{EMAIL}", params={"year": ANO}).json()

        assert corpo["taxa_diaria_90d"] == round(200 / 90, 2)


class TestAnoFechado:
    def test_ano_anterior_usa_o_ano_inteiro_decorrido(self, cliente, registrar):
        """Ano já fechado: não há "hoje" real para projetar — trata como se
        o ano inteiro tivesse decorrido, então a projeção coincide com o
        realizado."""
        registrar(EMAIL, 4000.00, f"{ANO - 1}-02-01", "venda")
        registrar(EMAIL, 3000.00, f"{ANO - 1}-06-15", "venda")
        registrar(EMAIL, 3000.00, f"{ANO - 1}-11-20", "venda")

        corpo = cliente.get(f"/ritmo/{EMAIL}", params={"year": ANO - 1}).json()

        assert corpo["total_vendas"] == 10000.00
        assert corpo["projecao_disponivel"] is True
        assert corpo["projecao_anual"] == 10000.00


class TestValidacao:
    def test_data_abertura_no_futuro_e_recusada_com_400_nao_500(self, cliente, registrar):
        """Achado pela suíte de contrato (Schemathesis): `data_abertura` é
        parâmetro livre, então precisa de resposta controlada para entrada
        contraditória — nunca um 500."""
        registrar(EMAIL, 1000.00, f"{ANO}-03-10", "venda")

        resposta = cliente.get(
            f"/ritmo/{EMAIL}", params={"year": ANO, "data_abertura": f"{ANO + 50}-01-01"}
        )

        assert resposta.status_code == 400


class TestSerieAcumulada:
    """`GET /ritmo/{email}/serie` — a curva "realizado" do gráfico de corrida
    contra o limite (US-26). Um ponto por dia, carregando o último valor
    conhecido adiante nos dias sem venda."""

    def test_um_ponto_por_dia_ate_hoje(self, cliente, registrar):
        registrar(EMAIL, 1000.00, f"{ANO}-01-01", "venda")

        pontos = cliente.get(f"/ritmo/{EMAIL}/serie", params={"year": ANO}).json()

        dias_no_ano_ate_hoje = (_hoje() - date(ANO, 1, 1)).days + 1
        assert len(pontos) == dias_no_ano_ate_hoje
        assert pontos[0]["data"] == f"{ANO}-01-01"
        assert pontos[-1]["data"] == _hoje().isoformat()

    def test_carrega_o_acumulado_adiante_nos_dias_sem_venda(self, cliente, registrar):
        registrar(EMAIL, 1000.00, f"{ANO}-01-05", "venda")
        registrar(EMAIL, 500.00, f"{ANO}-01-10", "venda")

        pontos = cliente.get(f"/ritmo/{EMAIL}/serie", params={"year": ANO}).json()
        por_data = {p["data"]: p["acumulado"] for p in pontos}

        assert por_data[f"{ANO}-01-04"] == 0.0
        assert por_data[f"{ANO}-01-05"] == 1000.00
        assert por_data[f"{ANO}-01-07"] == 1000.00  # sem venda no dia, carrega adiante
        assert por_data[f"{ANO}-01-10"] == 1500.00

    def test_ignora_compra_e_ano_diferente(self, cliente, registrar):
        registrar(EMAIL, 1000.00, f"{ANO}-01-05", "venda")
        registrar(EMAIL, 500.00, f"{ANO}-01-05", "compra")
        registrar(EMAIL, 2000.00, f"{ANO - 1}-12-31", "venda")

        pontos = cliente.get(f"/ritmo/{EMAIL}/serie", params={"year": ANO}).json()

        assert pontos[-1]["acumulado"] == 1000.00

    def test_bate_com_o_total_do_ritmo_no_ultimo_ponto(self, cliente, registrar):
        registrar(EMAIL, 1000.00, f"{ANO}-01-05", "venda")
        registrar(EMAIL, 2500.00, f"{ANO}-06-20", "venda")

        serie = cliente.get(f"/ritmo/{EMAIL}/serie", params={"year": ANO}).json()
        ritmo = cliente.get(f"/ritmo/{EMAIL}", params={"year": ANO}).json()

        assert serie[-1]["acumulado"] == ritmo["total_vendas"]

    def test_ano_fechado_vai_ate_31_de_dezembro(self, cliente, registrar):
        registrar(EMAIL, 1000.00, f"{ANO - 1}-03-10", "venda")

        pontos = cliente.get(f"/ritmo/{EMAIL}/serie", params={"year": ANO - 1}).json()

        assert pontos[-1]["data"] == f"{ANO - 1}-12-31"
        assert pontos[-1]["acumulado"] == 1000.00

    def test_usuario_sem_transacoes_fica_em_zero_o_ano_inteiro(self, cliente):
        pontos = cliente.get("/ritmo/ninguem@mei.com.br/serie", params={"year": ANO}).json()

        assert all(p["acumulado"] == 0.0 for p in pontos)
