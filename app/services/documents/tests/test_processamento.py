"""Testes do pipeline de extração (`app/processamento.py`), sem HTTP.

Esta é a parte do Documents que mais decide o número que o MEI vê. Um valor
lido errado vira faturamento errado, e faturamento errado vira orientação
errada sobre desenquadramento — a pior falha possível neste domínio.

Nenhum teste aqui chama a API do Gemini: o cliente é um duplo ou é `None`, e aí
roda o caminho por expressões regulares — o mesmo que atende quando a cota
acaba ou a chave falha.
"""

import pytest

from app import processamento as p

NOTA = """NOTA FISCAL ELETRONICA
IDENTIFICACAO DO EMITENTE
Salao da Marcia LTDA
CNPJ: 12.345.678/0001-95
DESTINATARIO
Douglas Acessorios ME
CNPJ 98.765.432/0001-10
Data de emissao: 17/06/2026
Servico de manicure e pedicure
VALOR TOTAL R$ 1.234,56
"""


class TestValor:
    @pytest.mark.parametrize(
        ("texto", "esperado"),
        [
            ("VALOR TOTAL R$ 1.234,56", 1234.56),
            ("R$ 47,50", 47.50),
            ("r$1.000,00", 1000.00),
            ("Total: 99,99", 99.99),
            ("TOTAL 1.234.567,89", 1234567.89),
        ],
    )
    def test_formato_brasileiro(self, texto, esperado):
        assert p.extract_amount_from_text(texto) == esperado

    def test_prefere_o_valor_marcado_com_real(self):
        texto = "Quantidade 12,00\nDesconto 5,00\nVALOR TOTAL R$ 1.234,56"
        assert p.extract_amount_from_text(texto) == 1234.56

    def test_nao_confunde_cnpj_com_valor(self):
        assert p.extract_amount_from_text("CNPJ: 12.345.678/0001-95") is None

    def test_nao_confunde_data_com_valor(self):
        assert p.extract_amount_from_text("Emissao: 15/03/2026") is None

    def test_texto_sem_valor(self):
        assert p.extract_amount_from_text("nenhum numero aqui") is None

    def test_zero_nao_e_valor_valido(self):
        assert p.extract_amount_from_text("R$ 0,00") is None


class TestCnpj:
    @pytest.mark.parametrize(
        "entrada", ["12.345.678/0001-95", "12345678000195", "12.345.678/000195"]
    )
    def test_normaliza_para_o_formato_com_pontuacao(self, entrada):
        assert p.normalize_cnpj(entrada) == "12.345.678/0001-95"

    @pytest.mark.parametrize("entrada", [None, "", "123", "1234567800019512345"])
    def test_recusa_o_que_nao_tem_catorze_digitos(self, entrada):
        assert p.normalize_cnpj(entrada) is None

    def test_primeiro_e_emitente_segundo_e_destinatario(self):
        emitente, destinatario = p.extract_cnpjs(NOTA)
        assert emitente == "12.345.678/0001-95"
        assert destinatario == "98.765.432/0001-10"

    def test_cnpj_repetido_nao_vira_destinatario(self):
        texto = "CNPJ 12.345.678/0001-95 ... CNPJ: 12.345.678/0001-95"
        assert p.extract_cnpjs(texto) == ("12.345.678/0001-95", None)

    def test_documento_sem_cnpj(self):
        assert p.extract_cnpjs("recibo simples") == (None, None)


class TestData:
    @pytest.mark.parametrize(
        ("texto", "esperado"),
        [
            ("Emissao: 17/06/2026", "2026-06-17"),
            ("17-06-2026", "2026-06-17"),
            ("2026-06-17", "2026-06-17"),
            ("Data 5/06/2026", "2026-06-05"),
        ],
    )
    def test_normaliza_para_iso(self, texto, esperado):
        assert p.extract_date(texto) == esperado

    def test_texto_sem_data(self):
        assert p.extract_date("sem data alguma") is None


class TestDescricao:
    def test_pega_a_primeira_linha_com_conteudo(self):
        assert p.extract_description(NOTA) == "NOTA FISCAL ELETRONICA"

    def test_ignora_linhas_so_de_numeros(self):
        assert (
            p.extract_description("123456\n15/03/2026\nServico de pintura") == "Servico de pintura"
        )

    def test_limita_o_tamanho(self):
        assert len(p.extract_description("a" * 500)) == 140

    def test_texto_vazio(self):
        assert p.extract_description("   \n  ") is None


class TestExtracaoPorRegex:
    def test_le_a_nota_inteira(self):
        extraido = p.regex_extract(NOTA)
        assert extraido["value"] == 1234.56
        assert extraido["date"] == "2026-06-17"
        assert extraido["cnpj_emitente"] == "12.345.678/0001-95"
        assert extraido["cnpj_destinatario"] == "98.765.432/0001-10"

    def test_texto_vazio_devolve_tudo_nulo(self):
        assert set(p.regex_extract("").values()) == {None}


class TestSanitizacaoDoGemini:
    def test_aceita_resposta_completa(self):
        limpo = p.sanitize_gemini_result(
            {
                "amount": 1234.56,
                "date": "2026-06-17",
                "cnpj_emitente": "12345678000195",
                "cnpj_destinatario": None,
                "description": "Servico de manicure",
            }
        )
        assert limpo["value"] == 1234.56
        assert limpo["date"] == "2026-06-17"
        assert limpo["cnpj_emitente"] == "12.345.678/0001-95"
        assert limpo["description"] == "Servico de manicure"

    @pytest.mark.parametrize("valor", [None, "nao é numero", -10, 0])
    def test_valor_invalido_vira_nulo(self, valor):
        assert p.sanitize_gemini_result({"amount": valor})["value"] is None

    def test_valor_com_mascara_brasileira_e_traduzido(self):
        # US-46: a ACL entra aqui.
        assert p.sanitize_gemini_result({"amount": "1.234,56"})["value"] == 1234.56

    @pytest.mark.parametrize("data", ["17/06/2026", "2026-6-17", 20260617, None])
    def test_data_fora_do_formato_iso_vira_nula(self, data):
        assert p.sanitize_gemini_result({"date": data})["date"] is None

    def test_descricao_e_truncada(self):
        assert len(p.sanitize_gemini_result({"description": "x" * 500})["description"]) == 140

    def test_cnpj_malformado_vira_nulo(self):
        assert p.sanitize_gemini_result({"cnpj_emitente": "123"})["cnpj_emitente"] is None


class TestConfianca:
    @pytest.mark.parametrize(
        ("campos", "metodo", "esperado"),
        [
            (3, "gemini", 0.95),
            (2, "gemini", 0.85),
            (1, "gemini", 0.6),
            (0, "gemini", 0.3),
            (3, "regex", 0.9),
            (2, "regex", 0.75),
            (1, "regex", 0.55),
            (0, "regex", 0.2),
        ],
    )
    def test_cresce_com_os_campos_encontrados(self, campos, metodo, esperado):
        chaves = ["value", "date", "cnpj_emitente"]
        assert p.score_confidence(dict.fromkeys(chaves[:campos], "x"), metodo) == esperado

    def test_gemini_vale_mais_que_regex_com_os_mesmos_campos(self):
        e = {"value": 1, "date": "2026-01-01", "cnpj_emitente": "x"}
        assert p.score_confidence(e, "gemini") > p.score_confidence(e, "regex")


class TestSugestaoDeTipo:
    EMITENTE = "12.345.678/0001-95"
    DESTINATARIO = "98.765.432/0001-10"

    def test_usuario_emitente_e_venda(self):
        assert p.suggest_tx_type(self.EMITENTE, self.EMITENTE, self.DESTINATARIO) == ("venda", True)

    def test_usuario_destinatario_e_compra(self):
        assert p.suggest_tx_type(self.DESTINATARIO, self.EMITENTE, self.DESTINATARIO) == (
            "compra",
            True,
        )

    def test_pontuacao_nao_atrapalha_a_comparacao(self):
        assert p.suggest_tx_type("12345678000195", self.EMITENTE, None) == ("venda", True)

    def test_sem_cnpj_do_usuario_nao_ha_sugestao(self):
        assert p.suggest_tx_type(None, self.EMITENTE, self.DESTINATARIO) == (None, False)

    def test_usuario_alheio_ao_documento_nao_ha_sugestao(self):
        assert p.suggest_tx_type("11.111.111/1111-11", self.EMITENTE, self.DESTINATARIO) == (
            None,
            False,
        )


class _ModelosFalsos:
    def __init__(self, resposta=None, erro=None):
        self._resposta = resposta
        self._erro = erro
        self.chamadas = []

    def generate_content(self, **kwargs):
        self.chamadas.append(kwargs)
        if self._erro is not None:
            raise self._erro
        return self._resposta


class _ClienteFalso:
    def __init__(self, resposta=None, erro=None):
        self.models = _ModelosFalsos(resposta, erro)


class _RespostaDoModelo:
    def __init__(self, text):
        self.text = text
        self.usage_metadata = None


JSON = (
    '{"amount": 1234.56, "date": "2026-06-17", '
    '"cnpj_emitente": "12345678000195", "cnpj_destinatario": null, '
    '"description": "Servico de manicure"}'
)


class TestParseJson:
    @pytest.mark.parametrize("bruto", ["{isto nao e json", "[1, 2, 3]", "null", ""])
    def test_resposta_ilegivel_vira_nulo(self, bruto):
        assert p._parse_json(bruto) is None

    def test_resposta_legivel_e_devolvida(self):
        assert p._parse_json('{"amount": 10}') == {"amount": 10}


class TestCaminhoDoGemini:
    def test_sem_cliente_devolve_nulo(self):
        assert p.gemini_de_imagem(None, "m", b"x", "image/png") is None
        assert p.gemini_de_texto(None, "m", "texto") is None

    def test_extrai_de_texto(self):
        cliente = _ClienteFalso(_RespostaDoModelo(JSON))
        assert p.gemini_de_texto(cliente, "gemini-x", "VALOR R$ 1.234,56")["date"] == "2026-06-17"

    def test_texto_vazio_nao_gasta_chamada(self):
        cliente = _ClienteFalso(_RespostaDoModelo(JSON))
        assert p.gemini_de_texto(cliente, "m", "   ") is None
        assert cliente.models.chamadas == []

    def test_texto_longo_e_truncado(self):
        cliente = _ClienteFalso(_RespostaDoModelo(JSON))
        p.gemini_de_texto(cliente, "m", "x" * 20000)
        assert len(cliente.models.chamadas[0]["contents"][1]) < 20000

    def test_erro_comum_do_modelo_vira_nulo(self):
        cliente = _ClienteFalso(erro=RuntimeError("resposta esquisita"))
        assert p.gemini_de_texto(cliente, "m", "texto") is None

    def test_erro_429_vira_falha_transitoria(self):
        cliente = _ClienteFalso(erro=RuntimeError("429 RESOURCE_EXHAUSTED"))
        with pytest.raises(p.FalhaTransitoriaGemini):
            p.gemini_de_texto(cliente, "m", "texto")


class TestProcessarArquivo:
    def _txt(self, tmp_path, conteudo=NOTA):
        arq = tmp_path / "nota.txt"
        arq.write_text(conteudo, encoding="utf-8")
        return arq

    def test_sem_gemini_usa_regex(self, tmp_path):
        arq = self._txt(tmp_path)
        extr = p.processar_arquivo(NOTA.encode(), ".txt", caminho=arq)
        assert extr.metodo == "regex"
        assert extr.estruturado["value"] == 1234.56
        assert extr.estruturado["confidence"] == 0.9
        assert extr.estruturado["tx_type_sugerido"] is None

    def test_com_gemini_usa_o_modelo(self, tmp_path):
        arq = self._txt(tmp_path)
        cliente = _ClienteFalso(_RespostaDoModelo(JSON))
        extr = p.processar_arquivo(
            NOTA.encode(), ".txt", caminho=arq, gemini_cliente=cliente, gemini_modelo="m"
        )
        assert extr.metodo == "gemini"
        assert extr.estruturado["value"] == 1234.56

    def test_cnpj_que_o_modelo_nao_achou_vem_do_ocr(self, tmp_path):
        """O JSON do modelo traz o destinatário nulo; o OCR o completa."""
        arq = self._txt(tmp_path)
        cliente = _ClienteFalso(_RespostaDoModelo(JSON))
        extr = p.processar_arquivo(
            NOTA.encode(), ".txt", caminho=arq, gemini_cliente=cliente, gemini_modelo="m"
        )
        assert extr.metodo == "gemini"
        assert extr.estruturado["cnpj_emitente"] == "12.345.678/0001-95"
        assert extr.estruturado["cnpj_destinatario"] == "98.765.432/0001-10"

    def test_cnpj_do_usuario_gera_sugestao(self, tmp_path):
        arq = self._txt(tmp_path)
        extr = p.processar_arquivo(
            NOTA.encode(), ".txt", caminho=arq, user_cnpj="12.345.678/0001-95"
        )
        assert extr.estruturado["tx_type_sugerido"] == "venda"
        assert extr.estruturado["tx_type_auto_detectado"] is True

    def test_falha_transitoria_cai_no_regex_por_padrao(self, tmp_path):
        arq = self._txt(tmp_path)
        cliente = _ClienteFalso(erro=RuntimeError("429 rate limit"))
        extr = p.processar_arquivo(
            NOTA.encode(), ".txt", caminho=arq, gemini_cliente=cliente, gemini_modelo="m"
        )
        assert extr.metodo == "regex"

    def test_falha_transitoria_propaga_quando_pedido(self, tmp_path):
        arq = self._txt(tmp_path)
        cliente = _ClienteFalso(erro=RuntimeError("503 unavailable"))
        with pytest.raises(p.FalhaTransitoriaGemini):
            p.processar_arquivo(
                NOTA.encode(),
                ".txt",
                caminho=arq,
                gemini_cliente=cliente,
                gemini_modelo="m",
                propagar_falha_transitoria=True,
            )


class TestCompletarCnpjsPeloOcr:
    def test_nao_troca_o_que_o_modelo_respondeu(self):
        estruturado = {"cnpj_emitente": "11.222.333/0001-81", "cnpj_destinatario": None}
        p.completar_cnpjs_pelo_ocr(estruturado, NOTA)
        assert estruturado["cnpj_emitente"] == "11.222.333/0001-81"
        assert estruturado["cnpj_destinatario"] == "98.765.432/0001-10"

    def test_nao_repete_o_cnpj_que_ja_ocupa_o_outro_papel(self):
        """Modelo pôs o 1º CNPJ do texto como destinatário: o OCR não pode
        devolvê-lo também como emitente."""
        estruturado = {"cnpj_emitente": None, "cnpj_destinatario": "12.345.678/0001-95"}
        p.completar_cnpjs_pelo_ocr(estruturado, NOTA)
        assert estruturado["cnpj_emitente"] is None

    def test_texto_sem_cnpj_nao_altera_nada(self):
        estruturado = {"cnpj_emitente": None, "cnpj_destinatario": None}
        assert p.completar_cnpjs_pelo_ocr(estruturado, "sem documento") == estruturado


class TestTetoDoOcr:
    """OCR travado não pode segurar o upload: estoura o teto e vira texto vazio."""

    def test_ocr_de_imagem_passa_o_teto_ao_tesseract(self, tmp_path, monkeypatch):
        import pytesseract
        from PIL import Image

        caminho = tmp_path / "nota.png"
        Image.new("RGB", (10, 10), "white").save(caminho)
        recebido = {}

        def falso(_imagem, **kwargs):
            recebido.update(kwargs)
            return "texto"

        monkeypatch.setattr(pytesseract, "image_to_string", falso)
        assert p.ocr_de_imagem(caminho) == "texto"
        assert recebido["timeout"] == p.OCR_TIMEOUT_SEGUNDOS

    def test_estouro_do_teto_degrada_para_texto_vazio(self, tmp_path, monkeypatch):
        def estoura(_caminho):
            raise RuntimeError("Tesseract process timeout")

        monkeypatch.setattr(p, "ocr_de_imagem", estoura)
        assert p.extrair_texto(tmp_path / "nota.png", ".png") == ""
