"""Testes das rotas do Limits.

O núcleo fiscal já é testado sem banco em `test_dominio_limites.py`. O que
importa aqui é a outra metade: se o serviço agrega o que devia agregar, se
traduz o resultado do domínio para o contrato HTTP sem perder informação, e se
os filtros por ano e mês recortam o que dizem recortar.
"""

from datetime import UTC, datetime

import pytest

from app import main

EMAIL = "marcia@mei.com.br"
OUTRO = "douglas@mei.com.br"
ANO = 2026


class TestHealth:
    def test_responde_identificando_o_servico(self, cliente):
        resposta = cliente.get("/health")

        assert resposta.status_code == 200
        assert resposta.json() == {"status": "ok", "service": "limits"}


class TestCriacaoDeTransacao:
    def test_grava_e_devolve_a_transacao(self, registrar):
        criada = registrar(EMAIL, 1500.50, f"{ANO}-03-10")

        assert criada["id"] > 0
        assert criada["email"] == EMAIL
        assert criada["amount"] == 1500.50
        assert criada["tx_date"] == f"{ANO}-03-10"
        assert criada["tx_type"] == "venda"

    def test_tipo_padrao_e_venda(self, cliente):
        resposta = cliente.post(
            "/transactions",
            json={"email": EMAIL, "amount": 100.0, "tx_date": f"{ANO}-01-05"},
        )

        assert resposta.status_code == 200
        assert resposta.json()["tx_type"] == "venda"

    def test_tipo_invalido_e_recusado(self, cliente):
        resposta = cliente.post(
            "/transactions",
            json={
                "email": EMAIL,
                "amount": 100.0,
                "tx_date": f"{ANO}-01-05",
                "tx_type": "doacao",
            },
        )

        assert resposta.status_code == 400
        assert "doacao" in resposta.json()["detail"]

    def test_email_invalido_e_recusado_pelo_contrato(self, cliente):
        resposta = cliente.post(
            "/transactions",
            json={"email": "nao-e-email", "amount": 100.0, "tx_date": f"{ANO}-01-05"},
        )

        assert resposta.status_code == 422


class TestEdicaoDeTransacao:
    def test_corrige_valor_extraido_errado(self, cliente, registrar):
        criada = registrar(EMAIL, 12345.00, f"{ANO}-04-01")

        resposta = cliente.patch(f"/transactions/{criada['id']}", json={"amount": 123.45})

        assert resposta.status_code == 200
        assert resposta.json()["amount"] == 123.45

    def test_campo_omitido_permanece_como_estava(self, cliente, registrar):
        criada = registrar(EMAIL, 900.00, f"{ANO}-04-01")

        resposta = cliente.patch(f"/transactions/{criada['id']}", json={"amount": 950.00})

        assert resposta.json()["tx_date"] == f"{ANO}-04-01"
        assert resposta.json()["tx_type"] == "venda"

    def test_mudanca_de_tipo_recalcula_o_faturamento(self, cliente, registrar):
        """Corrigir "venda" para "compra" precisa tirar o valor do teto.

        É o caso de uso mais provável de erro do usuário na revisão do
        documento, e o que mais muda a orientação que ele recebe.
        """
        criada = registrar(EMAIL, 5000.00, f"{ANO}-05-02")
        assert cliente.get(f"/summary/{EMAIL}?year={ANO}").json()["total_revenue"] == 5000.00

        cliente.patch(f"/transactions/{criada['id']}", json={"tx_type": "compra"})

        resumo = cliente.get(f"/summary/{EMAIL}?year={ANO}").json()
        assert resumo["total_revenue"] == 0.0
        assert resumo["total_despesas"] == 5000.00

    def test_transacao_inexistente(self, cliente):
        resposta = cliente.patch("/transactions/9999", json={"amount": 1.0})

        assert resposta.status_code == 404

    def test_tipo_invalido_na_edicao(self, cliente, registrar):
        criada = registrar(EMAIL, 100.00, f"{ANO}-01-01")

        resposta = cliente.patch(f"/transactions/{criada['id']}", json={"tx_type": "estorno"})

        assert resposta.status_code == 400


class TestRemocao:
    """Apagar um lançamento quando a nota que o gerou é apagada (#96)."""

    def test_apaga_e_sai_do_resumo(self, cliente, registrar):
        criada = registrar(EMAIL, 500.00, f"{ANO}-02-10")
        registrar(EMAIL, 100.00, f"{ANO}-02-11")

        resposta = cliente.delete(f"/transactions/{criada['id']}")

        assert resposta.status_code == 200
        assert resposta.json() == {"id": criada["id"], "removida": True}
        assert cliente.get(f"/summary/{EMAIL}?year={ANO}").json()["total_revenue"] == 100.00
        restantes = [t["id"] for t in cliente.get(f"/transactions?email={EMAIL}").json()]
        assert criada["id"] not in restantes

    def test_transacao_inexistente(self, cliente):
        assert cliente.delete("/transactions/9999").status_code == 404

    def test_apagar_duas_vezes_da_404_na_segunda(self, cliente, registrar):
        criada = registrar(EMAIL, 10.00, f"{ANO}-02-10")
        cliente.delete(f"/transactions/{criada['id']}")

        assert cliente.delete(f"/transactions/{criada['id']}").status_code == 404


class TestListagem:
    @pytest.fixture
    def base(self, cliente, registrar):
        registrar(EMAIL, 100.00, f"{ANO}-01-15")
        registrar(EMAIL, 200.00, f"{ANO}-03-20")
        registrar(EMAIL, 300.00, f"{ANO - 1}-03-20")
        registrar(OUTRO, 999.00, f"{ANO}-03-20")
        return cliente

    def test_isola_por_usuario(self, base):
        valores = [t["amount"] for t in base.get(f"/transactions?email={EMAIL}").json()]

        assert 999.00 not in valores

    def test_filtra_por_ano(self, base):
        resposta = base.get(f"/transactions?email={EMAIL}&year={ANO}")

        assert [t["amount"] for t in resposta.json()] == [200.00, 100.00]

    def test_filtra_por_mes(self, base):
        resposta = base.get(f"/transactions?email={EMAIL}&year={ANO}&month=3")

        assert [t["amount"] for t in resposta.json()] == [200.00]

    def test_ordena_da_mais_recente_para_a_mais_antiga(self, base):
        datas = [t["tx_date"] for t in base.get(f"/transactions?email={EMAIL}").json()]

        assert datas == sorted(datas, reverse=True)

    def test_mes_fora_da_faixa_e_recusado(self, base):
        assert base.get(f"/transactions?email={EMAIL}&month=13").status_code == 422


class TestResumoAnual:
    def test_so_venda_conta_para_o_teto(self, cliente, registrar):
        registrar(EMAIL, 50000.00, f"{ANO}-02-10")
        registrar(EMAIL, 30000.00, f"{ANO}-02-11", tipo="compra")

        resumo = cliente.get(f"/summary/{EMAIL}?year={ANO}").json()

        assert resumo["total_revenue"] == 50000.00
        assert resumo["total_despesas"] == 30000.00
        assert resumo["saldo_liquido"] == 20000.00
        assert resumo["remaining"] == 31000.00
        assert resumo["exceeded"] is False

    def test_usuario_sem_transacoes(self, cliente):
        resumo = cliente.get(f"/summary/ninguem@mei.com.br?year={ANO}").json()

        assert resumo["total_revenue"] == 0.0
        assert resumo["percent_used"] == 0.0
        assert resumo["alert_level"] == "ok"
        assert resumo["annual_limit"] == main.MEI_ANNUAL_LIMIT

    def test_transacao_de_outro_ano_nao_entra(self, cliente, registrar):
        registrar(EMAIL, 70000.00, f"{ANO - 1}-12-31")

        assert cliente.get(f"/summary/{EMAIL}?year={ANO}").json()["total_revenue"] == 0.0

    @pytest.mark.parametrize(
        ("faturamento", "nivel"),
        [
            (64799.99, "ok"),
            (64800.00, "warning"),
            (81000.00, "warning"),
            (81000.01, "exceeded"),
        ],
    )
    def test_nivel_de_alerta_acompanha_o_dominio(self, cliente, registrar, faturamento, nivel):
        registrar(EMAIL, faturamento, f"{ANO}-06-17")

        assert cliente.get(f"/summary/{EMAIL}?year={ANO}").json()["alert_level"] == nivel

    def test_ano_padrao_e_o_ano_corrente(self, cliente, registrar):
        """Regressão: o padrão era `Query(default=datetime.utcnow().year)`.

        Um valor padrão de `Query` é avaliado uma vez, na importação do módulo.
        O serviço que subisse em dezembro continuaria respondendo sobre o ano
        anterior depois da virada, até alguém reiniciá-lo.
        """
        corrente = datetime.now(UTC).year
        registrar(EMAIL, 4321.00, f"{corrente}-01-02")

        resumo = cliente.get(f"/summary/{EMAIL}").json()

        assert resumo["year"] == corrente
        assert resumo["total_revenue"] == 4321.00


class TestReset:
    def test_apaga_apenas_o_usuario_pedido(self, cliente, registrar):
        registrar(EMAIL, 100.00, f"{ANO}-01-01")
        registrar(OUTRO, 200.00, f"{ANO}-01-01")

        resposta = cliente.delete(f"/reset/{EMAIL}")

        assert resposta.json() == {"email": EMAIL, "transactions_deleted": 1}
        assert cliente.get(f"/transactions?email={EMAIL}").json() == []
        assert len(cliente.get(f"/transactions?email={OUTRO}").json()) == 1


class TestRelatorioPdf:
    def test_devolve_um_pdf_com_nome_de_arquivo(self, cliente, registrar):
        registrar(EMAIL, 1234.56, f"{ANO}-07-08")

        resposta = cliente.get(f"/report/{EMAIL}?year={ANO}")

        assert resposta.status_code == 200
        assert resposta.headers["content-type"] == "application/pdf"
        assert "relatorio-mei-marcia_mei.com.br-2026.pdf" in resposta.headers["content-disposition"]
        assert resposta.content.startswith(b"%PDF-")

    def test_ano_sem_transacoes_ainda_gera_pdf(self, cliente):
        """Relatório vazio é resposta legítima; erro 500 não é."""
        resposta = cliente.get(f"/report/{EMAIL}?year={ANO - 5}")

        assert resposta.status_code == 200
        assert resposta.content.startswith(b"%PDF-")

    def test_email_com_acento_nao_derruba_o_cabecalho(self, cliente):
        """Regressão: `Content-Disposition` é codificado em latin-1.

        Endereço internacionalizado é válido para o `EmailStr`, e interpolá-lo
        cru no cabeçalho derrubava a rota com `UnicodeEncodeError`.
        """
        resposta = cliente.get(f"/report/joão@mei.com.br?year={ANO}")

        assert resposta.status_code == 200
        # Não levanta: é exatamente o que o servidor faz ao enviar o cabeçalho.
        resposta.headers["content-disposition"].encode("latin-1")


class TestFormatacaoBrasileira:
    @pytest.mark.parametrize(
        ("valor", "esperado"),
        [
            (0.0, "0,00"),
            (1234.5, "1.234,50"),
            (47304.0, "47.304,00"),
            (1234567.89, "1.234.567,89"),
        ],
    )
    def test_milhar_com_ponto_e_decimal_com_virgula(self, valor, esperado):
        assert main.format_brl(valor) == esperado
