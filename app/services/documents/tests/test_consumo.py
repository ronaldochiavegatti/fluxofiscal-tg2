"""Envio do consumo medido ao billing (ADR-0024).

O que se protege: com a flag desligada nada sai do serviço; ligada, o corpo
leva só rótulos e contagens; e uma falha do billing nunca chega ao usuário.
"""

import httpx

from app import consumo


class _Resposta:
    def raise_for_status(self):
        return None


def _ligar(monkeypatch, enviados):
    monkeypatch.setattr(consumo, "ativo", lambda: True)

    def post(url, json, timeout):
        enviados.append((url, json))
        return _Resposta()

    monkeypatch.setattr(consumo.httpx, "post", post)


class TestEnvio:
    def test_flag_desligada_nao_envia_nada(self, monkeypatch):
        monkeypatch.setattr(consumo.httpx, "post", lambda *a, **k: 1 / 0)

        assert consumo.registrar("mei@exemplo.com", "svc", "op", "m", 10, 2) is None

    def test_sem_email_nao_envia(self, monkeypatch):
        enviados = []
        _ligar(monkeypatch, enviados)

        assert consumo.registrar(None, "svc", "op", "m", 10, 2) is None
        assert enviados == []

    def test_envia_rotulos_e_contagens(self, monkeypatch):
        enviados = []
        _ligar(monkeypatch, enviados)

        consumo.registrar("mei@exemplo.com", "svc", "op", "modelo-x", 1580, 109).result()

        url, corpo = enviados[0]
        assert url.endswith("/usage")
        assert corpo == {
            "email": "mei@exemplo.com",
            "servico": "svc",
            "operacao": "op",
            "modelo": "modelo-x",
            "tokens_entrada": 1580,
            "tokens_saida": 109,
        }

    def test_contagem_de_entrada_e_feita_na_thread(self, monkeypatch):
        enviados = []
        _ligar(monkeypatch, enviados)

        consumo.registrar("mei@exemplo.com", "svc", "emb", "m", None, 0, lambda: 7).result()

        assert enviados[0][1]["tokens_entrada"] == 7

    def test_contagem_que_falha_desiste_sem_enviar(self, monkeypatch):
        enviados = []
        _ligar(monkeypatch, enviados)

        def falha():
            raise RuntimeError("count_tokens fora")

        consumo.registrar("mei@exemplo.com", "svc", "emb", "m", None, 0, falha).result()

        assert enviados == []

    def test_billing_fora_do_ar_nao_levanta(self, monkeypatch):
        monkeypatch.setattr(consumo, "ativo", lambda: True)

        def post(*_a, **_k):
            raise httpx.ConnectError("billing fora")

        monkeypatch.setattr(consumo.httpx, "post", post)

        futuro = consumo.registrar("mei@exemplo.com", "svc", "op", "m", 1, 1)

        assert futuro.result() is None


class TestIntegracaoNosDocumentos:
    def test_custo_da_extracao_vai_para_a_metrica_e_para_o_billing(self, monkeypatch):
        from app import main

        metrica, billing = [], []
        monkeypatch.setattr(main, "registrar_custo_gemini", lambda **k: metrica.append(k))
        monkeypatch.setattr(main.consumo, "registrar", lambda *a, **k: billing.append(a))

        main._registrador_de_custo("mei@exemplo.com")("extracao_imagem", "m", 1580, 109)

        assert metrica[0]["tokens_entrada"] == 1580
        assert billing[0] == ("mei@exemplo.com", "documents", "extracao_imagem", "m", 1580, 109)
