"""Configuração das regras e metas por usuário (#91): rotas e efeito no painel.

O domínio já é testado em `test_dominio_parametros.py`. Aqui importa o
contrato HTTP (gravar, ler, voltar ao padrão, recusar o inválido) e que as
rotas do painel passam a usar a configuração — só com a flag ligada.
"""

import pytest

from app import main

EMAIL = "marcia@mei.com.br"
OUTRO = "joao@mei.com.br"
ANO = 2026


@pytest.fixture
def flag_ligada(monkeypatch):
    monkeypatch.setattr(main, "metricas_configuraveis_ligadas", lambda: True)


class TestRotasDeConfiguracao:
    def test_sem_configuracao_devolve_o_padrao(self, cliente):
        corpo = cliente.get(f"/configuracao/{EMAIL}").json()
        assert corpo["parametros"] == corpo["padrao"]
        assert corpo["parametros"]["limite_anual"] == 81000.0
        assert corpo["parametros"]["limiar_alerta"] == 0.8
        assert corpo["parametros"]["meta_mensal"] is None
        assert corpo["personalizados"] == []
        assert corpo["data_abertura"] is None
        assert corpo["ativa"] is False

    def test_grava_ajuste_parcial_e_lista_o_que_foi_personalizado(self, cliente):
        resposta = cliente.put(
            f"/configuracao/{EMAIL}",
            json={"parametros": {"limite_anual": 130000, "dias_minimos_para_projetar": 15}},
        )
        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["parametros"]["limite_anual"] == 130000.0
        assert corpo["parametros"]["dias_minimos_para_projetar"] == 15
        assert corpo["parametros"]["limiar_alerta"] == 0.8
        assert corpo["padrao"]["limite_anual"] == 81000.0
        assert corpo["personalizados"] == ["dias_minimos_para_projetar", "limite_anual"]

        # Persistiu, e um segundo PUT parcial não apaga o primeiro.
        cliente.put(f"/configuracao/{EMAIL}", json={"parametros": {"limiar_alerta": 0.7}})
        lido = cliente.get(f"/configuracao/{EMAIL}").json()
        assert lido["parametros"]["limite_anual"] == 130000.0
        assert lido["parametros"]["limiar_alerta"] == 0.7

    def test_configuracao_e_por_usuario(self, cliente):
        cliente.put(f"/configuracao/{EMAIL}", json={"parametros": {"limite_anual": 130000}})
        assert cliente.get(f"/configuracao/{OUTRO}").json()["parametros"]["limite_anual"] == 81000.0

    def test_null_devolve_o_campo_ao_padrao(self, cliente):
        cliente.put(
            f"/configuracao/{EMAIL}",
            json={"parametros": {"limite_anual": 130000, "limiar_alerta": 0.7}},
        )
        corpo = cliente.put(
            f"/configuracao/{EMAIL}", json={"parametros": {"limite_anual": None}}
        ).json()
        assert corpo["parametros"]["limite_anual"] == 81000.0
        assert corpo["personalizados"] == ["limiar_alerta"]

    def test_valor_igual_ao_padrao_nao_conta_como_personalizado(self, cliente):
        corpo = cliente.put(
            f"/configuracao/{EMAIL}",
            json={"parametros": {"limite_anual": 81000, "limite_proporcional": True}},
        ).json()
        assert corpo["personalizados"] == []

    def test_booleano_e_meta_mensal(self, cliente):
        corpo = cliente.put(
            f"/configuracao/{EMAIL}",
            json={"parametros": {"limite_proporcional": False, "meta_mensal": 5000}},
        ).json()
        assert corpo["parametros"]["limite_proporcional"] is False
        assert corpo["parametros"]["meta_mensal"] == 5000.0

    def test_data_de_abertura_grava_e_apaga(self, cliente):
        corpo = cliente.put(f"/configuracao/{EMAIL}", json={"data_abertura": "2026-07-01"}).json()
        assert corpo["data_abertura"] == "2026-07-01"
        # PUT sem o campo não mexe na data.
        corpo = cliente.put(
            f"/configuracao/{EMAIL}", json={"parametros": {"limiar_alerta": 0.7}}
        ).json()
        assert corpo["data_abertura"] == "2026-07-01"
        corpo = cliente.put(f"/configuracao/{EMAIL}", json={"data_abertura": None}).json()
        assert corpo["data_abertura"] is None

    @pytest.mark.parametrize(
        "parametros",
        [
            {"limite_anual": 0},
            {"limiar_alerta": 1.5},
            {"margem_desenquadramento": 0.5},
            {"dias_minimos_para_projetar": 0},
            {"campo_que_nao_existe": 1},
            {"limite_anual": True},
        ],
    )
    def test_invalido_e_422_e_nada_e_gravado(self, cliente, parametros):
        resposta = cliente.put(f"/configuracao/{EMAIL}", json={"parametros": parametros})
        assert resposta.status_code == 422
        assert cliente.get(f"/configuracao/{EMAIL}").json()["personalizados"] == []

    def test_campo_extra_no_corpo_e_422(self, cliente):
        resposta = cliente.put(f"/configuracao/{EMAIL}", json={"limite_anual": 1})
        assert resposta.status_code == 422

    def test_delete_volta_tudo_ao_padrao(self, cliente):
        cliente.put(
            f"/configuracao/{EMAIL}",
            json={"parametros": {"limite_anual": 130000}, "data_abertura": "2026-07-01"},
        )
        corpo = cliente.delete(f"/configuracao/{EMAIL}").json()
        assert corpo["personalizados"] == []
        assert corpo["data_abertura"] is None
        assert cliente.get(f"/configuracao/{EMAIL}").json()["parametros"]["limite_anual"] == 81000.0
        # Idempotente.
        assert cliente.delete(f"/configuracao/{EMAIL}").status_code == 200

    def test_gravada_invalida_mostra_padrao_em_vez_de_500(self, cliente):
        with main.SessionLocal() as db:
            db.add(main.ConfiguracaoFiscal(user_email=EMAIL, ajustes={"campo_removido": 1}))
            db.commit()
        corpo = cliente.get(f"/configuracao/{EMAIL}").json()
        assert corpo["parametros"] == corpo["padrao"]


class TestEfeitoNoPainel:
    def test_flag_desligada_ignora_a_configuracao(self, cliente, registrar):
        registrar(EMAIL, 60000, f"{ANO}-03-10")
        cliente.put(
            f"/configuracao/{EMAIL}",
            json={"parametros": {"limite_anual": 130000, "limiar_alerta": 0.4}},
        )
        resumo = cliente.get(f"/summary/{EMAIL}", params={"year": ANO}).json()
        assert resumo["annual_limit"] == 81000.0
        assert resumo["alert_level"] == "ok"
        assert resumo["alert_threshold_percent"] == 80.0

    def test_resumo_usa_limite_e_alerta_configurados(self, cliente, registrar, flag_ligada):
        registrar(EMAIL, 60000, f"{ANO}-03-10")
        cliente.put(
            f"/configuracao/{EMAIL}",
            json={"parametros": {"limite_anual": 130000, "limiar_alerta": 0.4}},
        )
        resumo = cliente.get(f"/summary/{EMAIL}", params={"year": ANO}).json()
        assert resumo["annual_limit"] == 130000.0
        assert resumo["remaining"] == 70000.0
        assert resumo["alert_level"] == "warning"
        assert resumo["alert_threshold_percent"] == 40.0

    def test_mensal_usa_meta_configurada(self, cliente, registrar, flag_ligada):
        registrar(EMAIL, 5000, f"{ANO}-03-10")
        cliente.put(f"/configuracao/{EMAIL}", json={"parametros": {"meta_mensal": 4000}})
        marco = cliente.get(f"/mensal/{EMAIL}", params={"year": ANO}).json()[2]
        assert marco["meta"] == 4000.0
        assert marco["acima_da_meta"] is True

    def test_mensal_e_ritmo_usam_a_data_de_abertura_configurada(
        self, cliente, registrar, flag_ligada
    ):
        registrar(EMAIL, 1000, f"{ANO}-08-10")
        cliente.put(f"/configuracao/{EMAIL}", json={"data_abertura": f"{ANO}-07-01"})
        assert cliente.get(f"/mensal/{EMAIL}", params={"year": ANO}).json()[0]["meta"] == 3375.0
        ritmo = cliente.get(f"/ritmo/{EMAIL}", params={"year": ANO}).json()
        assert ritmo["limite_aplicavel"] == 40500.0
        assert ritmo["proporcional"] is True

        # Desligar o proporcional devolve o teto cheio mesmo no ano de abertura.
        cliente.put(f"/configuracao/{EMAIL}", json={"parametros": {"limite_proporcional": False}})
        ritmo = cliente.get(f"/ritmo/{EMAIL}", params={"year": ANO}).json()
        assert ritmo["limite_aplicavel"] == 81000.0
        assert ritmo["proporcional"] is False

    def test_data_de_abertura_na_rota_vence_a_configurada(self, cliente, registrar, flag_ligada):
        registrar(EMAIL, 1000, f"{ANO}-08-10")
        cliente.put(f"/configuracao/{EMAIL}", json={"data_abertura": f"{ANO}-07-01"})
        ritmo = cliente.get(
            f"/ritmo/{EMAIL}", params={"year": ANO, "data_abertura": "2020-01-01"}
        ).json()
        assert ritmo["limite_aplicavel"] == 81000.0

    def test_concentracao_usa_limiar_configurado(self, cliente, registrar, flag_ligada):
        registrar(EMAIL, 600, f"{ANO}-03-10", cnpj_cliente="11.111.111/0001-11")
        registrar(EMAIL, 400, f"{ANO}-03-11", cnpj_cliente="22.222.222/0001-22")
        assert not any(
            c["alerta"] for c in cliente.get(f"/concentracao/{EMAIL}", params={"year": ANO}).json()
        )
        cliente.put(
            f"/configuracao/{EMAIL}", json={"parametros": {"limiar_concentracao_cliente": 0.5}}
        )
        itens = cliente.get(f"/concentracao/{EMAIL}", params={"year": ANO}).json()
        assert [c["alerta"] for c in itens] == [True, False]

    def test_gravada_invalida_nao_derruba_o_painel(self, cliente, registrar, flag_ligada):
        registrar(EMAIL, 1000, f"{ANO}-03-10")
        with main.SessionLocal() as db:
            db.add(main.ConfiguracaoFiscal(user_email=EMAIL, ajustes={"limiar_alerta": "7"}))
            db.commit()
        resumo = cliente.get(f"/summary/{EMAIL}", params={"year": ANO})
        assert resumo.status_code == 200
        assert resumo.json()["annual_limit"] == 81000.0

    def test_relatorio_pdf_usa_o_resumo_configurado(
        self, cliente, registrar, flag_ligada, monkeypatch
    ):
        registrar(EMAIL, 1000, f"{ANO}-03-10")
        cliente.put(f"/configuracao/{EMAIL}", json={"parametros": {"limite_anual": 130000}})
        capturado = {}

        def _pdf(email, year, summary, txs):
            capturado["limite"] = summary.annual_limit
            return b"%PDF-1.4"

        monkeypatch.setattr(main, "build_report_pdf", _pdf)
        assert cliente.get(f"/report/{EMAIL}", params={"year": ANO}).status_code == 200
        assert capturado["limite"] == 130000.0
